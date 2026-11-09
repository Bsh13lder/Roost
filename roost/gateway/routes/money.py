"""Money over HTTP — the Board's data (M1 D8)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from roost.constants import (
    GENERAL_PROJECT_NAME, MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH,
    MAX_EXPENSE_VENDOR_LENGTH, MAX_RECORD_ID_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import JsonAmount, parse_amount
from roost.money.expense_links import STEP_NEEDS_TASK_TEXT, project_conflict
from roost.money.currency import OptionalCurrencyCode
from roost.money.models import EXPENSE_POSTED, EXPENSE_VOID, ExpensePatch, Project
from roost.money.months import current_month, month_bounds, parse_spent_at
from roost.money.service import ExpenseEntry, MoneyService
from roost.money.summary import expense_row, summary_out
from roost.projects.service import NO_PROJECT_TEXT, ProjectRefusal
from roost.records.project_link import NO_SUCH_PROJECT_TEXT
from roost.tasks.quick_line import NO_PROJECT_HERE_TEXT
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Task

money_router = APIRouter(prefix="/api/money", tags=["money"])
EXPENSE_NOT_FOUND_TEXT = "Expense not found"
ONE_PROJECT_TEXT = "Name the project or send its id, not both."
NO_SUCH_TASK_TEXT = "No such task."
REPEAT_TASK_TEXT = "A repeating expense can't be for a task."


class ExpenseIn(BaseModel):
    """``project`` names a project (none: General). A project's page may send
    ``project_id`` instead. With no currency, the expense takes its project's
    currency, however the project was named (H7, Task 7's ``ExpenseEntry``)."""

    model_config = ConfigDict(extra="forbid")
    amount: JsonAmount
    project: str | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: str | None = Field(default=None, max_length=MAX_EXPENSE_VENDOR_LENGTH)
    starred: StrictBool = False
    income: StrictBool = False                                         # money in (v21): stored apart, never spent
    cadence: Literal["weekly", "monthly", "yearly"] | None = None      # also makes a repeating rule (Task 12)
    currency: OptionalCurrencyCode = None
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    # Redesign P3: an expense added from a task's drawer is filed under the task, or one of its steps.
    task_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    step_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    @model_validator(mode="after")
    def _one_way_to_name_the_project(self) -> "ExpenseIn":
        if self.project is not None and self.project_id is not None:
            raise ValueError(ONE_PROJECT_TEXT)
        if self.cadence is not None and (self.task_id is not None or self.step_id is not None):
            raise ValueError(REPEAT_TASK_TEXT)
        return self


class StarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starred: StrictBool


class VoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    void: StrictBool


def _service(request: Request) -> MoneyService:
    return request.app.state.money


def _month(month: str | None) -> str:
    value = month or current_month()
    try:
        month_bounds(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return value


@money_router.get("/summary")
async def money_summary(request: Request, user: CurrentUser, month: str | None = None):
    summary, projects = await _service(request).board_summary(user.id, _month(month))
    return summary_out(summary, {project.id: project for project in projects})


@money_router.get("/expenses")
async def list_expenses(request: Request, user: CurrentUser, month: str | None = None):
    service = _service(request)
    projects = {p.id: p for p in await service.projects(user.id)}
    return [expense_row(e, projects.get(e.project_id)) for e in await service.list_expenses(user.id, _month(month))]


@money_router.post("/expenses/{expense_id}/keep", dependencies=[RequireOrigin])
async def keep_expense(expense_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for an expense marked "from web content" and
    for the project name its row shows (no tool can do this)."""
    kept = await _service(request).keep_expense(user.id, expense_id)
    if kept is None:
        raise HTTPException(status_code=404, detail=EXPENSE_NOT_FOUND_TEXT)
    return expense_row(*kept)


async def _project_by_id(service: MoneyService, user_id: str, project_id: str) -> Project:
    """One of the user's projects, archived ones included. ``ValueError``: not one of theirs."""
    found = {project.id: project for project in await service.projects(user_id)}
    if project_id not in found:
        raise ValueError(NO_SUCH_PROJECT_TEXT)
    return found[project_id]


def _is_general(name: str) -> bool:
    return " ".join(name.casefold().split()) == GENERAL_PROJECT_NAME.casefold()


async def _named_project(request: Request, user_id: str, name: str | None) -> Project | None:
    """A project the web names is found or refused, never made (design P7): its id, its exact name or a
    unique part of one (``ProjectService.resolve``, ``change=True``). No name, or General, is ``None``
    (the service files it under General). ``ValueError`` (a 422, nothing written) with a plain sentence."""
    if name is None or _is_general(name) or not name.strip():
        return None
    found = await request.app.state.projects.resolve(user_id, name, change=True)
    if isinstance(found, ProjectRefusal):
        unknown = str(found) == NO_PROJECT_TEXT.format(name=name.strip())
        raise ValueError(NO_PROJECT_HERE_TEXT.format(name=name.strip()) if unknown else str(found))
    return found


async def _linked_task(request: Request, user_id: str, body: ExpenseIn) -> Task | None:
    """The task (and step) the expense is for: one of the user's tasks of any status, and one of
    its steps. ``ValueError`` (a 422, nothing written) for an unknown task or step, or a step alone."""
    if body.task_id is None:
        if body.step_id is not None:
            raise ValueError(STEP_NEEDS_TASK_TEXT)
        return None
    task = await request.app.state.tasks.get(user_id, body.task_id)
    if task is None:
        raise ValueError(NO_SUCH_TASK_TEXT)
    if body.step_id is not None and body.step_id not in {step.id for step in task.steps}:
        raise ValueError(STEP_NOT_FOUND_TEXT)
    return task


async def _check_task_project(service: MoneyService, user_id: str, task: Task, body: ExpenseIn) -> None:
    """An expense for a task lives in the task's project: any other project is a ``ValueError`` (422)."""
    task_project = None if task.project_id is None else {
        p.id: p for p in await service.projects(user_id)}.get(task.project_id)
    why = project_conflict(task, task_project, project_id=body.project_id, name=body.project)
    if why is not None:
        raise ValueError(why)


@money_router.post("/expenses", status_code=201, dependencies=[RequireOrigin])
async def add_expense(body: ExpenseIn, request: Request, user: CurrentUser):
    """A project named by id gets exactly that project (Task 7's ``project=``);
    one named by name is found or refused, never made (design P7). An archived project
    refuses (H3, ``ARCHIVED_TEXT``), so ``log_expense`` runs inside the ``try``.
    An expense for a task with no project named goes to the task's project."""
    service = _service(request)
    try:
        task = await _linked_task(request, user.id, body)
        entry = ExpenseEntry(amount=parse_amount(body.amount), spent_at=parse_spent_at(body.spent_at),
                             project=body.project, note=body.note, vendor=body.vendor, currency=body.currency,
                             task_id=body.task_id, step_id=body.step_id, starred=body.starred, cadence=body.cadence,
                             income=body.income)
        named = await _named_project(request, user.id, body.project)
        project_id = body.project_id if named is None else named.id
        if task is not None:
            await _check_task_project(service, user.id, task, body)
        if project_id is None and body.project is None and task is not None:
            project_id = task.project_id
        project = None if project_id is None else await _project_by_id(service, user.id, project_id)
        expense, target = await service.log_expense(user.id, entry, project=project)
    except ValueError as exc:   # an amount, a day, or a project it can't use
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return expense_row(expense, target)


async def _changed_row(request: Request, user_id: str, expense_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Apply one change from the Board and answer with the expense's row."""
    service = _service(request)
    try:
        expense = await service.update_expense(user_id, expense_id, ExpensePatch(changes))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if expense is None:
        raise HTTPException(status_code=404, detail=EXPENSE_NOT_FOUND_TEXT)
    projects = {project.id: project for project in await service.projects(user_id)}
    return expense_row(expense, projects.get(expense.project_id))


@money_router.put("/expenses/{expense_id}/star", dependencies=[RequireOrigin])
async def star_expense(expense_id: str, body: StarIn, request: Request, user: CurrentUser):
    """Star or unstar (P6). A starred expense counts in its project's starred total."""
    return await _changed_row(request, user.id, expense_id, {"is_favorite": body.starred})


@money_router.put("/expenses/{expense_id}/void", dependencies=[RequireOrigin])
async def void_expense(expense_id: str, body: VoidIn, request: Request, user: CurrentUser):
    """Void, or post again (H6). A void expense stays listed and leaves every sum."""
    status = EXPENSE_VOID if body.void else EXPENSE_POSTED
    return await _changed_row(request, user.id, expense_id, {"status": status})
