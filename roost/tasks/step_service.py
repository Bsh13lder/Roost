"""``StepService`` — a task's checklist, one change at a time (redesign P3).

The tools and the HTTP routes both go through it. Every change is applied to
the task's current steps in a compare-and-set (``TaskStore.edit_steps``) and
publishes ``tasks_changed``. Deleting a step keeps what was filed under it on
the task: its expenses lose their ``step_id`` (each publishes
``money_changed``) and so do its comments.

``None`` means no live task of the user's (a 404). ``StepNotFound``: the task
has no such step (a 404). ``ValueError``: a title or a change it refuses (a
422). ``StepsBusy``: too many changes at once (a 409)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from roost.events.hub import EventHub
from roost.money.expense_store import ExpenseStore
from roost.tasks.comment_store import CommentStore
from roost.tasks.models import Task
from roost.tasks.service import publish_task_change
from roost.tasks.steps import (
    with_step_added, with_step_budget, with_step_done, with_step_moved, with_step_renamed, without_step,
)
from roost.tasks.store import TaskStore

NO_CURRENCY_TEXT = "This task's project can't be read, so its steps can't get a budget now."


@dataclass(frozen=True)
class StepRemoval:
    task: Task
    moved_expenses: tuple[str, ...]   # the expenses now filed under the whole task
    moved_comments: int


class StepService:
    def __init__(self, tasks: TaskStore, expenses: ExpenseStore, comments: CommentStore, events: EventHub) -> None:
        self._tasks = tasks
        self._expenses = expenses
        self._comments = comments
        self._events = events

    async def add(self, user_id: str, task_id: str, title: str, *, tainted: bool = False) -> Task | None:
        """A new open step at the end. ``tainted``: a run that read outside content added it, so the
        task now holds web text and is marked so (a step has no taint bit of its own)."""
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_added(steps, title),
                                            taint=tainted)
        return await self._changed(user_id, task)

    async def rename(self, user_id: str, task_id: str, step_id: str, title: str) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_renamed(steps, step_id, title))
        return await self._changed(user_id, task)

    async def set_done(self, user_id: str, task_id: str, step_id: str, done: bool) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: with_step_done(steps, step_id, done))
        return await self._changed(user_id, task)

    async def move(self, user_id: str, task_id: str, step_id: str, position: int) -> Task | None:
        task = await self._tasks.edit_steps(user_id, task_id,
                                            lambda steps: with_step_moved(steps, step_id, position))
        return await self._changed(user_id, task)

    async def set_budget(self, user_id: str, task_id: str, step_id: str, amount: Decimal | None) -> Task | None:
        """A step's own budget in the task's currency (its project's, or General's), or ``None`` to clear it
        (owner, 2026-10-26). ``ValueError``: an amount it refuses, or a project that can no longer be read."""
        task = await self._tasks.get(user_id, task_id)
        if task is None:
            return None
        currency = await self._tasks.money_currency(user_id, task)
        if currency is None:
            raise ValueError(NO_CURRENCY_TEXT)
        changed = await self._tasks.edit_steps(
            user_id, task_id, lambda steps: with_step_budget(steps, step_id, amount, currency))
        return await self._changed(user_id, changed)

    async def delete(self, user_id: str, task_id: str, step_id: str) -> StepRemoval | None:
        task = await self._tasks.edit_steps(user_id, task_id, lambda steps: without_step(steps, step_id))
        if task is None:
            return None
        moved = await self._expenses.unlink_step(user_id, task_id, step_id)
        comments = await self._comments.unlink_step(user_id, task_id, step_id)
        await self._changed(user_id, task)
        for expense_id in moved:
            await self._events.publish(user_id, {"type": "money_changed", "change": "expense_updated", "id": expense_id})
        return StepRemoval(task=task, moved_expenses=moved, moved_comments=comments)

    async def _changed(self, user_id: str, task: Task | None) -> Task | None:
        if task is not None:
            await publish_task_change(self._events, user_id, "updated", task.id)
        return task
