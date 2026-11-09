"""Reopen, move-overdue and restore-dues over HTTP (Task 10, design P11, §7).

- ``POST /api/tasks/{id}/reopen``: a done or failed task is open again (the Undo of a complete).
- ``POST /api/tasks/move-overdue``: every open overdue task gets one new due, all or none. ``to`` is words
  ("today"), an ISO day, a local ISO moment, or ``null`` for no date. The answer holds each task's old
  values, which ``restore-dues`` writes back. A task that was timed keeps its time when ``to`` names none.
- ``POST /api/tasks/restore-dues``: put those values back, all or none.
Another user's task is a 404 and nothing is written. Every write needs the origin header."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.constants import MAX_DUE_TEXT_LENGTH, MAX_PRE_REMINDERS, MAX_RECORD_ID_LENGTH, MOVE_OVERDUE_MAX, TASK_NO_PROJECT
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.tasks import project_scope
from roost.tasks.due import build_schedule
from roost.tasks.format import task_out
from roost.tasks.reminders import parse_iso_datetime
from roost.tasks.models import DueSet, Task
from roost.tasks.service import TaskService
from roost.tasks.views import counts, madrid_today, pick
from roost.timezones import local_tz

task_views_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
TASK_NOT_FOUND_TEXT = "Task not found"
PROJECT_NOT_FOUND_TEXT = "Project not found"
NO_CLOSED_TASK_TEXT = "No closed task with that id"
_CLOCK_START, _CLOCK_END = len("YYYY-MM-DDT"), len("YYYY-MM-DDTHH:MM")
_DAY_LENGTH = len("YYYY-MM-DD")
_ISO_START = re.compile(r"\d{4}-\d{2}-\d{2}")
_Iso = Annotated[str, Field(max_length=MAX_DUE_TEXT_LENGTH)]


_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MOMENT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)")
_BAD_DUE_TEXT = "“{value}” is not a due date. Use 2026-10-23 or a local time like 2026-10-23T09:30:00+02:00."
_BAD_MOMENT_TEXT = "“{value}” is not a time. Use a full time with its offset, like 2026-10-23T09:30:00+02:00."


def _moment(value: str) -> datetime | None:
    """An aware moment from strict ISO text (never a compact or offset-less form), else ``None``."""
    if not _MOMENT_RE.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _due_day_or_moment(value: str | None) -> str | None:
    """The due as ``build_schedule`` stores it: a plain day, or a local moment with seconds."""
    if value is None:
        return None
    if _DAY_RE.fullmatch(value):
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError as exc:
            raise ValueError(_BAD_DUE_TEXT.format(value=value)) from exc
    moment = _moment(value)
    if moment is None or moment.utcoffset() != moment.astimezone(local_tz()).utcoffset():
        raise ValueError(_BAD_DUE_TEXT.format(value=value))
    return moment.astimezone(local_tz()).isoformat(timespec="seconds")


def _utc_moment(value: str | None) -> str | None:
    """A reminder as stored: UTC, from text that names its offset."""
    if value is None:
        return None
    if _moment(value) is None:
        raise ValueError(_BAD_MOMENT_TEXT.format(value=value))
    return parse_iso_datetime(value).isoformat()   # type: ignore[union-attr]


class MoveOverdueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str | None = Field(default="today", max_length=MAX_DUE_TEXT_LENGTH)   # words, an ISO day or moment; null: no date


class DueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)
    due_date: _Iso | None
    reminder_at: _Iso | None
    pre_reminders: list[_Iso] = Field(default_factory=list, max_length=MAX_PRE_REMINDERS)

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return _due_day_or_moment(value)

    @field_validator("reminder_at")
    @classmethod
    def _one(cls, value: str | None) -> str | None:
        return _utc_moment(value)

    @field_validator("pre_reminders")
    @classmethod
    def _many(cls, values: list[str]) -> list[str]:
        return [_utc_moment(value) or "" for value in values]


class RestoreDuesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DueIn] = Field(min_length=1, max_length=MOVE_OVERDUE_MAX)


def _service(request: Request) -> TaskService:
    return request.app.state.tasks


def _due_out(due: DueSet) -> dict[str, Any]:
    return {"id": due.id, "due_date": due.due_date, "reminder_at": due.reminder_at,
            "pre_reminders": list(due.pre_reminders)}


def _checked_to(to: str | None) -> None:
    """Words are read by ``build_schedule``; text that starts like an ISO date must be one whole (no "T25:99")."""
    if to is None:
        return
    if _ISO_START.match(to.strip()):
        try:
            datetime.fromisoformat(to.strip())
        except ValueError as exc:
            raise ValueError(f"I could not read a date or time in “{to}”. Try 2026-10-23 or 2026-10-23T09:30.") from exc
    build_schedule(to, None, None)     # unreadable words are refused even when nothing is late


def _new_due(task: Task, to: str | None) -> DueSet:
    """The task's schedule once moved to ``to``; ``ValueError`` (plain sentence) for words it can't read."""
    if to is None:
        return DueSet(task.id, None, None, ())
    schedule = build_schedule(to, None, None)
    if schedule.reminder_at is None and schedule.due_date and task.due_date and len(task.due_date) > _DAY_LENGTH:
        clock = task.due_date[_CLOCK_START:_CLOCK_END]     # a timed task keeps its time
        schedule = build_schedule(f"{schedule.due_date}T{clock}", None, None)
    return DueSet(task.id, schedule.due_date, schedule.reminder_at, schedule.pre_reminders)


@task_views_router.get("/counts")
async def task_counts(request: Request, user: CurrentUser,
                      project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """What each Board tab counts (G1): overdue, today, the next 14 days, no date, done this week, and every
    open task. ``project_id`` narrows them to one of the user's projects (another's is a 404) or, as ``none``,
    to the tasks in no project; an empty one is no filter."""
    if project_id and project_id != TASK_NO_PROJECT and not await request.app.state.projects.owns(user.id, project_id):
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_TEXT)
    tasks = await _service(request).list(user.id, status="all", **project_scope(project_id))
    return asdict(counts(tasks, madrid_today()))


@task_views_router.post("/{task_id}/reopen", dependencies=[RequireOrigin])
async def reopen_task(task_id: str, request: Request, user: CurrentUser):
    task = await _service(request).reopen(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=NO_CLOSED_TASK_TEXT)
    return task_out(task)


@task_views_router.post("/move-overdue", dependencies=[RequireOrigin])
async def move_overdue(body: MoveOverdueIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        _checked_to(body.to)
        late = pick(await service.list(user.id), "overdue", today=madrid_today())[:MOVE_OVERDUE_MAX]
        items = [_new_due(task, body.to) for task in late]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    before = await service.move_dues(user.id, items) if items else ()
    if before is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return {"moved": [_due_out(due) for due in before]}


@task_views_router.post("/restore-dues", dependencies=[RequireOrigin])
async def restore_dues(body: RestoreDuesIn, request: Request, user: CurrentUser):
    items = [DueSet(item.id, item.due_date, item.reminder_at, tuple(item.pre_reminders)) for item in body.items]
    if await _service(request).move_dues(user.id, items) is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return {"restored": len(items)}
