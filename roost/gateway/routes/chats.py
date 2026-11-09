"""Home's chats.

- ``GET /api/chats``: the chat list (S1.4).
- ``GET /api/chats/search?q=``: words in every chat's messages, ``{"results": [{chat_kind, chat_id, name, thread_id,
  message_id, from_you, snippet, created_at, tainted}]}``, best match first (``roost/talk/text_search.py``)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from roost.constants import CHAT_TEXT_SEARCH_QUERY_MAX
from roost.gateway.deps import CurrentUser
from roost.talk.chats import chat_rows
from roost.talk.text_search import search_chats

chats_router = APIRouter(prefix="/api", tags=["chats"])


@chats_router.get("/chats")
async def list_chats(request: Request, user: CurrentUser):
    state = request.app.state
    return await chat_rows(user_id=user.id, bots=state.bots, talk=state.talk, rooms=state.rooms)


@chats_router.get("/chats/search")
async def search_chat_text(
    request: Request, user: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=CHAT_TEXT_SEARCH_QUERY_MAX)],
) -> dict[str, list[dict[str, Any]]]:
    state = request.app.state
    return {"results": await search_chats(user.id, q, bots=state.bots, talk=state.talk, rooms=state.rooms)}
