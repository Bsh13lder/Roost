"""A task's steps over HTTP (redesign P3): add, rename, tick or untick, budget, move and delete. The same
``StepService`` as the bots' step tools, so every change publishes ``tasks_changed``.

- Another user's task, a deleted task or a step the task doesn't have: 404.
- A title or a budget it refuses, or too many steps: 422 with the plain sentence.
- ``budget`` (owner, 2026-10-26) is the step's own budget in the task's currency; ``null`` clears it.
- Too many changes at once (the compare-and-set lost every try): 409, "Try again."
- Each answer is the task (``task_out``); deleting a step also says how many of its expenses and
  comments moved to the whole task."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Awaitable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from roost.constants import MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS
from roost.money.amounts import JsonAmount, parse_amount
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.tasks.format import task_out
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Task
from roost.tasks.step_service import StepRemoval, StepService
from roost.tasks.steps import StepNotFound
from roost.tasks.store import StepsBusy

steps_router = APIRouter(prefix="/api/tasks", tags=["steps"])
TASK_NOT_FOUND_TEXT = "Task not found"
NOTHING_TO_CHANGE_TEXT = "Send a new title, done, or a budget."


class StepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class StepPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=MAX_STEP_TITLE_LENGTH)
    done: StrictBool | None = None
    budget: JsonAmount | None = None     # sent as null: clear the step's budget

    @model_validator(mode="after")
    def _something_to_change(self) -> "StepPatchIn":
        if self.title is None and self.done is None and "budget" not in self.model_fields_set:
            raise ValueError(NOTHING_TO_CHANGE_TEXT)
        return self


class StepMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=0, le=MAX_TASK_STEPS - 1)   # 0 is first; past the end puts it last


def _service(request: Request) -> StepService:
    return request.app.state.steps


async def _settled(change: Awaitable[Task | StepRemoval | None]) -> Task | StepRemoval:
    """The change's result, or the HTTP error that says why there is none."""
    try:
        result = await change
    except StepNotFound as exc:
        raise HTTPException(status_code=404, detail=STEP_NOT_FOUND_TEXT) from exc
    except StepsBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return result


@steps_router.post("/{task_id}/steps", status_code=201, dependencies=[RequireOrigin])
async def add_step(task_id: str, body: StepIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    return task_out(await _settled(_service(request).add(user.id, task_id, body.title)))


@steps_router.patch("/{task_id}/steps/{step_id}", dependencies=[RequireOrigin])
async def update_step(task_id: str, step_id: str, body: StepPatchIn, request: Request,
                      user: CurrentUser) -> dict[str, Any]:
    """A new title, a tick (``done: true``) or an untick, a budget, or several."""
    service = _service(request)
    task = None
    if "budget" in body.model_fields_set:
        task = await _settled(service.set_budget(user.id, task_id, step_id, _budget(body.budget)))
    if body.title is not None:
        task = await _settled(service.rename(user.id, task_id, step_id, body.title))
    if body.done is not None:
        task = await _settled(service.set_done(user.id, task_id, step_id, body.done))
    return task_out(task)


def _budget(amount: JsonAmount | None) -> Decimal | None:
    """The amount by ``parse_amount``'s rules (a 422 with its sentence), or ``None`` to clear it."""
    try:
        return None if amount is None else parse_amount(amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@steps_router.post("/{task_id}/steps/{step_id}/move", dependencies=[RequireOrigin])
async def move_step(task_id: str, step_id: str, body: StepMoveIn, request: Request,
                    user: CurrentUser) -> dict[str, Any]:
    return task_out(await _settled(_service(request).move(user.id, task_id, step_id, body.position)))


@steps_router.delete("/{task_id}/steps/{step_id}", dependencies=[RequireOrigin])
async def delete_step(task_id: str, step_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    """The task without the step. Its expenses and comments stay on the task."""
    removal = await _settled(_service(request).delete(user.id, task_id, step_id))
    return {**task_out(removal.task), "moved_expenses": len(removal.moved_expenses),
            "moved_comments": removal.moved_comments}
