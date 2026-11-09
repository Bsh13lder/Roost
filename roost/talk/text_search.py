"""Chat text search for Home (``GET /api/chats/search``): the ``search_chat`` tool's matching, across every chat.

Every query word must appear (accents and case folded), the best match first, then the newest. The scan covers the
user's bot chats and rooms (not routine run logs, not cards), at most ``CHAT_SEARCH_SCAN_LIMIT`` of the newest
messages. Bodies are decrypted server-side for their owner only: every read is scoped by ``user_id``. A snippet is
plain text (the client draws it as text, never as HTML); a reply that read web content keeps its ``tainted`` mark."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.bots.store import BotStore
from roost.constants import CHAT_SEARCH_SCAN_LIMIT, CHAT_TEXT_SEARCH_RESULTS_MAX
from roost.memory.chat_search import flatten, match_score, raw_snippet
from roost.notes.search import query_terms
from roost.notes.text import fold
from roost.rooms.store import RoomStore
from roost.talk.store import Message, TalkStore


@dataclass(frozen=True)
class ChatName:
    kind: str       # "bot" or "room", as in ``GET /api/chats``
    id: str
    name: str


@dataclass(frozen=True)
class _Scored:
    score: int
    message: Message
    chat: ChatName
    snippet: str


async def _chat_names(
    user_id: str, bots: BotStore, rooms: RoomStore,
) -> tuple[dict[str, ChatName], dict[str, ChatName]]:
    """(by room thread id, by bot id): the chat row a message belongs to."""
    by_thread = {room.thread_id: ChatName("room", room.id, room.name) for room in await rooms.list(user_id)}
    by_bot = {bot.id: ChatName("bot", bot.id, bot.name) for bot in await bots.list(user_id)}
    return by_thread, by_bot


def _scored(message: Message, chat: ChatName, terms: tuple[str, ...]) -> _Scored | None:
    body = flatten(message.body)
    folded = fold(body)
    score = match_score(folded, terms)
    return _Scored(score, message, chat, raw_snippet(body, folded, terms)) if score > 0 else None


def _out(hit: _Scored) -> dict[str, Any]:
    message = hit.message
    return {
        "chat_kind": hit.chat.kind, "chat_id": hit.chat.id, "name": hit.chat.name, "thread_id": message.thread_id,
        "message_id": message.id, "from_you": message.role == "user" and message.author_bot_id is None,
        "snippet": hit.snippet, "created_at": message.created_at, "tainted": message.tainted,
    }


async def search_chats(user_id: str, query: str, *, bots: BotStore, talk: TalkStore,
                       rooms: RoomStore) -> list[dict[str, Any]]:
    """The user's hits for ``query``, best first, at most ``CHAT_TEXT_SEARCH_RESULTS_MAX``."""
    terms = query_terms(query)
    if not terms:
        return []
    by_thread, by_bot = await _chat_names(user_id, bots, rooms)
    hits: list[_Scored] = []
    for message, thread_bot_id in await talk.scan_all_chats(user_id, limit=CHAT_SEARCH_SCAN_LIMIT):
        chat = by_thread.get(message.thread_id) or by_bot.get(thread_bot_id)
        hit = _scored(message, chat, terms) if chat is not None else None
        if hit is not None:
            hits.append(hit)
    best = sorted(hits, key=lambda hit: -hit.score)[:CHAT_TEXT_SEARCH_RESULTS_MAX]   # stable: newest first on ties
    return [_out(hit) for hit in best]
