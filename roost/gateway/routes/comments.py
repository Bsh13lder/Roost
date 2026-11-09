"""Comments over HTTP (redesign P3): a task's thread, and the user's own comments.

- ``GET`` / ``POST /api/tasks/{id}/comments``: the thread, oldest first, and a new comment by the user
  (``step_id`` puts it on one of the task's steps).
- ``PATCH`` / ``DELETE /api/comments/{id}``: only the user's own comments; a bot's is 403.
- Another user's task or comment, or one that is gone: 404. A body or step it refuses: 422.
The same ``CommentService`` as the bots' tools, so every change publishes ``tasks_changed``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from roost.constants import MAX_COMMENT_LENGTH, MAX_RECORD_ID_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.tasks.comment_service import CommentNotYours, CommentService
from roost.tasks.comments import comment_out

comments_router = APIRouter(tags=["comments"])
TASK_NOT_FOUND_TEXT = "Task not found"
COMMENT_NOT_FOUND_TEXT = "Comment not found"


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)
    step_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)


class CommentPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)


def _service(request: Request) -> CommentService:
    return request.app.state.comments


@comments_router.get("/api/tasks/{task_id}/comments")
async def list_comments(task_id: str, request: Request, user: CurrentUser) -> list[dict[str, Any]]:
    comments = await _service(request).list(user.id, task_id)
    if comments is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return [comment_out(comment) for comment in comments]


@comments_router.post("/api/tasks/{task_id}/comments", status_code=201, dependencies=[RequireOrigin])
async def add_comment(task_id: str, body: CommentIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        comment = await _service(request).add(user.id, task_id, body.body, step_id=body.step_id)
    except ValueError as exc:   # an empty body after trimming, or a step the task doesn't have
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if comment is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND_TEXT)
    return comment_out(comment)


@comments_router.patch("/api/comments/{comment_id}", dependencies=[RequireOrigin])
async def edit_comment(comment_id: str, body: CommentPatchIn, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        comment = await _service(request).edit(user.id, comment_id, body.body)
    except CommentNotYours as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if comment is None:
        raise HTTPException(status_code=404, detail=COMMENT_NOT_FOUND_TEXT)
    return comment_out(comment)


@comments_router.delete("/api/comments/{comment_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_comment(comment_id: str, request: Request, user: CurrentUser) -> None:
    try:
        deleted = await _service(request).delete(user.id, comment_id)
    except CommentNotYours as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=COMMENT_NOT_FOUND_TEXT)
