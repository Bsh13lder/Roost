"""A comment on a task or on one of its steps (redesign P3).

A comment is the user's ("user") or a bot's (its id). Its body is ``enc:v2``
under ``task_comments:body``; a bot's comment written after reading outside
content carries the taint bit, like every record (M1 D3). Only the user's
own comments can be edited or deleted, and only over HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.constants import MAX_COMMENT_LENGTH

COMMENT_BY_USER = "user"
EMPTY_COMMENT_TEXT = "A comment needs some words."
LONG_COMMENT_TEXT = f"A comment holds at most {MAX_COMMENT_LENGTH} characters."


@dataclass(frozen=True)
class TaskComment:
    id: str
    user_id: str
    task_id: str
    step_id: str | None      # one of the task's steps; None: the whole task
    author: str              # "user", or the bot's id
    body: str
    tainted: bool
    created_at: str
    edited_at: str | None

    @property
    def by_user(self) -> bool:
        return self.author == COMMENT_BY_USER


def comment_body(text: str | None) -> str:
    """The trimmed body, or a ``ValueError`` with a plain sentence."""
    body = (text or "").strip()
    if not body:
        raise ValueError(EMPTY_COMMENT_TEXT)
    if len(body) > MAX_COMMENT_LENGTH:
        raise ValueError(LONG_COMMENT_TEXT)
    return body


def comment_out(comment: TaskComment) -> dict[str, Any]:
    """``CommentOut``, the web's shape."""
    return {
        "id": comment.id, "task_id": comment.task_id, "step_id": comment.step_id, "author": comment.author,
        "body": comment.body, "tainted": comment.tainted, "created_at": comment.created_at,
        "edited_at": comment.edited_at,
    }
