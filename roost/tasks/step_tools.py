"""The step tools over the user's tasks (redesign P3): ``add_step``,
``update_step``, ``delete_step`` and ``move_step``.

A task is named the way the money tools name one (``roost.money.expense_links``):
its id, its exact title or a unique part of one, among tasks of every status;
a near miss or a title several tasks share is a refusal that lists them. A
step is named the same way among its task's steps. Results are escaped, and
carry the task's taint: they echo its title and its steps."""

from __future__ import annotations

import html
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from roost.constants import MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS, MAX_TASK_TITLE_LENGTH
from roost.money.expense_links import find_step, find_task
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.tasks.models import Step, Task
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.store import StepsBusy

_ACTIVITY = {
    "add_step": "adding a step", "update_step": "changing a step", "delete_step": "deleting a step",
    "move_step": "moving a step",
}
_NEEDS = {
    "add_step": "the task (its id or title) and the step's title",
    "update_step": "the task, the step, and a new title or done (true or false)",
    "delete_step": "the task and the step (each by id or title)",
    "move_step": "the task, the step and its new place (1 is first)",
}
GONE_TEXT = "Refused: that task is gone."
NOTHING_TO_CHANGE_TEXT = "Refused: update_step needs a new title or done (true or false)."


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def steps_text(task: Task) -> str:
    """The task's steps in order, with their ids, for the model to name them next."""
    if not task.steps:
        return "It has no steps."
    lines = "; ".join(f"{'[x]' if step.done else '[ ]'} {_escape(step.title)} (id={step.id})" for step in task.steps)
    return f"Its steps: {lines}."


class AddStepArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    title: ToolText = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class StepRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText = Field(min_length=1, max_length=MAX_STEP_TITLE_LENGTH)


class UpdateStepArgs(StepRefArgs):
    title: ToolText | None = Field(default=None, max_length=MAX_STEP_TITLE_LENGTH)
    done: StrictBool | None = None


class MoveStepArgs(StepRefArgs):
    position: int = Field(ge=1, le=MAX_TASK_STEPS)


class StepTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, tasks: TaskService, steps: StepService) -> None:
        self._tasks = tasks
        self._steps = steps

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_step": self._add, "update_step": self._update, "delete_step": self._delete,
                    "move_step": self._move}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except StepsBusy as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")
        except (ValueError, LookupError) as exc:    # a title it refuses; a step gone since it was named
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddStepArgs.model_validate(arguments)
        task = await find_task(self._tasks, ctx.user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        updated = await self._steps.add(ctx.user_id, task.id, args.title, tainted=ctx.tainted)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        text = f"Added step “{_escape(updated.steps[-1].title)}” to {_escape(task.title)}. {steps_text(updated)}"
        return ToolOutcome(text, created=True, tainted=updated.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateStepArgs.model_validate(arguments)
        if args.title is None and args.done is None:
            return ToolOutcome(NOTHING_TO_CHANGE_TEXT)
        found = await self._step_of(ctx.user_id, args)
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        updated: Task | None = task
        if args.title is not None:
            updated = await self._steps.rename(ctx.user_id, task.id, step.id, args.title)
        if updated is not None and args.done is not None:
            updated = await self._steps.set_done(ctx.user_id, task.id, step.id, args.done)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        return ToolOutcome(f"Updated a step of {_escape(task.title)}. {steps_text(updated)}", tainted=updated.tainted)

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._step_of(ctx.user_id, StepRefArgs.model_validate(arguments))
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        removal = await self._steps.delete(ctx.user_id, task.id, step.id)
        if removal is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        kept = (f" {len(removal.moved_expenses)} expense(s) and {removal.moved_comments} comment(s) filed under it "
                "stay on the task." if removal.moved_expenses or removal.moved_comments else "")
        text = f"Deleted step “{_escape(step.title)}” from {_escape(task.title)}.{kept} {steps_text(removal.task)}"
        return ToolOutcome(text, tainted=task.tainted)

    async def _move(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = MoveStepArgs.model_validate(arguments)
        found = await self._step_of(ctx.user_id, args)
        if isinstance(found, ToolOutcome):
            return found
        task, step = found
        updated = await self._steps.move(ctx.user_id, task.id, step.id, args.position - 1)
        if updated is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        return ToolOutcome(f"Moved step “{_escape(step.title)}”. {steps_text(updated)}", tainted=updated.tainted)

    async def _step_of(self, user_id: str, args: StepRefArgs) -> tuple[Task, Step] | ToolOutcome:
        task = await find_task(self._tasks, user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        step = find_step(task, args.step)
        return step if isinstance(step, ToolOutcome) else (task, step)
