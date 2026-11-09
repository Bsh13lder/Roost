"""``CommentService`` — comments on a task or a step, plus their live frame
(redesign P3). The tools and the HTTP routes both go through it, so every
change publishes ``tasks_changed`` with ``change: "commented"``.

- A comment's step must be one of its task's steps (``ValueError``).
- Only the user's own comments can be edited or deleted: a bot's comment
  raises ``CommentNotYours``, which the routes answer 403.
- ``None`` everywhere means "no such task or comment of this user's" (a 404)."""

from __future__ import annotations

from roost.constants import COMMENT_LIST_LIMIT
from roost.events.hub import EventHub
from roost.tasks.comment_store import CommentStore
from roost.tasks.comments import COMMENT_BY_USER, TaskComment, comment_body
from roost.tasks.models import STEP_NOT_FOUND_TEXT
from roost.tasks.service import publish_task_change
from roost.tasks.store import TaskStore

NOT_YOURS_TEXT = "Only your own comments can be changed."


class CommentNotYours(PermissionError):
    """A bot's comment: the user may read it, never edit or delete it."""


class CommentService:
    def __init__(self, comments: CommentStore, tasks: TaskStore, events: EventHub) -> None:
        self._comments = comments
        self._tasks = tasks
        self._events = events

    async def list(self, user_id: str, task_id: str, *, limit: int = COMMENT_LIST_LIMIT,
                   ) -> tuple[TaskComment, ...] | None:
        if await self._tasks.get(user_id, task_id) is None:
            return None
        return await self._comments.list(user_id, task_id, limit=limit)

    async def add(self, user_id: str, task_id: str, body: str, *, step_id: str | None = None,
                  author: str = COMMENT_BY_USER, tainted: bool = False) -> TaskComment | None:
        text = comment_body(body)
        task = await self._tasks.get(user_id, task_id)
        if task is None:
            return None
        if step_id is not None and step_id not in {step.id for step in task.steps}:
            raise ValueError(STEP_NOT_FOUND_TEXT)
        comment = await self._comments.add(user_id, task_id, step_id=step_id, author=author, body=text,
                                           tainted=tainted)
        if comment is not None:
            await publish_task_change(self._events, user_id, "commented", task_id)
        return comment

    async def edit(self, user_id: str, comment_id: str, body: str) -> TaskComment | None:
        text = comment_body(body)
        current = await self._own(user_id, comment_id)
        if current is None:
            return None
        edited = await self._comments.edit(user_id, comment_id, text)
        if edited is not None:
            await publish_task_change(self._events, user_id, "commented", edited.task_id)
        return edited

    async def delete(self, user_id: str, comment_id: str) -> bool:
        current = await self._own(user_id, comment_id)
        if current is None or not await self._comments.delete(user_id, comment_id):
            return False
        await publish_task_change(self._events, user_id, "commented", current.task_id)
        return True

    async def _own(self, user_id: str, comment_id: str) -> TaskComment | None:
        current = await self._comments.get(user_id, comment_id)
        if current is not None and not current.by_user:
            raise CommentNotYours(NOT_YOURS_TEXT)
        return current
