"""Search the older part of one chat: every query word must appear, the best matches first.

The messages are the user's own data, but a reply that read web content stays marked as such."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from roost.constants import CHAT_SEARCH_LIMIT, CHAT_SEARCH_SNIPPET_CHARS
from roost.notes.search import query_terms
from roost.notes.text import fold
from roost.timezones import local_tz
from roost.talk.store import Message

_SPACES = re.compile(r"\s+")
_CUT = "…"
WEB_MARK = " [from web content]"


@dataclass(frozen=True)
class ChatHit:
    line: str
    tainted: bool


def _who(message: Message, bot_id: str) -> str:
    if message.role == "user" and message.author_bot_id is None:
        return "the user"
    return "you" if message.author_bot_id in (None, bot_id) else "a teammate"


def raw_snippet(body: str, folded: str, terms: tuple[str, ...]) -> str:
    """About ``CHAT_SEARCH_SNIPPET_CHARS`` characters around the first hit, ``…`` at a cut end, not escaped."""
    first = min(folded.find(term) for term in terms)
    start = max(0, first - CHAT_SEARCH_SNIPPET_CHARS // 2)
    end = min(len(body), start + CHAT_SEARCH_SNIPPET_CHARS)
    start = max(0, min(start, end - CHAT_SEARCH_SNIPPET_CHARS))
    return ("" if start == 0 else _CUT) + body[start:end] + ("" if end == len(body) else _CUT)


def _snippet(body: str, folded: str, terms: tuple[str, ...]) -> str:
    """The snippet escaped, for the model."""
    return html.escape(raw_snippet(body, folded, terms), quote=True)


def flatten(body: str) -> str:
    """A message body on one line."""
    return _SPACES.sub(" ", body).strip()


def match_score(folded: str, terms: tuple[str, ...]) -> int:
    return _score(folded, terms)


def _score(folded: str, terms: tuple[str, ...]) -> int:
    """0 unless every term appears."""
    counts = [folded.count(term) for term in terms]
    return 0 if any(count == 0 for count in counts) else sum(counts)


def search_hits(messages: Iterable[Message], query: str, bot_id: str) -> tuple[ChatHit, ...]:
    """``messages`` arrive newest first; the best score wins, then the newest."""
    terms = query_terms(query)
    if not terms:
        return ()
    scored: list[tuple[int, Message, str, str]] = []
    for message in messages:
        body = _SPACES.sub(" ", message.body).strip()
        folded = fold(body)
        if (score := _score(folded, terms)) > 0:
            scored.append((score, message, body, folded))
    best = sorted(scored, key=lambda item: -item[0])[:CHAT_SEARCH_LIMIT]
    return tuple(_hit(message, body, folded, terms, bot_id) for _, message, body, folded in best)


def _hit(message: Message, body: str, folded: str, terms: tuple[str, ...], bot_id: str) -> ChatHit:
    when = datetime.fromisoformat(message.created_at).astimezone(local_tz()).strftime("%Y-%m-%d %H:%M")
    line = f"- [{when}] {_who(message, bot_id)}: {_snippet(body, folded, terms)}"
    return ChatHit(line + (WEB_MARK if message.tainted else ""), message.tainted)


def search_thread(messages: Iterable[Message], query: str, bot_id: str) -> tuple[str, ...]:
    return tuple(hit.line for hit in search_hits(messages, query, bot_id))
