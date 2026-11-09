"""The money tools over the user's shared money (M1 D2, D7; projects hub H1,
H3, H6, H7, H11).

- ``log_expense`` alone keeps find-or-create for its project (H3). With a
  task and no project named, the money goes to the task's project; a project
  named outright wins. An archived project takes nothing (``MoneyService``).
- Every other money tool names a project exact-or-ask
  (``roost.projects.refs``): a near miss is refused for a change, and nothing
  is ever created from a name. ``set_budget`` sets or clears the total budget
  of a project, never General's. A move out of a project may land in General.
- An expense may be linked to a task of any status and one of its steps
  (``roost.money.expense_links``), starred, and voided: a void expense is
  still listed but never summed."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from roost.constants import EXPENSE_LIST_LIMIT
from roost.money.amounts import optional_amount, parse_amount
from roost.money.expense_links import ExpenseLink, find_link, project_conflict
from roost.money.format import escape, expense_line, money, summary_text
from roost.money.models import EXPENSE_POSTED, EXPENSE_VOID, KIND_INCOME, Expense, ExpensePatch, Project
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.tool_args import (
    ExpenseRefArgs, ListExpensesArgs, LogExpenseArgs, MonthArgs, SetBudgetArgs, UpdateExpenseArgs,
)
from roost.money.project_store import is_general
from roost.projects.refs import project_ref, required_project
from roost.projects.service import ProjectRefusal, ProjectService
from roost.records.paging import more_line
from roost.tags.record import bot_record_tags
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.models import Task
from roost.tasks.service import TaskService

__all__ = [
    "ExpenseRefArgs", "ListExpensesArgs", "LogExpenseArgs", "MonthArgs", "MoneyTools", "SetBudgetArgs",
    "UpdateExpenseArgs",
]

_ACTIVITY = {
    "log_expense": "logging an expense", "list_expenses": "checking your expenses",
    "money_summary": "adding up your month", "update_expense": "correcting an expense",
    "delete_expense": "deleting an expense", "set_budget": "setting a budget",
}
NO_EXPENSE_TEXT = "Refused: there is no expense with that id."
NOTHING_TO_CHANGE_TEXT = "Refused: nothing to change."
PROJECT_GONE_TEXT = "Refused: that project is gone."


def _same(value: Any) -> Any:
    return value


def _flag(value: Any) -> bool:
    """ExpensePatch takes a real bool for ``is_favorite``; whatever pydantic
    coerced the model's text to, hand it exactly that."""
    return bool(value)


def _status(void: Any) -> str:
    return EXPENSE_VOID if _flag(void) else EXPENSE_POSTED


# update_expense's plain arguments: (argument, Expense field, reader). A null leaves the field as it is.
_PLAIN = (("amount", "amount", parse_amount), ("spent_at", "spent_at", parse_spent_at),
          ("note", "description", _same), ("starred", "is_favorite", _flag), ("void", "status", _status))


def _month(value: str | None) -> str:
    month = value or current_month()
    month_bounds(month)   # raises a plain ValueError for a bad month
    return month


def _project_name(projects: Mapping[str, Project], expense: Expense) -> str:
    project = projects.get(expense.project_id)
    return project.name if project is not None else "?"


def _project_tainted(projects: Mapping[str, Project], expense: Expense) -> bool:
    project = projects.get(expense.project_id)
    return project is not None and project.tainted


def _plain_changes(args: UpdateExpenseArgs) -> dict[str, Any]:
    return {field: read(getattr(args, name)) for name, field, read in _PLAIN if getattr(args, name) is not None}


def _logged(expense: Expense, project: Project, link: ExpenseLink) -> str:
    task = f" for “{escape(link.task.title)}”" if link.task is not None else ""
    step = f", step “{escape(link.step.title)}”" if link.step is not None else ""
    starred = ", starred" if expense.is_favorite else ""
    kind = "money in " if expense.kind == KIND_INCOME else ""
    return (f"Logged {kind}{money(expense.amount, expense.currency)} to {escape(project.name)} on {expense.spent_at}"
            f"{task}{step}{starred} (id={expense.id}).")


def _updated(expense: Expense) -> str:
    void = " [void]" if expense.status == EXPENSE_VOID else ""
    starred = " [starred]" if expense.is_favorite else ""
    return f"Updated: {money(expense.amount, expense.currency)} on {expense.spent_at}{void}{starred}."


class MoneyTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: MoneyService, projects: ProjectService, tasks: TaskService) -> None:
        self._service = service
        self._projects = projects
        self._tasks = tasks

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"log_expense": self._log, "list_expenses": self._list, "money_summary": self._summary,
                    "update_expense": self._update, "delete_expense": self._delete, "set_budget": self._budget}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} got arguments it can't use; see its description.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {escape(str(exc))}")

    async def _log(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = LogExpenseArgs.model_validate(arguments)
        amount, day = parse_amount(args.amount), parse_spent_at(args.spent_at)
        link = await find_link(self._tasks, ctx.user_id, args.task, args.step)
        if isinstance(link, ToolOutcome):
            return link
        refused = await self._task_conflict(ctx.user_id, link.task, name=args.project)
        if refused is not None:
            return refused
        target = await self._log_project(ctx, args.project, link)
        tags = bot_record_tags(ctx, None if is_general(target) else target.name, args.tags)
        entry = ExpenseEntry(amount=amount, spent_at=day, project=target.name, note=args.note, vendor=args.vendor,
                             currency=args.currency, task_id=link.task_id, step_id=link.step_id,
                             starred=args.starred, income=args.income, tags=tags)
        expense, project = await self._service.log_expense(ctx.user_id, entry, created_by_bot=ctx.bot_id,
                                                            tainted=ctx.tainted, project=target)
        # The reply echoes the project's name and the task's title; web-made ones are web text (D3).
        return ToolOutcome(_logged(expense, project, link), created=True, tainted=project.tainted or link.tainted)

    async def _task_conflict(self, user_id: str, task: Task | None, *, project_id: str | None = None,
                             name: str | None = None) -> ToolOutcome | None:
        """A refusal when the project named can't hold an expense for ``task`` (it lives in the task's project)."""
        if task is None:
            return None
        held = None
        if task.project_id is not None:
            found = await self._projects.resolve(user_id, task.project_id, change=False)
            held = None if isinstance(found, ProjectRefusal) else found
        why = project_conflict(task, held, project_id=project_id, name=name)
        return None if why is None else ToolOutcome(f"Refused: {escape(why)}", tainted=task.tainted or (held is not None and held.tainted))

    async def _log_project(self, ctx: RecordContext, name: str | None, link: ExpenseLink) -> Project:
        """H3: the named project, found or made; with none named, the linked
        task's project; else General."""
        task = link.task
        if not (name or "").strip() and task is not None and task.project_id is not None:
            found = await self._projects.resolve(ctx.user_id, task.project_id, change=False)
            if not isinstance(found, ProjectRefusal):
                return found
        return await self._service.project_for(ctx.user_id, name, created_by_bot=ctx.bot_id, tainted=ctx.tainted)

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """Taint covers every expense shown AND every project name printed."""
        args = ListExpensesArgs.model_validate(arguments)
        month = _month(args.month)
        wanted = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(wanted, ToolOutcome):
            return wanted
        projects = {p.id: p for p in await self._service.projects(ctx.user_id)}
        expenses = await self._service.list_expenses(ctx.user_id, month)
        matching = tuple(e for e in expenses if wanted is None or e.project_id == wanted.id)
        shown = matching[args.offset:args.offset + EXPENSE_LIST_LIMIT]
        if not shown:
            return ToolOutcome("No expenses match." if not matching
                               else f"Nothing more: all {len(matching)} expenses are listed.")
        lines = "\n".join(expense_line(e, _project_name(projects, e)) for e in shown)
        tainted = any(e.tainted or _project_tainted(projects, e) for e in shown)
        return ToolOutcome(lines + more_line(len(matching), args.offset, len(shown)), tainted=tainted)

    async def _summary(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        summary, tainted = await self._service.summary(ctx.user_id, _month(MonthArgs.model_validate(arguments).month))
        return ToolOutcome(summary_text(summary), tainted=tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateExpenseArgs.model_validate(arguments)
        current = await self._service.get_expense(ctx.user_id, args.expense)
        if current is None:
            return ToolOutcome(NO_EXPENSE_TEXT)
        changes = await self._changes(args, current, ctx.user_id)
        if isinstance(changes, ToolOutcome):
            return changes
        if not changes:                       # for instance project='' alone, which names no project
            return ToolOutcome(NOTHING_TO_CHANGE_TEXT, tainted=current.tainted)
        expense = await self._service.update_expense(ctx.user_id, current.id, ExpensePatch(changes))
        if expense is None:
            return ToolOutcome(NO_EXPENSE_TEXT, tainted=current.tainted)
        # No project name or task title is echoed here, so they add no text (and no taint).
        return ToolOutcome(_updated(expense), tainted=current.tainted)

    async def _changes(self, args: UpdateExpenseArgs, current: Expense,
                       user_id: str) -> dict[str, Any] | ToolOutcome:
        """The patch: the plain fields, a move (exact-or-ask), and the task and step links."""
        plain = _plain_changes(args)
        project = await project_ref(self._projects, user_id, args.project, change=True, allow_general=True)
        if isinstance(project, ToolOutcome):
            return project
        links = await self._link_changes(args, current, user_id)
        if isinstance(links, ToolOutcome):
            return links
        moved = {} if project is None else {"project_id": project.id}
        followed = await self._follow_task(current, project, links, user_id)
        if isinstance(followed, ToolOutcome):
            return followed
        moved = {**moved, **followed}
        return {**plain, **moved, **links}

    async def _follow_task(self, current: Expense, project: Project | None, links: dict[str, Any],
                           user_id: str) -> dict[str, Any] | ToolOutcome:
        """The expense and its task share a project: a task newly linked pulls the expense into the
        task's project, and a project named for a linked task must be that task's."""
        task_id = links["task_id"] if "task_id" in links else current.task_id
        if task_id is None or (project is None and "task_id" not in links):
            return {}
        task = await self._tasks.get(user_id, task_id)
        if task is None:
            return {}
        refused = await self._task_conflict(user_id, task, project_id=None if project is None else project.id,
                                            name=None if project is None else project.name)
        if refused is not None:
            return refused
        return {"project_id": task.project_id} if project is None and task.project_id is not None else {}

    async def _link_changes(self, args: UpdateExpenseArgs, current: Expense,
                            user_id: str) -> dict[str, Any] | ToolOutcome:
        """``task`` '' unlinks the task and its step; ``step`` '' unlinks the
        step. A step needs a task: the one named here, else the expense's own.
        The task named again without a step keeps the step it already has."""
        if args.task is not None and not args.task.strip():
            return {"task_id": None, "step_id": None}
        if args.task is None and (args.step is None or not args.step.strip()):
            return {} if args.step is None else {"step_id": None}
        task_ref = args.task if args.task is not None else current.task_id
        link = await find_link(self._tasks, user_id, task_ref, args.step)
        if isinstance(link, ToolOutcome):
            return link
        if args.step is None and link.task_id == current.task_id:
            return {"task_id": link.task_id}      # the same task again: the step it was filed under stays
        return {"task_id": link.task_id, "step_id": link.step_id}

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        current = await self._service.get_expense(ctx.user_id, ExpenseRefArgs.model_validate(arguments).expense)
        if current is None:
            return ToolOutcome(NO_EXPENSE_TEXT)
        await self._service.delete_expense(ctx.user_id, current.id)
        return ToolOutcome(f"Deleted the {money(current.amount, current.currency)} expense of {current.spent_at}.",
                           tainted=current.tainted)

    async def _budget(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """H3: exact-or-ask, never a new project, never General; H5: an amount of '' clears the budget."""
        args = SetBudgetArgs.model_validate(arguments)
        amount = optional_amount(args.amount)
        found = await required_project(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(found, ToolOutcome):
            return found
        project = await self._service.set_budget(ctx.user_id, found, amount, created_by_bot=ctx.bot_id,
                                                 tainted=ctx.tainted)
        if project is None:
            return ToolOutcome(PROJECT_GONE_TEXT, tainted=found.tainted)
        if project.budget is None:
            return ToolOutcome(f"Budget for {escape(project.name)} cleared.", tainted=project.tainted)
        return ToolOutcome(f"Budget for {escape(project.name)}: {money(project.budget, project.currency)}.",
                           tainted=project.tainted)
