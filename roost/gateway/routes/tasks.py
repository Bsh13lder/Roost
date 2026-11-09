"""Tasks over HTTP — the Board's data (M1 D8). Same ``TaskService`` as the
tools, so every change publishes ``tasks_changed``.

Projects hub (H11): a task may join one of the user's projects and carry a
budget slice in that project's currency. A project that isn't the user's is
refused (422, "No such project."), ``?project_id=`` lists one project's tasks,
and ``POST /{id}/fail`` closes an open task as failed.

Deleting is soft, so ``POST /{id}/restore`` is Delete's exact Undo: the same task (id, steps, comments) comes
back; 404 when the id is not one of the user's deleted tasks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Sequence

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from roost.bots.models import Bot
from roost.constants import (
    TASK_RANGE_MAX_DAYS, TASK_SEARCH_MAX_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_PRE_REMINDERS, MAX_RECORD_ID_LENGTH, MAX_TASK_CATEGORY_LENGTH, MAX_TASK_NOTES_LENGTH,
    MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS, MAX_TASK_TAG_LENGTH, MAX_TASK_TAGS, MAX_TASK_TITLE_LENGTH, TASK_ESTIMATE_MAX_MINUTES,
    TASK_IDS_QUERY_MAX, TASK_NO_PROJECT,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import refuse_general
from roost.money.amounts import JsonAmount, parse_amount
from roost.tasks.assign import assign_task
from roost.tasks.comment_store import CommentStore
from roost.tasks.due import build_schedule, patch_from_fields, validate_recur_until
from roost.tasks.format import task_out
from roost.projects.service import ProjectRefusal
from roost.tasks.models import Priority, Task, TaskDraft, TaskFilter
from roost.tasks.recurrence import validate_cron
from roost.tasks.service import TaskService
from roost.tasks.slice_note import slice_note
from roost.money.expense_store import ExpenseStore
from roost.tasks.row_money import money_task_ids, row_money_out, rows_money, sort_by_money_left
from roost.tasks.views import FINISHABLE_VIEWS, TaskSort, TaskView, due_bucket, in_range, madrid_today, pick

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
NO_OPEN_TASK_TEXT = "No open task with that id"
NO_DELETED_TASK_TEXT = "No deleted task with that id"
ASSIGN_CONFIRM_TEXT = "Confirm handing this to {name} first."
NO_SUCH_BOT_TEXT = "No such bot."
Amount = JsonAmount


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority = "medium"
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    allocated_budget: Amount | None = None      # the budget slice, in the project's currency; needs a project
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)   # words or ISO
    recurring: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)     # a cron, or a repeat rule (JSON)
    recur_until: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)   # the series' last day
    tags: list[Annotated[str, Field(min_length=1, max_length=MAX_TASK_TAG_LENGTH)]] = Field(
        default_factory=list, max_length=MAX_TASK_TAGS)                              # #tags
    steps: list[Annotated[str, Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)]] = Field(
        default_factory=list, max_length=MAX_TASK_STEPS)                            # checklist titles
    starred: StrictBool = False
    estimate_minutes: StrictInt | None = Field(default=None, ge=1, le=TASK_ESTIMATE_MAX_MINUTES)
    assign_bot_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # hand it to this bot...
    assign_confirmed: StrictBool = False                                                # ...once you confirmed


class TaskPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority | None = None
    status: Literal["todo", "in_progress", "cancelled"] | None = None
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)   # null unlinks
    allocated_budget: Amount | None = None                                           # null clears the slice
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)   # words or ISO; null clears
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)   # with reminder_at; [] none
    recurring: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)     # a cron; null: no repeat
    starred: StrictBool | None = None
    estimate_minutes: StrictInt | None = Field(default=None, ge=1, le=TASK_ESTIMATE_MAX_MINUTES)   # null clears


def _service(request: Request) -> TaskService:
    return request.app.state.tasks


def project_scope(project_id: str | None) -> dict[str, Any]:
    """The task list's project filter: ``TASK_NO_PROJECT`` keeps the tasks in no project, an id keeps that
    project's, and a missing or empty value keeps every task."""
    if project_id == TASK_NO_PROJECT:
        return {"no_project": True}
    return {"project_id": project_id or None}


def _unreadable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _slice(amount: Amount | None) -> Decimal | None:
    """A budget slice follows ``parse_amount``'s rules; ``None`` is no slice."""
    return None if amount is None else parse_amount(amount)


def _draft(body: TaskIn, owner: str = "user") -> TaskDraft:
    """Raises ``ValueError`` (plain text) for a due date or a slice it can't read."""
    schedule = build_schedule(body.due_date, body.reminder_at, body.pre_reminders)
    return TaskDraft(title=body.title.strip(), description=body.description, category=body.category,
                     priority=body.priority, due_date=schedule.due_date, reminder_at=schedule.reminder_at,
                     pre_reminders=schedule.pre_reminders, project_id=body.project_id,
                     allocated_budget=_slice(body.allocated_budget), recurring=validate_cron(body.recurring),
                     recur_until=validate_recur_until(body.recur_until), steps=tuple(body.steps), tags=tuple(body.tags),
                     starred=body.starred, estimate_minutes=body.estimate_minutes, owner=owner)


def _patch_fields(body: TaskPatchIn) -> dict[str, Any]:
    """The fields the body set, read: a slice by the amount rules, a repeat as a cron. ``ValueError``."""
    fields = body.model_dump(include=body.model_fields_set)
    sliced = {"allocated_budget": _slice(fields["allocated_budget"])} if "allocated_budget" in fields else {}
    repeat = {"recurring": validate_cron(fields["recurring"])} if "recurring" in fields else {}
    return {**fields, **sliced, **repeat}


async def task_rows(request: Request, user_id: str, tasks: Sequence[Task],
                    sort: TaskSort | None = None) -> list[dict[str, Any]]:
    """List rows (G3): each task with its ``money``, ``due_bucket`` and ``comment_count``. Expenses, projects and
    comment counts are read once.
    ``sort="money_left"`` orders by the slice left (G6), which needs the money read here."""
    projects = {project.id: project for project in await request.app.state.money.projects(user_id)}
    ids = money_task_ids(tasks, projects)
    expenses = await ExpenseStore(request.app.state.config).for_tasks(user_id, ids) if ids else ()
    money, today = rows_money(tasks, expenses, projects), madrid_today()
    talk = await CommentStore(request.app.state.config).counts(user_id, [task.id for task in tasks])
    if sort == "money_left":
        tasks = sort_by_money_left(tasks, money)
    return [{**task_out(task), "money": row_money_out(money.get(task.id)), "due_bucket": due_bucket(task, today),
             "comment_count": talk.get(task.id, 0)} for task in tasks]


RANGE_NEEDS_BOTH_TEXT = "Give both from and to, as days like 2026-10-01."
RANGE_NOT_WITH_VIEW_TEXT = "A date range and a view cannot be asked together."
RANGE_ORDER_TEXT = "The range must end on or after the day it starts."
RANGE_LENGTH_TEXT = f"A range can cover at most {TASK_RANGE_MAX_DAYS} days."
RANGE_DAY_TEXT = "“{value}” is not a day. Use a day like 2026-10-23."


def _range_day(value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=RANGE_DAY_TEXT.format(value=value)) from None
    if day.isoformat() != value:
        raise HTTPException(status_code=422, detail=RANGE_DAY_TEXT.format(value=value))
    return day


async def _range_rows(request: Request, user_id: str, first: str | None, last: str | None, view: str | None,
                      project_id: str | None, sort: TaskSort | None):
    if first is None or last is None:
        raise HTTPException(status_code=422, detail=RANGE_NEEDS_BOTH_TEXT)
    if view is not None:
        raise HTTPException(status_code=422, detail=RANGE_NOT_WITH_VIEW_TEXT)
    start, end = _range_day(first), _range_day(last)
    if end < start:
        raise HTTPException(status_code=422, detail=RANGE_ORDER_TEXT)
    if (end - start).days + 1 > TASK_RANGE_MAX_DAYS:
        raise HTTPException(status_code=422, detail=RANGE_LENGTH_TEXT)
    tasks = await _service(request).list(user_id, status="all", **project_scope(project_id))
    today = madrid_today()
    inside = [task for task in tasks if in_range(task, start, end, today)]
    return await task_rows(request, user_id, pick(inside, None, today=today, sort=sort or "due"), sort)


TOO_MANY_IDS_TEXT = f"Ask for at most {TASK_IDS_QUERY_MAX} tasks at once."


async def _rows_by_id(request: Request, user_id: str, ids: str):
    """``ids`` (comma-separated, the chat's task cards): those of the user's tasks, any status, in the order asked;
    an id that is not one of the user's live tasks is left out, never an error."""
    wanted = tuple(dict.fromkeys(part.strip() for part in ids.split(",") if part.strip()))
    if len(wanted) > TASK_IDS_QUERY_MAX:
        raise HTTPException(status_code=422, detail=TOO_MANY_IDS_TEXT)
    by_id = {task.id: task for task in await _service(request).list(user_id, status="all")}
    return await task_rows(request, user_id, [by_id[task_id] for task_id in wanted if task_id in by_id])


@tasks_router.get("")
async def list_tasks(request: Request, user: CurrentUser, status: TaskFilter = "open",
                     project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH),
                     view: TaskView | None = None, q: str | None = Query(default=None, max_length=TASK_SEARCH_MAX_LENGTH),
                     sort: TaskSort | None = None,
                     first: Annotated[str | None, Query(alias="from")] = None,
                     last: Annotated[str | None, Query(alias="to")] = None,
                     include_finished: bool = False,
                     ids: str | None = Query(default=None, max_length=TASK_IDS_QUERY_MAX * (MAX_RECORD_ID_LENGTH + 1))):
    """``from`` and ``to`` (G11, both or neither, no ``view``) answer the tasks the calendar shows: due in the
    range, any status but cancelled, plus open overdue ones when today is in it. ``project_id`` keeps one
    project's tasks, ``none`` the tasks in no project; an empty one is no filter. ``view`` (today, upcoming,
    overdue, someday, done, board) picks a tab, ``q`` searches title and description, ``sort`` is due, priority,
    created, created_asc, title or money_left. ``include_finished`` adds done tasks to today, upcoming and
    someday when their due falls in the view; other views ignore it."""
    if ids is not None:
        return await _rows_by_id(request, user.id, ids)
    scope = project_scope(project_id)
    if first is not None or last is not None:
        return await _range_rows(request, user.id, first, last, view, project_id, sort)
    if view is None and not q and sort is None:
        return await task_rows(request, user.id, await _service(request).list(user.id, status=status, **scope))
    finished = include_finished and view in FINISHABLE_VIEWS
    status = "all" if view == "board" or finished else ("done" if view == "done" else status)
    tasks = await _service(request).list(user.id, status=status, **scope)
    chosen = pick(tasks, view, today=madrid_today(), query=q, sort=sort or "due", finished=finished)
    return await task_rows(request, user.id, chosen, sort)


async def _assignee(request: Request, user_id: str, body: TaskIn) -> Bot | None:
    """The bot to hand the task to: one of the user's, and only once the user confirmed. ``ValueError``."""
    if body.assign_bot_id is None:
        return None
    bot = await request.app.state.bots.get(user_id, body.assign_bot_id)
    if bot is None:
        raise ValueError(NO_SUCH_BOT_TEXT)
    if not body.assign_confirmed:
        raise ValueError(ASSIGN_CONFIRM_TEXT.format(name=bot.name))
    return bot


@tasks_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_task(body: TaskIn, request: Request, user: CurrentUser):
    try:
        bot = await _assignee(request, user.id, body)
        await refuse_general(request, user.id, body.project_id)
        task = await _service(request).add(user.id, _draft(body, "user" if bot is None else bot.id))
    except ValueError as exc:   # a due date or slice it can't read, General, or not one of the user's projects
        raise _unreadable(exc) from exc
    if bot is not None:
        await assign_task(request.app.state, user.id, task, bot)
    return task_out(task)


async def _slice_notice(request: Request, user_id: str, before: Task | None, after: Task,
                        body: TaskPatchIn) -> str | None:
    """Why a move cleared the task's slice, for the PATCH reply (``None`` when it did not)."""
    if before is None or before.project_id == after.project_id:
        return None
    moved_to = None if after.project_id is None else await request.app.state.projects.resolve(
        user_id, after.project_id, change=False)
    if isinstance(moved_to, ProjectRefusal):
        return None
    return slice_note(before, after, moved_to, asked="allocated_budget" in body.model_fields_set)


@tasks_router.patch("/{task_id}", dependencies=[RequireOrigin])
async def update_task(task_id: str, body: TaskPatchIn, request: Request, user: CurrentUser):
    """The changed task. A move that cleared its budget slice (another currency, or no project) adds
    ``notice`` with the reason."""
    service = _service(request)
    try:
        await refuse_general(request, user.id, body.project_id)
        before = await service.get(user.id, task_id)
        task = await service.update(user.id, task_id, patch_from_fields(_patch_fields(body)))
    except ValueError as exc:   # also General, the store's "No such project." and "A budget slice needs a project."
        raise _unreadable(exc) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    notice = await _slice_notice(request, user.id, before, task, body)
    return task_out(task) if notice is None else {**task_out(task), "notice": notice}


@tasks_router.post("/{task_id}/complete", dependencies=[RequireOrigin])
async def complete_task(task_id: str, request: Request, user: CurrentUser):
    completion = await _service(request).complete(user.id, task_id)
    if completion is None:
        raise HTTPException(status_code=404, detail=NO_OPEN_TASK_TEXT)
    return {**task_out(completion.done), "next_id": None if completion.next is None else completion.next.id}


@tasks_router.post("/{task_id}/fail", dependencies=[RequireOrigin])
async def fail_task(task_id: str, request: Request, user: CurrentUser):
    """Close an open task as failed (H11). As with complete, a recurring task
    comes back for its next time; the answer is the failed task."""
    failure = await _service(request).fail(user.id, task_id)
    if failure is None:
        raise HTTPException(status_code=404, detail=NO_OPEN_TASK_TEXT)
    return task_out(failure.done)


@tasks_router.post("/{task_id}/keep", dependencies=[RequireOrigin])
async def keep_task(task_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a task marked "from web content" — they
    are trusted here, so its taint bit is cleared (no tool can do this)."""
    task = await _service(request).keep(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_out(task)


@tasks_router.delete("/{task_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_task(task_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@tasks_router.post("/{task_id}/restore", dependencies=[RequireOrigin])
async def restore_task(task_id: str, request: Request, user: CurrentUser):
    task = await _service(request).restore(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=NO_DELETED_TASK_TEXT)
    return task_out(task)
