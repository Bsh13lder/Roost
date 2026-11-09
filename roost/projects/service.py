"""``ProjectService`` — one place for projects (projects hub: P1, P2, P5, H2–H4,
H7, H9, H10, H15).

A project is a ``money_projects`` row (``ProjectStore``). Its expenses always
belong to one project; its tasks, notes and documents link to it by
``project_id``. Tools and HTTP routes both go through this service, so the
Board updates whoever changed a project: every change rides on
``money_changed`` with an H10 ``change`` and the project's or the top-up's id.
A total budget set or cleared from the Board (P3, H5) rides on it as
``MoneyService``'s ``budget_set``, the frame a bot's ``set_budget`` sends.

- General (H2) is hidden from the list and can be neither changed (its
  total budget and top-ups included) nor deleted, and no other project may
  take its name.
- A name a bot gives is exact-or-ask (H3, ``resolve``): a lone near miss may
  be read but never changed, several hits ask which one, and nothing is ever
  created from a name here.
- Every ``ValueError`` text is a plain sentence with no apostrophe, so the
  tools' ``html.escape`` leaves it readable (see ``TaskPatch``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from roost.bots.store import BotStore
from roost.constants import (
    GENERAL_PROJECT_NAME, PROJECT_LIST_LIMIT, PROJECT_MATCHES_SHOWN, PROJECT_PAGE_ITEMS, PROJECT_STATUSES,
    TOPUP_SOURCE_MAX_CHARS,
)
from roost.documents.models import DocumentMeta
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.money.amounts import parse_amount
from roost.money.expense_store import ExpenseStore
# LEAD_BOT_TEXT, STATUS_TEXT and CURRENCY_LOCKED_TEXT are Task 2's sentences, re-exported from here for
# the routes (Task 8), so a service refusal and a store refusal can never read differently.
from roost.money.models import (  # noqa: F401 — STATUS_TEXT is re-exported
    LEAD_BOT_TEXT, STATUS_TEXT, Expense, Project, ProjectDraft, ProjectPatch, TopUp,
)
from roost.money.months import current_month, today_madrid
from roost.money.project_store import CURRENCY_LOCKED_TEXT, ProjectStore, is_general
from roost.money.recurring import Recurring, UpcomingCharge
from roost.money.recurring_service import RecurringService
from roost.money.recurring_store import RecurringStore
from roost.money.service import MoneyChange      # "budget_set": the frame a bot's set_budget sends too
from roost.notes.models import Note
from roost.notes.store import NoteStore
from roost.projects.numbers import (
    Progress, ProjectNumbers, TaskMoney, counted, progress, project_numbers, task_money,
)
from roost.records.resolver import NamedRef, Resolve
from roost.records.resolver import resolve as resolve_name
from roost.tasks.models import Task
from roost.tasks.store import TaskStore

ProjectChange = Literal[
    "project_created", "project_updated", "project_deleted", "topup_added", "topup_edited", "topup_undone",
]
ProjectRow = tuple[Project, ProjectNumbers, Progress]

GENERAL_PIN_TEXT = "General can't be pinned."
GENERAL_FIXED_TEXT = "General is where expenses with no project go; it cannot be changed or deleted."
GENERAL_NAME_TEXT = "General is kept for expenses with no project; pick another name."
TOPUP_SOURCE_TEXT = f"A top-up source has at most {TOPUP_SOURCE_MAX_CHARS} characters."
NO_PROJECT_TEXT = "No project is called “{name}”. Use create_project first."
NEAR_MISS_TEXT = "No project is called “{name}”. Did you mean {names}? Say it exactly."
SEVERAL_TEXT = "Several projects match “{name}”. Say which one: {names}."
WEB_MARK = " [from web content]"

_OPEN_TASK = ("todo", "in_progress")
_ACTIVE = PROJECT_STATUSES[0]       # "active": archived projects are listed after the active ones


@dataclass(frozen=True)
class ProjectDetail:
    """A project's page (H14) and ``get_project``'s answer. ``numbers`` cover
    every expense; ``expenses``, ``notes`` and ``documents`` are the latest
    ``PROJECT_PAGE_ITEMS``; ``tasks`` and ``topups`` are complete. ``tainted``:
    the project or a record behind the page is web-made, an expense of another
    project that is part of a task's spent included. ``task_money``: each
    task's planned / spent / left (design §2, H11), over every expense linked
    to the task by id, whatever project it is filed under."""

    project: Project
    numbers: ProjectNumbers
    progress: Progress
    tasks: tuple[Task, ...]
    expenses: tuple[Expense, ...]
    notes: tuple[Note, ...]
    documents: tuple[DocumentMeta, ...]
    topups: tuple[TopUp, ...]
    lead_bot_name: str | None
    tainted: bool
    task_money: Mapping[str, TaskMoney]
    upcoming: tuple[UpcomingCharge, ...] = ()       # this project's charges due in the next 31 days (Task 12)
    repeating: tuple[Recurring, ...] = ()           # this project's repeating rules (G13)
    counts: Mapping[str, int] = MappingProxyType({})    # the page's tab counts: tasks_open, expenses, notes, documents


@dataclass(frozen=True)
class ProjectListing:
    """The Projects tab's rows, and whether a web-made expense (a voided one too: it was web text once)
    is behind the sums they print (M1 D3, R1)."""

    rows: tuple[ProjectRow, ...]
    web_money: bool


class ProjectRefusal(str):
    """``resolve``'s refusal: a plain, unescaped ``str`` (the contract's
    ``Project | str``) that also carries the taint of the project names it
    shows (M1 D3), so the tool that echoes it taints the run."""

    tainted: bool

    def __new__(cls, text: str, *, tainted: bool = False) -> ProjectRefusal:
        refusal = super().__new__(cls, text)
        refusal.tainted = tainted
        return refusal


def _folded(name: str) -> str:
    """The folding ``ProjectStore``'s ``name_key`` uses: case and spacing ignored."""
    return " ".join(name.casefold().split())


def _is_general_name(name: str) -> bool:
    return _folded(name) == _folded(GENERAL_PROJECT_NAME)


def _clean_source(source: str | None) -> str | None:
    text = (source or "").strip()
    if len(text) > TOPUP_SOURCE_MAX_CHARS:
        raise ValueError(TOPUP_SOURCE_TEXT)
    return text or None


def _names(projects: Sequence[Project]) -> str:
    """Names for a refusal, by name, each web-made one marked as such."""
    shown = sorted(projects, key=lambda project: project.name.casefold())
    return "; ".join(f"“{project.name}”" + (WEB_MARK if project.tainted else "") for project in shown)


def _refusal(name: str, hit: Resolve, by_id: Mapping[str, Project]) -> ProjectRefusal:
    """H3's three refusals. One that lists names carries their taint (M1 D3)."""
    shown = tuple(by_id[candidate.id] for candidate in hit.candidates[:PROJECT_MATCHES_SHOWN])
    tainted, wanted = any(project.tainted for project in shown), name.strip()
    if hit.reason == "fuzzy":
        return ProjectRefusal(NEAR_MISS_TEXT.format(name=wanted, names=_names(shown)), tainted=tainted)
    if hit.reason == "multi":
        return ProjectRefusal(SEVERAL_TEXT.format(name=wanted, names=_names(shown)), tainted=tainted)
    return ProjectRefusal(NO_PROJECT_TEXT.format(name=wanted))


class ProjectService:
    def __init__(self, projects: ProjectStore, expenses: ExpenseStore, tasks: TaskStore, notes: NoteStore,
                 documents: DocumentStore, bots: BotStore, events: EventHub,
                 recurring: RecurringService | None = None) -> None:
        self._projects = projects
        self._expenses = expenses
        self._tasks = tasks
        self._notes = notes
        self._documents = documents
        self._bots = bots
        self._events = events
        self._recurring = recurring or RecurringService(RecurringStore(expenses.config, expenses), projects, events)

    async def names(self, user_id: str) -> tuple[str, ...]:
        """The names of the user's projects (General apart), for readers that match typed words to one."""
        found = await self._projects.list(user_id, include_archived=True)
        return tuple(project.name for project in found if not is_general(project))

    async def general_currency(self, user_id: str) -> str:
        """The currency a task in no project counts its money in (owner, 2026-10-26)."""
        return await self._projects.general_currency(user_id)

    async def list(self, user_id: str, *, include_archived: bool = False) -> tuple[ProjectRow, ...]:
        """The Projects tab and ``list_projects``: General hidden (H2), active
        before archived, then by name, at most ``PROJECT_LIST_LIMIT``. Tasks
        are one query, grouped here. Expenses are read per project shown,
        because the store has no all-projects read and every amount is
        decrypted either way."""
        return (await self.listing(user_id, include_archived=include_archived)).rows

    async def listing(self, user_id: str, *, include_archived: bool = False) -> ProjectListing:
        """``list`` plus whether a web-made expense is behind its sums, judged on the expenses it
        read for them, so a caller that needs both (``list_projects``) never reads them twice."""
        await self._recurring.catch_up(user_id)
        found = await self._projects.list(user_id, include_archived=include_archived)
        shown = sorted((project for project in found if not is_general(project)),
                       key=lambda project: (project.status != _ACTIVE, project.name.casefold()))
        tasks = await self._tasks.list(user_id, status="all")
        month = current_month()
        rows: list[ProjectRow] = []
        web_money = False
        for project in shown[:PROJECT_LIST_LIMIT]:
            expenses = await self._expenses.list_project(user_id, project.id)
            rows.append(self._row(project, expenses, tasks, month))
            web_money = web_money or any(expense.tainted for expense in expenses)
        return ProjectListing(rows=tuple(rows), web_money=web_money)

    async def detail(self, user_id: str, project_id: str, *, now: datetime | None = None) -> ProjectDetail | None:
        """``now`` (default: the real clock) decides the local month and day the numbers and the repeating-charge
        catch-up use; the budget-alert job passes its own clock."""
        project = await self._projects.get(user_id, project_id)
        if project is None:
            return None
        today = None if now is None else date.fromisoformat(today_madrid(now))
        upcoming = await self._recurring.upcoming(user_id, project_id, today)      # catches up first
        expenses = await self._expenses.list_project(user_id, project_id)
        tasks = await self._tasks.list(user_id, status="all", project_id=project_id)
        notes = await self._notes.for_project(user_id, project_id, PROJECT_PAGE_ITEMS)
        documents = await self._documents.for_project(user_id, project_id, PROJECT_PAGE_ITEMS)
        topups = await self._projects.topups(user_id, project_id)
        linked = await self._expenses.for_tasks(user_id, tuple(task.id for task in tasks))
        # A task's spent also counts expenses filed under other projects: the page shows that number.
        behind_spent = tuple(e for e in linked if e.project_id != project_id and counted(e, project.currency))
        records = (*tasks, *expenses, *notes, *documents, *topups, *behind_spent)
        return ProjectDetail(
            project=project, numbers=project_numbers(project, expenses, current_month(now)), progress=progress(tasks),
            tasks=tasks, expenses=expenses[:PROJECT_PAGE_ITEMS],      # list_project is newest spent_at first
            notes=notes, documents=documents, topups=topups,
            lead_bot_name=await self._lead_bot_name(user_id, project.lead_bot_id),
            tainted=project.tainted or any(record.tainted for record in records),
            task_money=MappingProxyType({task.id: task_money(task, linked, project.currency) for task in tasks}),
            upcoming=upcoming, repeating=await self._recurring.list(user_id, project_id),
            counts=MappingProxyType({
                "tasks_open": sum(1 for task in tasks if task.status in _OPEN_TASK),
                "expenses": len(expenses),
                "notes": await self._notes.count_for_project(user_id, project_id),
                "documents": await self._documents.count_for_project(user_id, project_id),
            }),
        )

    async def create(self, user_id: str, draft: ProjectDraft, *, created_by_bot: str | None = None,
                     tainted: bool = False) -> Project:
        """A new project. The store checks its fields and refuses a name in use."""
        if _is_general_name(draft.name):
            raise ValueError(GENERAL_NAME_TEXT)
        await self._check_lead_bot(user_id, draft.lead_bot_id)
        project = await self._projects.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "project_created", project.id)
        return project

    async def update(self, user_id: str, project_id: str, changes: Mapping[str, object]) -> Project | None:
        """Rename, colour, dates, lead bot, monthly limit, archive / unarchive
        and currency. ``None``: no such project."""
        patch = ProjectPatch(changes)          # each field's shape, the status included, checked and tidied
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        await self._check_changes(user_id, current, patch.changes)
        updated = await self._projects.update(user_id, project_id, patch)
        if updated is not None:
            await self._changed(user_id, "project_updated", updated.id)
        return updated

    async def set_pinned(self, user_id: str, project_id: str, pinned: bool) -> Project | None:
        """Pin or unpin from the Board. General is never pinned (``ValueError``). ``None``: no such project."""
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        if is_general(current):
            raise ValueError(GENERAL_PIN_TEXT)
        if current.pinned == pinned:
            return current     # nothing changed: pinned_at stays and no event goes out
        updated = await self._projects.set_pinned(user_id, project_id, pinned)
        if updated is not None:
            await self._changed(user_id, "project_updated", updated.id)
        return updated

    async def keep(self, user_id: str, project_id: str) -> Project | None:
        """The user vouches for a project made from web content (the Board's
        Keep): its mark goes. HTTP only, never a tool. ``None``: no such project."""
        kept = await self._projects.keep(user_id, project_id)
        if kept is not None:
            await self._changed(user_id, "project_updated", kept.id)
        return kept

    async def delete(self, user_id: str, project_id: str) -> bool:
        """H9 in the store's one transaction: the expenses move to General, the
        tasks, notes and documents lose the link and stay, and the project is
        soft-deleted. ``project_deleted`` makes every open tab refresh them."""
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return False
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        deleted = await self._projects.delete(user_id, project_id)
        if deleted:
            await self._recurring.delete_for_project(user_id, project_id)     # its repeating rules go with it
            await self._changed(user_id, "project_deleted", project_id)
        return deleted

    async def owns(self, user_id: str, project_id: str) -> bool:
        """Whether ``project_id`` is one of the user's live projects (archived and General included)."""
        return await self._projects.get(user_id, project_id) is not None

    async def ensure_linkable(self, user_id: str, project_id: str | None) -> None:
        """H2: tasks, notes and documents never file under General, the tools' rule
        too (``project_ref``). ``ValueError`` with the General sentence when
        ``project_id`` is General. ``None`` (no link) and an id that is not one of
        the user's projects pass: the record's own write refuses those."""
        if project_id is None:
            return
        found = await self._projects.get(user_id, project_id)
        if found is not None and is_general(found):
            raise ValueError(GENERAL_FIXED_TEXT)

    async def set_budget(self, user_id: str, project_id: str, amount: Decimal | None) -> Project | None:
        """Set the total budget from the Board (P3), or clear it with ``None``
        (H5). The store writes the "Budget set" row. General is refused like
        any other change to it (H2). ``None``: no such project."""
        checked = None if amount is None else parse_amount(amount)
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        updated = await self._projects.set_budget(user_id, project_id, checked, created_by_bot=None, tainted=False)
        if updated is not None:
            await self._changed(user_id, "budget_set", project_id)
        return updated

    async def add_topup(self, user_id: str, project_id: str, amount: Decimal, source: str | None = None, *,
                        created_by_bot: str | None = None, tainted: bool = False) -> TopUp | None:
        """Raise the total budget by ``amount`` (H4). General has no budget, so
        it takes no top-up either (H2). ``None``: no such project."""
        checked, cleaned = parse_amount(amount), _clean_source(source)
        current = await self._projects.get(user_id, project_id)
        if current is None:
            return None
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        topup = await self._projects.add_topup(user_id, project_id, checked, cleaned,
                                               created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "topup_added", topup.id)
        return topup

    async def edit_topup(self, user_id: str, topup_id: str, amount: Decimal) -> TopUp | None:
        """``amount`` is the top-up's new amount; the store writes the difference (H4)."""
        topup = await self._projects.edit_topup(user_id, topup_id, parse_amount(amount))
        if topup is not None:
            await self._changed(user_id, "topup_edited", topup_id)
        return topup

    async def undo_topup(self, user_id: str, topup_id: str) -> TopUp | None:
        """The top-up and all its edits leave the budget together (H4)."""
        topup = await self._projects.undo_topup(user_id, topup_id)
        if topup is not None:
            await self._changed(user_id, "topup_undone", topup_id)
        return topup

    async def topups(self, user_id: str, project_id: str) -> tuple[TopUp, ...] | None:
        """The history, newest first, with undone rows. ``None``: no such project."""
        if await self._projects.get(user_id, project_id) is None:
            return None
        return await self._projects.topups(user_id, project_id)

    async def resolve(self, user_id: str, name: str, *, change: bool) -> Project | ProjectRefusal:
        """Exact-or-ask (H3) over every live project, archived ones included:
        an id, an exact name or a unique part of one. A lone near miss is
        read (``change=False``) but never changed. Nothing is ever created."""
        known = await self._projects.list(user_id, include_archived=True)
        by_id = {project.id: project for project in known}
        if name.strip() in by_id:
            return by_id[name.strip()]
        hit = resolve_name(name, [NamedRef(project.id, project.name) for project in known])
        if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
            return by_id[hit.resolved.id]
        return _refusal(name, hit, by_id)

    @staticmethod
    def _row(project: Project, expenses: Sequence[Expense], tasks: Sequence[Task], month: str) -> ProjectRow:
        own = tuple(task for task in tasks if task.project_id == project.id)
        return project, project_numbers(project, expenses, month), progress(own)

    async def _check_changes(self, user_id: str, current: Project, changes: Mapping[str, object]) -> None:
        """The rules only the service can check, on ``ProjectPatch``'s tidied
        values (an upper-cased currency, a stripped bot id). The patch already
        checked each field's shape, the status included."""
        if is_general(current):
            raise ValueError(GENERAL_FIXED_TEXT)
        if "name" in changes and _is_general_name(str(changes["name"])):
            raise ValueError(GENERAL_NAME_TEXT)
        if "lead_bot_id" in changes:
            await self._check_lead_bot(user_id, changes["lead_bot_id"])
        new_currency = changes.get("currency", current.currency)
        if new_currency != current.currency and await self._projects.has_money(user_id, current.id):
            raise ValueError(CURRENCY_LOCKED_TEXT)

    async def _check_lead_bot(self, user_id: str, bot_id: object) -> None:
        """H15: a lead bot is one of the user's own bots; ``None`` clears it."""
        if bot_id is None:
            return
        if not isinstance(bot_id, str) or await self._bots.get(user_id, bot_id) is None:
            raise ValueError(LEAD_BOT_TEXT)

    async def _lead_bot_name(self, user_id: str, bot_id: str | None) -> str | None:
        bot = await self._bots.get(user_id, bot_id) if bot_id else None
        return bot.name if bot is not None else None

    async def _changed(self, user_id: str, change: ProjectChange | MoneyChange, item_id: str) -> None:
        await self._events.publish(user_id, {"type": "money_changed", "change": change, "id": item_id})
