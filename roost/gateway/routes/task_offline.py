"""Offline tasks (owner, 2026-11-08, docs/plans/2026-11-08-roost-offline-tasks.md O4, O5).

The phone kept a quick line while it couldn't reach Roost. ``POST /api/tasks/offline`` reads it as of the moment
it was typed, never hands it to a bot (that needs your confirm), and keeps any part that would need a question (an
unknown project, a slice or a repeat it can't use) as plain words in the title: it never guesses. The phone's
``client_id`` makes it once: the same id again answers 200 with the task it already made."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from roost.constants import (
    MAX_TASK_TITLE_LENGTH, OFFLINE_CLOCK_SKEW_S, OFFLINE_TYPED_AT_MAX_AGE_DAYS, QUICK_LINE_MAX_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.tasks import TaskIn, _draft
from roost.money.amounts import amount_text
from roost.timezones import local_tz
from roost.tasks.format import task_out
from roost.tasks.models import Task
from roost.tasks.quick_line import QuickLine, read_quick_line
from roost.tasks.store import ClientIdTaken

offline_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TYPED_AT_TEXT = "That time is not one the phone could have typed the line at."
_NEVER_OFFLINE = frozenset({"assignee"})
# A part that would need a question, and the kind whose words then stay in the title.
_QUESTION_KINDS = (("project_question", "project"), ("budget_problem", "budget"), ("repeat_problem", "repeat"))


class OfflineTaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: UUID
    text: str = Field(min_length=1, max_length=QUICK_LINE_MAX_LENGTH)
    typed_at: AwareDatetime

    @field_validator("text")
    @classmethod
    def _has_words(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Type a few words for the task.")
        return value

    @field_validator("typed_at")
    @classmethod
    def _plausible(cls, value: datetime) -> datetime:
        now = datetime.now(local_tz())
        if value > now + timedelta(seconds=OFFLINE_CLOCK_SKEW_S) or value < now - timedelta(
                days=OFFLINE_TYPED_AT_MAX_AGE_DAYS):
            raise ValueError(TYPED_AT_TEXT)
        return value


def _questions(line: QuickLine) -> frozenset[str]:
    return frozenset(kind for field, kind in _QUESTION_KINDS if getattr(line, field))


async def _read(request: Request, user_id: str, body: OfflineTaskIn) -> QuickLine:
    """The line as of ``typed_at``; read once more with any part that asks a question left as words."""
    async def read(skip: frozenset[str]) -> QuickLine:
        return await read_quick_line(request.app.state.projects, user_id, body.text, skip=skip,
                                     now=body.typed_at.astimezone(local_tz()))
    line = await read(_NEVER_OFFLINE)
    asked = _questions(line)
    return line if not asked else await read(_NEVER_OFFLINE | asked)


def _task_in(line: QuickLine, text: str) -> TaskIn:
    """What the phone would have sent had it been online; a line of only chips keeps the whole line as its title."""
    title = line.title.strip() or " ".join(text.split())
    return TaskIn(
        title=title[:MAX_TASK_TITLE_LENGTH], due_date=line.due.due_date, priority=line.priority or "medium",
        project_id=None if line.project is None else line.project.id,
        allocated_budget=None if line.budget is None else amount_text(line.budget), tags=list(line.tags),
        starred=line.starred, estimate_minutes=line.estimate_minutes, reminder_at=line.reminder_at,
        recurring=line.recurring, recur_until=line.recur_until,
    )


def _made(task: Task, created: bool) -> dict[str, Any]:
    return {**task_out(task), "created": created}


@offline_router.post("/offline", status_code=201, dependencies=[RequireOrigin])
async def add_offline_task(body: OfflineTaskIn, request: Request, response: Response,
                           user: CurrentUser) -> dict[str, Any]:
    tasks = request.app.state.tasks
    client_id = str(body.client_id)
    if (existing := await tasks.by_client_id(user.id, client_id)) is not None:
        response.status_code = 200
        return _made(existing, False)
    line = await _read(request, user.id, body)
    try:
        task = await tasks.add(user.id, _draft(_task_in(line, body.text)), client_id=client_id)
    except ClientIdTaken:            # a second sync of the same line got here first
        response.status_code = 200
        return _made(await tasks.by_client_id(user.id, client_id), False)
    except ValueError as exc:        # a date or slice the store can't take
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _made(task, True)
