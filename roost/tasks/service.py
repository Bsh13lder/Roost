"""``TaskService`` — the tasks store plus its live frame (M1 D8) and the
recurring respawn (harvested logic in ``recurrence``). Tools and HTTP routes
both go through it, so the Board updates whoever changed a task."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal, Sequence

from roost.events.hub import EventHub
from roost.tasks.models import DueSet, Task, TaskDraft, TaskFilter, TaskPatch
from roost.tasks.recurrence import next_occurrence_fields, series_ended
from roost.tasks.store import TaskStore

logger = logging.getLogger(__name__)

# "commented" (redesign P3): a comment on the task was added, edited or deleted.
TaskChange = Literal["created", "updated", "completed", "failed", "deleted", "restored", "commented"]


@dataclass(frozen=True)
class Completion:
    done: Task
    next: Task | None


def _shifted(done: Task, reminder_at: str | None) -> tuple[str, ...]:
    """The completed task's advance reminders, moved with its reminder."""
    if not (done.reminder_at and reminder_at and done.pre_reminders):
        return ()
    old, new = datetime.fromisoformat(done.reminder_at), datetime.fromisoformat(reminder_at)
    return tuple(sorted(
        (new - (old - datetime.fromisoformat(pre))).astimezone(timezone.utc).isoformat() for pre in done.pre_reminders
    ))


def respawn_draft(done: Task, due_date: str | None, reminder_at: str | None) -> TaskDraft:
    """The next occurrence of a closed (done or failed) recurring task. It stays
    in the same project with the same budget slice, star and estimate (a task in no project keeps its
    slice too, in General's currency; owner 2026-10-26)."""
    return TaskDraft(
        title=done.title, description=done.description, category=done.category, priority=done.priority,
        owner=done.owner, due_date=due_date, reminder_at=reminder_at, pre_reminders=_shifted(done, reminder_at),
        recurring=done.recurring, recur_until=done.recur_until, tags=done.tags,
        steps=tuple(step.title for step in done.steps), project_id=done.project_id,
        allocated_budget=done.allocated_budget,
        starred=done.starred, estimate_minutes=done.estimate_minutes,
    )


class TaskService:
    def __init__(self, store: TaskStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def list(self, user_id: str, *, status: TaskFilter = "open",
                   project_id: str | None = None, no_project: bool = False) -> tuple[Task, ...]:
        return await self._store.list(user_id, status=status, project_id=project_id, no_project=no_project)

    async def get(self, user_id: str, task_id: str) -> Task | None:
        return await self._store.get(user_id, task_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Task, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def add(self, user_id: str, draft: TaskDraft, *, created_by_bot: str | None = None,
                  tainted: bool = False, client_id: str | None = None) -> Task:
        task = await self._store.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted,
                                        client_id=client_id)
        await self._changed(user_id, "created", task.id)
        return task

    async def by_client_id(self, user_id: str, client_id: str) -> Task | None:
        return await self._store.find_by_client_id(user_id, client_id)

    async def update(self, user_id: str, task_id: str, patch: TaskPatch) -> Task | None:
        task = await self._store.update(user_id, task_id, patch)
        if task is not None:
            await self._changed(user_id, "updated", task.id)
        return task

    async def complete(self, user_id: str, task_id: str) -> Completion | None:
        done = await self._store.complete(user_id, task_id)
        if done is None:
            return None
        await self._changed(user_id, "completed", done.id)
        return Completion(done=done, next=await self._respawn(user_id, done) if done.recurring else None)

    async def fail(self, user_id: str, task_id: str) -> Completion | None:
        """Close an open task as failed (H11). As with ``complete``, a
        recurring task comes back for its next time; ``Completion.done`` holds
        the failed task. ``None`` when there is no open task with that id."""
        failed = await self._store.fail(user_id, task_id)
        if failed is None:
            return None
        await self._changed(user_id, "failed", failed.id)
        return Completion(done=failed, next=await self._respawn(user_id, failed) if failed.recurring else None)

    async def reopen(self, user_id: str, task_id: str) -> Task | None:
        """Open a done or failed task again. ``None`` when there is no closed task of the user's with that id."""
        task = await self._store.reopen(user_id, task_id)
        if task is not None:
            await self._changed(user_id, "updated", task.id)
        return task

    async def move_dues(self, user_id: str, items: Sequence[DueSet]) -> tuple[DueSet, ...] | None:
        """Set many tasks' schedules in one transaction, all or none. Returns the values before (what an Undo
        sends back), or ``None`` when one id is not the user's live task (nothing was written)."""
        before = await self._store.set_dues(user_id, items)
        if before is not None:
            for item in items:
                await self._changed(user_id, "updated", item.id)
        return before

    async def keep(self, user_id: str, task_id: str) -> Task | None:
        """The user vouches for a web-made task (HTTP only, never a tool)."""
        task = await self._store.keep(user_id, task_id)
        if task is not None:
            await self._changed(user_id, "updated", task.id)
        return task

    async def delete(self, user_id: str, task_id: str) -> bool:
        deleted = await self._store.delete(user_id, task_id)
        if deleted:
            await self._changed(user_id, "deleted", task_id)
        return deleted

    async def restore(self, user_id: str, task_id: str) -> Task | None:
        """Delete's Undo (HTTP only): the same task comes back, or ``None`` when it isn't the user's deleted task."""
        task = await self._store.restore(user_id, task_id)
        if task is not None:
            await self._changed(user_id, "restored", task.id)
        return task

    async def _respawn(self, user_id: str, done: Task) -> Task | None:
        """The next occurrence keeps the series' creator, its taint and its project."""
        try:
            due_date, reminder_at = next_occurrence_fields(
                done.recurring, orig_due=done.due_date, orig_reminder=done.reminder_at,
            )
        except (ValueError, RuntimeError):
            logger.warning("Could not compute the next occurrence of task %s", done.id, exc_info=True)
            return None
        if due_date is None or series_ended(done.recur_until, due_date, reminder_at):
            return None
        return await self._add_next(user_id, done, respawn_draft(done, due_date, reminder_at))

    async def _add_next(self, user_id: str, done: Task, draft: TaskDraft) -> Task:
        """A project deleted between the close and this respawn refuses the
        link ("No such project."). The series goes on, unlinked, and the log
        says so, instead of the close failing after its write."""
        try:
            return await self.add(user_id, draft, created_by_bot=done.created_by_bot, tainted=done.tainted)
        except ValueError as exc:
            if draft.project_id is None:
                raise
            logger.warning("The next occurrence of task %s was refused (%s); it comes back without its project",
                           done.id, exc)
            return await self.add(user_id, replace(draft, project_id=None, allocated_budget=None),
                                  created_by_bot=done.created_by_bot, tainted=done.tainted)

    async def _changed(self, user_id: str, change: TaskChange, task_id: str) -> None:
        await publish_task_change(self._events, user_id, change, task_id)


async def publish_task_change(events: EventHub, user_id: str, change: TaskChange, task_id: str) -> None:
    """The one ``tasks_changed`` frame (M1 D8): the task, steps and comment services all send it."""
    await events.publish(user_id, {"type": "tasks_changed", "change": change, "task_id": task_id})
