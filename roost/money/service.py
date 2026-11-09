"""``MoneyService`` — projects + expenses + the ``money_changed`` frame. Tools
and HTTP routes both go through it.

Projects hub:
- ``log_expense`` alone may make a project from a name (H3): an exact or typo
  match is reused, anything else is created.
- An archived project takes no new expense, and no expense moves into it (H3).
- An expense with no currency takes its project's (H7).
- ``set_budget`` sets or clears the total budget of a project the caller has
  already found (H3, H5): it never makes one."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Sequence

from roost.constants import GENERAL_INBOX_PAGE, GENERAL_PROJECT_NAME, PINNED_EXPENSES_MAX, PROJECT_STATUSES
from roost.events.hub import EventHub
from roost.money.board_summary import all_time_line, build_board, needs_all_time, prior_month
from roost.money.expense_store import ExpenseStore
from roost.money.models import KIND_EXPENSE, KIND_INCOME, Expense, ExpenseDraft, ExpensePatch, MoneySummary, Project
from roost.money.months import current_month, month_bounds, today_madrid
from roost.money.project_store import ProjectStore, is_general
from roost.money.recurring_service import RecurringService
from roost.money.recurring_store import RecurringStore
from roost.money.reports import MonthTotals, months_ending, trend
from roost.money.summary import summarize
from roost.records.project_link import NO_SUCH_PROJECT_TEXT
from roost.records.resolver import NamedRef, resolve

MoneyChange = Literal["expense_created", "expense_updated", "expense_deleted", "budget_set", "recurring_changed"]
ARCHIVED_TEXT = "“{name}” is archived; unarchive it first."
REPEAT_INCOME_TEXT = "Money in can't repeat yet: log each one on its own."
EXPENSE_GONE_PROJECT_TEXT = "Its project is gone; restore it into another project."
_ARCHIVED = PROJECT_STATUSES[1]


@dataclass(frozen=True)
class ExpenseEntry:
    """A parsed, validated expense to log (amount and day already read)."""

    amount: Decimal
    spent_at: str
    project: str | None = None
    note: str | None = None
    vendor: str | None = None
    currency: str | None = None      # None: the project's own currency (H7)
    task_id: str | None = None       # a task of any status (H11)
    step_id: str | None = None       # one of that task's steps
    starred: bool = False
    cadence: str | None = None       # weekly | monthly | yearly: also makes a repeating rule (the first charge is this day)
    income: bool = False             # money in: stored as kind "income", never counted as spent
    tags: tuple[str, ...] = ()       # a bot's expense: bot:<slug>, project:<slug> and its topic tags


def open_for_money(project: Project) -> Project:
    """H3: an archived project takes no new or moved expense (``ValueError``)."""
    if project.status == _ARCHIVED:
        raise ValueError(ARCHIVED_TEXT.format(name=project.name))
    return project


class MoneyService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, events: EventHub,
                 recurring: RecurringService | None = None) -> None:
        self._projects = projects
        self._expenses = expenses
        self._events = events
        self.recurring = recurring or RecurringService(RecurringStore(expenses.config, expenses), projects, events)

    async def project_for(self, user_id: str, name: str | None, *, created_by_bot: str | None,
                          tainted: bool) -> Project:
        """An existing project on its id, an exact or a typo match (harvested
        resolver), else a new one. A partial match never redirects money
        elsewhere. An id is a project, never a new name: list_projects prints
        ids, and a model that copies one must not make a project of it."""
        wanted = (name or "").strip() or GENERAL_PROJECT_NAME
        known = await self._projects.list(user_id)
        by_id = next((project for project in known if project.id == wanted), None)
        if by_id is not None:
            return by_id
        hit = resolve(wanted, [NamedRef(p.id, p.name) for p in known])
        if hit.resolved is not None and hit.reason in ("exact", "fuzzy"):
            return next(p for p in known if p.id == hit.resolved.id)
        return await self._projects.find_or_create(user_id, wanted, created_by_bot=created_by_bot, tainted=tainted)

    async def log_expense(self, user_id: str, entry: ExpenseEntry, *, created_by_bot: str | None = None,
                          tainted: bool = False, project: Project | None = None) -> tuple[Expense, Project]:
        """Log into ``project``, or else into the one ``entry.project`` names
        (found or made, H3). An archived project refuses (``ValueError``)."""
        target = open_for_money(project or await self.project_for(
            user_id, entry.project, created_by_bot=created_by_bot, tainted=tainted))
        draft = ExpenseDraft(
            project_id=target.id, amount=entry.amount, currency=entry.currency or target.currency,
            description=entry.note, vendor=entry.vendor, spent_at=entry.spent_at, task_id=entry.task_id,
            step_id=entry.step_id, is_favorite=entry.starred, kind=KIND_INCOME if entry.income else KIND_EXPENSE,
            tags=entry.tags,
        )
        rule = None
        if entry.income and entry.cadence is not None:
            raise ValueError(REPEAT_INCOME_TEXT)
        if entry.cadence is not None:
            rule = await self.recurring.start(
                user_id, target, amount=entry.amount, currency=draft.currency, note=entry.note, vendor=entry.vendor,
                cadence=entry.cadence, first_day=date.fromisoformat(entry.spent_at), created_by_bot=created_by_bot,
                tainted=tainted)
            draft = replace(draft, recurring_id=rule.id, occurrence=entry.spent_at)
        try:
            expense = await self._expenses.add(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        except BaseException:
            if rule is not None:
                await self.recurring.delete(user_id, rule.id)       # the first charge failed: no rule without it
            raise
        await self._changed(user_id, "expense_created", expense.id)
        return expense, target

    async def projects(self, user_id: str) -> tuple[Project, ...]:
        return await self._projects.list(user_id)

    async def list_expenses(self, user_id: str, month: str) -> tuple[Expense, ...]:
        await self.recurring.catch_up(user_id)
        return await self._expenses.list_month(user_id, month)

    async def range(self, user_id: str, first: date, last: date,
                    project_id: str | None = None) -> tuple[tuple[Expense, ...], dict[str, str]]:
        """The expenses spent on ``first..last`` (inclusive), voids included, newest first; and each repeating
        rule's cadence by id (so a row can say it repeats). Repeating charges are caught up first. ``project_id``
        narrows to one project (the route has checked it is the user's)."""
        await self.recurring.catch_up(user_id)
        following = (last + timedelta(days=1)).isoformat()
        expenses = await self._expenses.list_range(user_id, first.isoformat(), following, project_id)
        rules = {rule.id: rule.cadence for rule in await self.recurring.list(user_id, project_id)}
        return expenses, rules

    async def has_project(self, user_id: str, project_id: str) -> bool:
        """Whether this is one of the user's live projects (a report's ``project_id`` filter is theirs or a 404)."""
        return await self._projects.get(user_id, project_id) is not None

    async def trend(self, user_id: str, months: int, project_id: str | None = None) -> tuple[MonthTotals, ...]:
        """Each of the last ``months`` months' posted spending per currency (never mixed), ending this month."""
        await self.recurring.catch_up(user_id)
        window = months_ending(current_month(), months)
        first, _ = month_bounds(window[0])
        _, following = month_bounds(window[-1])
        return trend(await self._expenses.list_range(user_id, first, following, project_id), window)

    async def export_range(self, user_id: str, first_month: str, last_month: str, project_id: str | None,
                           limit: int) -> tuple[tuple[Expense, ...], bool]:
        """The expenses of the months ``first_month``..``last_month`` (inclusive), oldest first, at most ``limit``
        (the newest are kept when there are more); and whether it was cut."""
        await self.recurring.catch_up(user_id)
        first, _ = month_bounds(first_month)
        _, following = month_bounds(last_month)
        found = await self._expenses.list_range(user_id, first, following, project_id, limit + 1)
        return tuple(reversed(found[:limit])), len(found) > limit

    async def general_inbox(self, user_id: str, before: str | None) -> tuple[tuple[Expense, ...], str | None]:
        """One page of the expenses sitting in General (newest first) and the cursor for the next page."""
        await self.recurring.catch_up(user_id)
        general = next((p for p in await self._projects.list(user_id) if is_general(p)), None)
        if general is None:
            return (), None
        return await self._expenses.list_general(user_id, general.id, before, GENERAL_INBOX_PAGE)

    async def for_task(self, user_id: str, task_id: str) -> tuple[Expense, ...]:
        """Every expense filed under the task or one of its steps (redesign P3's drawer), voids included."""
        await self.recurring.catch_up(user_id)
        return await self._expenses.for_tasks(user_id, (task_id,))

    async def get_expense(self, user_id: str, expense_id: str) -> Expense | None:
        return await self._expenses.get(user_id, expense_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[tuple[Expense, Project | None], ...]:
        projects = {p.id: p for p in await self.projects(user_id)}
        expenses = await self._expenses.made_by(user_id, bot_id, limit)
        return tuple((expense, projects.get(expense.project_id)) for expense in expenses)

    async def summary(self, user_id: str, month: str) -> tuple[MoneySummary, bool]:
        """The month's summary and whether anything behind it is tainted: an
        expense in its totals, or a project whose name it prints. A web-made
        project the summary doesn't show leaves it clean (R1: taint must not
        spread to every conversation that adds up a month). A voided web-made
        expense still counts as tainted: that is the safe direction, and
        skipping voids would be a second rule to keep in step with the sums."""
        await self.recurring.catch_up(user_id)
        projects = await self._projects.list(user_id)
        expenses = await self._expenses.list_month(user_id, month)
        summary = summarize(month, projects, expenses)
        shown = {row.project for row in summary.by_project}
        tainted = any(e.tainted for e in expenses) or any(p.tainted for p in projects if p.name in shown)
        return summary, tainted

    async def board_summary(self, user_id: str, month: str) -> tuple[MoneySummary, tuple[Project, ...]]:
        """The month's summary with the Money tab's fields (G8: Today, change, limits, top project, coming up,
        pins, each row's total-budget bar), and the user's projects (the starred rows name theirs)."""
        summary, _ = await self.summary(user_id, month)
        projects = await self._projects.list(user_id)
        day = today_madrid()
        tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        previous = prior_month(month)
        all_time = {p.id: all_time_line(p, await self._expenses.list_project(user_id, p.id))
                    for p in needs_all_time(projects, summary)}
        built = build_board(
            summary, projects, all_time, day=day, today_expenses=await self._expenses.list_range(user_id, day, tomorrow),
            previous=previous, previous_expenses=await self._expenses.list_month(user_id, previous),
            charges=await self.recurring.upcoming(user_id),
            starred=await self._expenses.list_starred(user_id, PINNED_EXPENSES_MAX))
        return built, projects

    async def update_expense(self, user_id: str, expense_id: str, patch: ExpensePatch) -> Expense | None:
        """A move goes only into one of the user's open projects (H3):
        ``ValueError`` for an archived or unknown one, and nothing is written."""
        if "project_id" in patch.changes:
            await self._open_project(user_id, str(patch.changes["project_id"]))
        expense = await self._expenses.update(user_id, expense_id, patch)
        if expense is not None:
            await self._changed(user_id, "expense_updated", expense.id)
        return expense

    async def keep_expense(self, user_id: str, expense_id: str) -> tuple[Expense, Project | None] | None:
        """The user vouches for an expense on the Board (HTTP only, never a
        tool): it and the project name its row shows are theirs now, so a
        month listing them no longer taints a run. The project's budget
        history is not vouched for here: that is the project's own Keep."""
        expense = await self._expenses.keep(user_id, expense_id)
        if expense is None:
            return None
        project = await self._projects.keep_name(user_id, expense.project_id)
        await self._changed(user_id, "expense_updated", expense.id)
        return expense, project

    async def delete_expense(self, user_id: str, expense_id: str) -> bool:
        deleted = await self._expenses.delete(user_id, expense_id)
        if deleted:
            await self._changed(user_id, "expense_deleted", expense_id)
        return deleted

    async def restore_expense(self, user_id: str, expense_id: str) -> Expense | None:
        """Undo a delete. ``None``: no such deleted expense of this user's. ``ValueError``
        (``EXPENSE_GONE_PROJECT_TEXT``) when its project is gone; move it into another project first."""
        try:
            expense = await self._expenses.restore(user_id, expense_id)
        except ValueError as exc:
            raise ValueError(EXPENSE_GONE_PROJECT_TEXT) from exc
        if expense is not None:
            await self._changed(user_id, "expense_updated", expense.id)
        return expense

    async def move_expenses(self, user_id: str, expense_ids: Sequence[str],
                            project_id: str) -> dict[str, str] | None:
        """File these expenses under one of the user's open projects, all or none (``ExpenseStore.move_many``).
        ``ValueError`` for an archived, unknown or foreign project. ``None``: one id is not a live expense
        of this user's, and nothing moved. Returns each moved id's earlier project."""
        await self._open_project(user_id, project_id)
        moved = await self._expenses.move_many(user_id, expense_ids, project_id)
        if moved is not None:
            for expense_id in expense_ids:
                await self._changed(user_id, "expense_updated", expense_id)
        return moved

    async def expenses_by_id(self, user_id: str, expense_ids: Sequence[str]) -> dict[str, Expense]:
        return await self._expenses.get_many(user_id, expense_ids)

    async def set_budget(self, user_id: str, project: Project, amount: Decimal | None, *,
                         created_by_bot: str | None = None, tainted: bool = False) -> Project | None:
        """Set, or with ``None`` clear (H5), the total budget of a project the
        caller found. ``None``: the project is gone."""
        updated = await self._projects.set_budget(user_id, project.id, amount, created_by_bot=created_by_bot,
                                                  tainted=tainted)
        if updated is not None:
            await self._changed(user_id, "budget_set", project.id)
        return updated

    async def open_project(self, user_id: str, project_id: str) -> Project:
        """One of the user's open projects. ``ValueError``: unknown, foreign or archived."""
        return await self._open_project(user_id, project_id)

    async def _open_project(self, user_id: str, project_id: str) -> Project:
        target = await self._projects.get(user_id, project_id)
        if target is None:
            raise ValueError(NO_SUCH_PROJECT_TEXT)
        return open_for_money(target)

    async def _changed(self, user_id: str, change: MoneyChange, item_id: str) -> None:
        await self._events.publish(user_id, {"type": "money_changed", "change": change, "id": item_id})
