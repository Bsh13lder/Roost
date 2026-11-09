"""The comment tools (redesign P3): ``add_comment`` and ``list_comments``.

A bot's comment records the bot as its author and the run's taint, like every
record a bot writes (M1 D3). Listing shows each comment's author ("the user",
"you" for this bot, or another bot by id) and marks a web-made one; the
result carries the taint of the task and of every comment it shows."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import COMMENT_TOOL_LIMIT, MAX_COMMENT_LENGTH, MAX_STEP_TITLE_LENGTH, MAX_TASK_TITLE_LENGTH
from roost.money.expense_links import find_step, find_task
from roost.records.tool_text import ToolText
from roost.talk.domain_tools import RecordContext
from roost.timezones import local_tz
from roost.talk.outcome import ToolOutcome
from roost.tasks.comment_service import CommentService
from roost.tasks.comments import TaskComment
from roost.tasks.models import Task
from roost.tasks.service import TaskService

_ACTIVITY = {"add_comment": "adding a comment", "list_comments": "reading comments"}
_NEEDS = {
    "add_comment": "the task (its id or title), the text, and optionally the step",
    "list_comments": "the task (its id or title)",
}
GONE_TEXT = "Refused: that task is gone."
_WEB_MARK = " [from web content]"


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddCommentArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)
    step: ToolText | None = Field(default=None, max_length=MAX_STEP_TITLE_LENGTH)
    text: ToolText = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)


class ListCommentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: ToolText = Field(min_length=1, max_length=MAX_TASK_TITLE_LENGTH)


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(local_tz()).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _comment_line(comment: TaskComment, task: Task, bot_id: str) -> str:
    author = "the user" if comment.by_user else "you" if comment.author == bot_id else f"bot {comment.author}"
    steps = {step.id: step.title for step in task.steps}
    about = f" on step “{_escape(steps[comment.step_id])}”" if comment.step_id in steps else ""
    mark = _WEB_MARK if comment.tainted else ""
    return f"[{_when(comment.created_at)}] {author}{about}: {_escape(comment.body)}{mark}"


class CommentTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, tasks: TaskService, comments: CommentService) -> None:
        self._tasks = tasks
        self._comments = comments

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_comment": self._add, "list_comments": self._list}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddCommentArgs.model_validate(arguments)
        task = await find_task(self._tasks, ctx.user_id, args.task)
        if isinstance(task, ToolOutcome):
            return task
        step = None if args.step is None or not args.step.strip() else find_step(task, args.step)
        if isinstance(step, ToolOutcome):
            return step
        comment = await self._comments.add(ctx.user_id, task.id, args.text, step_id=None if step is None else step.id,
                                           author=ctx.bot_id, tainted=ctx.tainted)
        if comment is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        about = "" if step is None else f" on step “{_escape(step.title)}”"
        return ToolOutcome(f"Commented on {_escape(task.title)}{about}.", created=True, tainted=task.tainted)

    async def _list(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        task = await find_task(self._tasks, ctx.user_id, ListCommentsArgs.model_validate(arguments).task)
        if isinstance(task, ToolOutcome):
            return task
        shown = await self._comments.list(ctx.user_id, task.id, limit=COMMENT_TOOL_LIMIT)
        if shown is None:
            return ToolOutcome(GONE_TEXT, tainted=task.tainted)
        if not shown:
            return ToolOutcome(f"{_escape(task.title)} has no comments.", tainted=task.tainted)
        lines = "\n".join(_comment_line(comment, task, ctx.bot_id) for comment in shown)
        tainted = task.tainted or any(comment.tainted for comment in shown)
        return ToolOutcome(f"Comments on {_escape(task.title)}:\n{lines}", tainted=tainted)
