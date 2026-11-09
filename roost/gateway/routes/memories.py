"""What I remember over HTTP: the Profile's memory panel. The same ``MemoryService`` the bots' tools use, so
every change publishes ``memories_changed``.

Another user's memory or bot is a 404 (a path or query id) or a 422 "No such bot." (a body id): never the
other user's text. A web add or edit is the user's own word: ``source='user'`` and never tainted."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import (
    MAX_RECORD_ID_LENGTH, MEMORY_IMPORTANCE_DEFAULT, MEMORY_IMPORTANCE_MAX, MEMORY_IMPORTANCE_MIN,
    MEMORY_TEXT_MAX_CHARS,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.memory.models import MemoryDraft, MemoryKind, memory_out
from roost.memory.service import MemoryDuplicate, MemoryPatch, MemoryRefused, MemoryService

memories_router = APIRouter(prefix="/api/memories", tags=["memories"])
MEMORY_NOT_FOUND_TEXT = "Memory not found"
NO_SUCH_BOT_TEXT = "No such bot."
EMPTY_PATCH_TEXT = "Say what to change."


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MEMORY_TEXT_MAX_CHARS)
    kind: MemoryKind
    bot_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)
    importance: int = Field(default=MEMORY_IMPORTANCE_DEFAULT, ge=MEMORY_IMPORTANCE_MIN, le=MEMORY_IMPORTANCE_MAX)
    pinned: bool = False


class MemoryPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=MEMORY_TEXT_MAX_CHARS)
    kind: MemoryKind | None = None
    importance: int | None = Field(default=None, ge=MEMORY_IMPORTANCE_MIN, le=MEMORY_IMPORTANCE_MAX)
    pinned: bool | None = None
    restore: Literal[True] | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "MemoryPatchIn":
        if all(value is None for value in self.model_dump().values()):
            raise ValueError(EMPTY_PATCH_TEXT)
        return self


def _service(request: Request) -> MemoryService:
    return request.app.state.memories


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail=MEMORY_NOT_FOUND_TEXT)


@memories_router.get("")
async def list_memories(request: Request, user: CurrentUser,
                        bot_id: str = Query(max_length=MAX_RECORD_ID_LENGTH), faded: bool = False,
                        kind: MemoryKind | None = None):
    """About you and this bot's memories, pinned first then newest; ``faded`` adds the archived ones and
    ``kind`` keeps one kind."""
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return [memory_out(m) for m in await _service(request).list_for_bot(user.id, bot_id, faded=faded, kind=kind)]


@memories_router.post("", status_code=201, dependencies=[RequireOrigin])
async def add_memory(body: MemoryIn, request: Request, user: CurrentUser):
    bot_id = body.bot_id if body.kind != "about_you" else None
    if bot_id is not None and await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=422, detail=NO_SUCH_BOT_TEXT)
    draft = MemoryDraft(kind=body.kind, text=body.text, bot_id=bot_id, source="user", created_by_bot=None,
                        importance=body.importance, pinned=body.pinned, tainted=False)
    try:
        result = await _service(request).save(user.id, draft)
    except MemoryRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return memory_out(result.memory)


@memories_router.patch("/{memory_id}", dependencies=[RequireOrigin])
async def edit_memory(memory_id: str, body: MemoryPatchIn, request: Request, user: CurrentUser):
    patch = MemoryPatch(text=body.text, kind=body.kind, importance=body.importance, pinned=body.pinned,
                        restore=body.restore)
    try:
        memory = await _service(request).edit(user.id, memory_id, patch)
    except MemoryDuplicate as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MemoryRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if memory is None:
        raise _missing()
    return memory_out(memory)


@memories_router.delete("/{memory_id}", status_code=204, dependencies=[RequireOrigin])
async def forget_memory(memory_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).forget(user.id, memory_id):
        raise _missing()
