"""Edit, delete, restore and bulk-move expenses over HTTP (Task 8, design §8, P9).

- ``PATCH /api/money/expenses/{id}``: amount, note, vendor, day (day words, never a future day), project.
- ``DELETE /api/money/expenses/{id}``: soft delete (204); ``POST …/{id}/restore`` undoes it.
- ``POST /api/money/expenses/move``: up to ``BULK_MOVE_MAX`` expenses into one open project, all or none.

Another user's expense is a 404 and nothing is written; in a bulk move one id that is not the user's refuses
the whole batch. Every write needs the origin header. An expense for a task stays in the task's project."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import (
    BULK_MOVE_MAX, MAX_DUE_TEXT_LENGTH, MAX_EXPENSE_NOTE_LENGTH, MAX_EXPENSE_VENDOR_LENGTH, MAX_RECORD_ID_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.money.amounts import JsonAmount, parse_amount
from roost.money.expense_links import TASK_IN_TEXT, TASK_NO_PROJECT_TEXT
from roost.money.models import Expense, ExpensePatch, Project
from roost.money.months import parse_spent_at
from roost.money.project_store import is_general
from roost.money.service import MoneyService
from roost.money.summary import expense_row
from roost.tasks.models import Task

money_edit_router = APIRouter(prefix="/api/money", tags=["money"])
EXPENSE_NOT_FOUND_TEXT = "Expense not found"
NOTHING_TO_CHANGE_TEXT = "Send at least one thing to change."
CANT_CLEAR_TEXT = "{field} can't be cleared."
DUPLICATE_IDS_TEXT = "Each expense can be listed once."
_RecordId = Annotated[str, Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)]


class ExpensePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: JsonAmount | None = None
    note: str | None = Field(default=None, max_length=MAX_EXPENSE_NOTE_LENGTH)
    vendor: str | None = Field(default=None, max_length=MAX_EXPENSE_VENDOR_LENGTH)
    spent_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    @model_validator(mode="after")
    def _something_to_change(self) -> "ExpensePatchIn":
        if not self.model_fields_set:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        for field in ("amount", "spent_at", "project_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(CANT_CLEAR_TEXT.format(field=field))
        return self

    def changes(self) -> dict[str, Any]:
        """The patch's columns, read and checked (``ValueError``: a plain sentence). A blank note or
        vendor clears it."""
        sent = self.model_fields_set
        found: dict[str, Any] = {}
        if "amount" in sent:
            found["amount"] = parse_amount(self.amount)
        if "spent_at" in sent:
            found["spent_at"] = parse_spent_at(self.spent_at)
        if "note" in sent:
            found["description"] = (self.note or "").strip() or None
        if "vendor" in sent:
            found["vendor"] = (self.vendor or "").strip() or None
        if "project_id" in sent:
            found["project_id"] = self.project_id
        return found


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expense_ids: list[_RecordId] = Field(min_length=1, max_length=BULK_MOVE_MAX)
    project_id: _RecordId

    @model_validator(mode="after")
    def _each_once(self) -> "MoveIn":
        if len(set(self.expense_ids)) != len(self.expense_ids):
            raise ValueError(DUPLICATE_IDS_TEXT)
        return self


def _service(request: Request) -> MoneyService:
    return request.app.state.money


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=EXPENSE_NOT_FOUND_TEXT)


def _unusable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _leaves_its_task(task: Task, task_project: Project | None, target: Project) -> str | None:
    """Why an expense filed under ``task`` can't go to ``target``, or ``None``: it lives in the task's project,
    and for a task with no project in General."""
    if task.project_id is None:
        return None if is_general(target) else TASK_NO_PROJECT_TEXT
    if target.id == task.project_id:
        return None
    return TASK_IN_TEXT.format(project=task_project.name if task_project else "another project")


async def _check_task_links(request: Request, user_id: str, expenses: list[Expense], project_id: str) -> None:
    """``ValueError`` when any of these expenses is for a task and ``project_id`` is not the task's project.
    A project that is not the user's is the service's refusal, so it is skipped here."""
    service = _service(request)
    projects = {project.id: project for project in await service.projects(user_id)}
    target = projects.get(project_id)
    if target is None:
        return
    for expense in expenses:
        if expense.task_id is None:
            continue
        task = await request.app.state.tasks.get(user_id, expense.task_id)
        if task is None:
            continue
        why = _leaves_its_task(task, projects.get(task.project_id or ""), target)
        if why is not None:
            raise ValueError(why)


async def _row(request: Request, user_id: str, expense: Expense) -> dict[str, Any]:
    projects = {project.id: project for project in await _service(request).projects(user_id)}
    return expense_row(expense, projects.get(expense.project_id))


@money_edit_router.patch("/expenses/{expense_id}", dependencies=[RequireOrigin])
async def patch_expense(expense_id: str, body: ExpensePatchIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        changes = body.changes()
        current = await service.get_expense(user.id, expense_id)
        if current is None:
            raise _not_found()
        if "project_id" in changes:
            await _check_task_links(request, user.id, [current], changes["project_id"])
        expense = await service.update_expense(user.id, expense_id, ExpensePatch(changes))
    except ValueError as exc:
        raise _unusable(exc) from exc
    if expense is None:
        raise _not_found()
    return await _row(request, user.id, expense)


@money_edit_router.delete("/expenses/{expense_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_expense(expense_id: str, request: Request, user: CurrentUser) -> Response:
    if not await _service(request).delete_expense(user.id, expense_id):
        raise _not_found()
    return Response(status_code=204)


@money_edit_router.post("/expenses/{expense_id}/restore", dependencies=[RequireOrigin])
async def restore_expense(expense_id: str, request: Request, user: CurrentUser):
    try:
        expense = await _service(request).restore_expense(user.id, expense_id)
    except ValueError as exc:
        raise _unusable(exc) from exc
    if expense is None:
        raise _not_found()
    return await _row(request, user.id, expense)


@money_edit_router.post("/expenses/move", dependencies=[RequireOrigin])
async def move_expenses(body: MoveIn, request: Request, user: CurrentUser):
    service = _service(request)
    found = await service.expenses_by_id(user.id, body.expense_ids)
    if len(found) != len(body.expense_ids):
        raise _not_found()                      # one that is not the user's refuses the whole batch
    try:
        await _check_task_links(request, user.id, list(found.values()), body.project_id)
        moved = await service.move_expenses(user.id, body.expense_ids, body.project_id)
    except ValueError as exc:
        raise _unusable(exc) from exc
    if moved is None:
        raise _not_found()
    return {"moved": [{"id": expense_id, "from_project_id": moved[expense_id]} for expense_id in body.expense_ids]}
