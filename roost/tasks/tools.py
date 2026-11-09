"""The task tools over the user's shared tasks (M1 D2, D6; projects hub H3,
H11). Argument names and meanings are LazyClaw's ``task_manager.py`` skills';
the handlers are Roost's: pydantic arguments, provenance (bot + taint) on
every new row, escaped results, a refusal sentence instead of a guess.

A task may belong to one of the user's projects, named exact-or-ask
(``roost.projects.refs``; never created here, never General), and carry a
budget slice in that project's currency. ``update_task`` with status
``failed`` closes it as failed through ``TaskService.fail``, and a repeating
task comes back, as ``complete_task`` does."""

from __future__ import annotations

import html
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_DUE_TEXT_LENGTH, MAX_PRE_REMINDERS, MAX_TASK_CATEGORY_LENGTH,
    MAX_TASK_NOTES_LENGTH, MAX_TASK_STEPS, MAX_TASK_TAGS, MAX_TASK_TITLE_LENGTH, TASK_LIST_LIMIT,
)
from roost.money.amounts import amount_text, optional_amount
from roost.money.models import Project
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.tool_text import ToolText
from roost.tags.record import bot_record_tags
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.cards import CardVerb, TaskCards
from roost.tasks.due import build_schedule, patch_from_fields, validate_recur_until
from roost.tasks.format import reminders_text, task_line, task_list_text
from roost.tasks.models import Priority, Task, TaskDraft
from roost.tasks.recurrence import validate_cron
from roost.tasks.service import Completion, TaskService
from roost.tasks.slice_note import slice_note
from roost.tasks.store import SLICE_NEEDS_PROJECT

_ACTIVITY = {
    "add_task": "adding a task", "list_tasks": "checking your tasks", "update_task": "updating a task",
    "complete_task": "completing a task", "delete_task": "deleting a task",
}
_NEEDS = {
    "add_task": "a title (and optionally due_date, category, priority, steps, project and budget)",
    "list_tasks": "an optional status (open, done, failed, all), category, project and offset",
    "update_task": "the task (its id or title) and the fields to change",
    "complete_task": "the task (its id or title)", "delete_task": "the task (its id or title)",
}
_CHANGES = frozenset({"update_task", "complete_task", "delete_task"})
_FAILED = "failed"
_Amount = str | int | float


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddTaskArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    description: ToolText | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority = "medium"
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)
    recurring: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    recur_until: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    steps: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_STEPS)
    tags: list[ToolText] = Field(default_factory=list, max_length=MAX_TASK_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    budget: _Amount | None = None


class ListTasksArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["open", "done", "failed", "all"] = "open"
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    offset: int = Field(default=0, ge=0)


class TaskRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)


class UpdateTaskArgs(TaskRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    description: ToolText | None = Field(default=None, max_length=MAX_TASK_NOTES_LENGTH)
    category: ToolText | None = Field(default=None, max_length=MAX_TASK_CATEGORY_LENGTH)
    priority: Priority | None = None
    status: Literal["todo", "in_progress", "cancelled", "failed"] | None = None
    due_date: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    reminder_at: str | None = Field(default=None, max_length=MAX_DUE_TEXT_LENGTH)
    pre_reminders: list[str] | None = Field(default=None, max_length=MAX_PRE_REMINDERS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)
    budget: _Amount | None = None


def _in_category(tasks: tuple[Task, ...], category: str | None) -> tuple[Task, ...]:
    if not category:
        return tasks
    wanted = category.strip().casefold()
    return tuple(task for task in tasks if (task.category or "").casefold() == wanted)


def _update_fields(args: UpdateTaskArgs, project: Project | None) -> dict[str, Any]:
    """The fields the call set. '' clears the due date, the project and the
    budget slice; a null leaves the project and the slice as they are."""
    fields = args.model_dump(include=args.model_fields_set - {"task", "project", "budget"})
    due = {"due_date": None} if fields.get("due_date") == "" else {}
    linked = {"project_id": id_of(project)} if args.project is not None else {}
    sliced = {"allocated_budget": optional_amount(args.budget)} if args.budget is not None else {}
    return {**fields, **due, **linked, **sliced}


def _bot_slice_rule(project_id: str | None, fields: dict[str, Any]) -> None:
    """A bot still gives a task a budget slice only inside a project (H11); the user's own drawer may set
    one on any task (owner, 2026-10-26). ``ValueError`` (a refusal), nothing written."""
    if project_id is None and fields.get("allocated_budget") is not None:
        raise ValueError(SLICE_NEEDS_PROJECT)


def _filed(project: Project | None, task: Task, *, unlinked: bool = False) -> str:
    """The reply's end: the task's project and, when it has one, its budget slice."""
    if project is None or task.allocated_budget is None:
        return project_suffix(project, unlinked=unlinked)
    return (f" Project: “{_escape(project.name)}”, budget {amount_text(task.allocated_budget)} "
            f"{project.currency}.")


def _closing(verb: str, task: Task, closing: Completion | None) -> ToolOutcome:
    """complete_task's reply, and a failed update's: a repeating task's next time is shown."""
    if closing is None:
        return ToolOutcome(f"Refused: {_escape(task.title)} is not open any more.", tainted=task.tainted)
    following = f" Next time: {task_line(closing.next)}" if closing.next is not None else ""
    return ToolOutcome(f"{verb}: {_escape(task.title)}.{following}", tainted=task.tainted)


class TaskTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: TaskService, projects: ProjectService, cards: TaskCards | None = None) -> None:
        self._service = service
        self._projects = projects
        self._cards = cards   # None: no task cards in the chat

    async def finish_run(self, user_id: str, bot_id: str, run_id: str | None) -> None:
        """The run ended: its task cards line goes under the bot's reply."""
        if self._cards is not None:
            await self._cards.finish_run(user_id, bot_id, run_id)

    async def _show(self, ctx: RecordContext, task_ids: tuple[str, ...], verb: CardVerb, more: int = 0) -> None:
        if self._cards is None:
            return
        if ctx.run_id is None:
            await self._cards.note_now(ctx, task_ids, verb, more=more)
        else:
            self._cards.note(ctx, task_ids, verb, more=more)

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_task": self._add, "list_tasks": self._list, "update_task": self._update,
                    "complete_task": self._complete, "delete_task": self._delete}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddTaskArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        schedule = build_schedule(args.due_date, args.reminder_at, args.pre_reminders)
        draft = TaskDraft(
            title=args.title.strip(), description=args.description, category=args.category, priority=args.priority,
            due_date=schedule.due_date, reminder_at=schedule.reminder_at, pre_reminders=schedule.pre_reminders,
            recurring=validate_cron(args.recurring), recur_until=validate_recur_until(args.recur_until),
            tags=bot_record_tags(ctx, None if project is None else project.name, args.tags),
            steps=tuple(args.steps), project_id=id_of(project),
            allocated_budget=optional_amount(args.budget),
        )
        _bot_slice_rule(draft.project_id, {"allocated_budget": draft.allocated_budget})
        task = await self._service.add(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        await self._show(ctx, (task.id,), "added")
        return ToolOutcome(f"Added: {task_line(task)}{reminders_text(task)}{_filed(project, task)}", created=True,
                           tainted=project_taint(project))

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = ListTasksArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        tasks = await self._service.list(ctx.user_id, status=args.status, project_id=id_of(project))
        matching = _in_category(tasks, args.category)
        shown = matching[args.offset:args.offset + TASK_LIST_LIMIT]
        await self._show(ctx, tuple(task.id for task in shown), "listed", len(matching) - args.offset - len(shown))
        return ToolOutcome(task_list_text(shown, len(matching), args.offset), tainted=any(task.tainted for task in shown))

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateTaskArgs.model_validate(arguments)
        found = await self._find(ctx.user_id, args.task)
        if isinstance(found, ToolOutcome):
            return found
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        fields = _update_fields(args, project)
        _bot_slice_rule(fields.get("project_id", found.project_id), fields)
        failing = fields.get("status") == _FAILED
        rest = {name: value for name, value in fields.items() if not (failing and name == "status")}
        task = found if failing and not rest else await self._service.update(
            ctx.user_id, found.id, patch_from_fields(rest))
        if task is None:
            return ToolOutcome("Refused: that task is gone.", tainted=found.tainted)
        if failing:
            return _closing("Failed", task, await self._service.fail(ctx.user_id, task.id))
        filed = _filed(project, task, unlinked=args.project is not None)
        cleared = slice_note(found, task, project, asked="allocated_budget" in fields)
        said = f" {_escape(cleared)}" if cleared else ""
        return ToolOutcome(f"Updated: {task_line(task)}{reminders_text(task)}{filed}{said}", tainted=found.tainted or project_taint(project))

    async def _complete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, TaskRefArgs.model_validate(arguments).task)
        if isinstance(found, ToolOutcome):
            return found
        return _closing("Completed", found, await self._service.complete(ctx.user_id, found.id))

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find(ctx.user_id, TaskRefArgs.model_validate(arguments).task)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.id)
        return ToolOutcome(f"Deleted: {_escape(found.title)}.", tainted=found.tainted)

    async def target_title(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> str | None:
        """The change check: the stored title of the open task a change names, or ``None``."""
        if name not in _CHANGES:
            return None
        try:
            found = await self._find(ctx.user_id, TaskRefArgs.model_validate(arguments).task)
        except ValidationError:
            return None
        return None if isinstance(found, ToolOutcome) else found.title

    async def _find(self, user_id: str, ref: str) -> Task | ToolOutcome:
        """The open task a change targets: its id, its exact title or a
        single substring hit (harvested resolver) — never a guess. Every tool
        calling this is a ``write_change``, so a lone fuzzy hit ("call mom"
        vs "Call tom") is a "did you mean" refusal, not a silent change to the
        wrong task. Both refusals show titles to the model, so they carry
        those tasks' taint (D3): a web-derived title among them taints the
        run before it can change anything."""
        tasks = await self._service.list(user_id, status="open")
        by_id = next((task for task in tasks if task.id == ref.strip()), None)
        if by_id is not None:
            return by_id
        by_key = {task.id: task for task in tasks}
        hit = resolve(ref, [NamedRef(task.id, task.title) for task in tasks])
        if hit.resolved is not None and hit.reason != "fuzzy":
            return by_key[hit.resolved.id]
        shown = tuple(by_key[c.id] for c in hit.candidates[:5])
        tainted = any(t.tainted for t in shown)
        if hit.reason == "fuzzy":
            return ToolOutcome(f"Refused: no open task is called “{_escape(ref)}”. Did you mean "
                               f"“{_titles(shown)}”? Say it exactly.", tainted=tainted)
        if hit.reason == "multi":
            return ToolOutcome(f"Refused: several open tasks match “{_escape(ref)}”: {_titles(shown)}. Say which one.",
                               tainted=tainted)
        return ToolOutcome(f"Refused: no open task matches “{_escape(ref)}”.")


def _titles(tasks: tuple[Task, ...]) -> str:
    """Escaped titles for a refusal, each web-made one marked as such."""
    return "; ".join(_escape(t.title) + (" [from web content]" if t.tainted else "") for t in tasks)
