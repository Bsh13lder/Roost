"""W2: is the act's quote really your words, and is this an act your words may cover?

``quote_is_yours`` is pure: after NFC and whitespace are forgiven the quote is a whole message or line of yours, or
at least ``OWNER_WORDS_MIN_WORDS`` whole words inside one. ``your_quote`` reads the sources: your newest
``OWNER_WORDS_MESSAGES_MAX`` own, untainted text messages in this chat (the newest one when the act carries no quote) (``text_source``'s own query; a bot's reply,
a card line, a tool result or a page is never one). ``words_may_cover`` says which floor acts your words may cover:
a send, submit, accept, delete or account click or key (owner, 2026-11-03: sign up, register, save changes, log
out), never spend, a password or email change or anything unknown (W3), never a covered control, a secret box or contact details (W4), and never a send while the page holds text the
bot wrote itself (``own_text``, owner 2026-11-03: the Send card shows it first)."""

from __future__ import annotations

from typing import Iterable

from roost.approvals.models import FloorKind
from roost.computer_use.commit_words import commit_class, normalise
from roost.computer_use.models import ActResolution
from roost.computer_use.text_source import flat, whole_words_in, your_messages
from roost.config import Config
from roost.owner_words.constants import (
    OWNER_WORDS_CLASSES,
    OWNER_WORDS_NEVER_WORDS,
    OWNER_WORDS_MAX_CHARS,
    OWNER_WORDS_MESSAGES_MAX,
    OWNER_WORDS_MIN_WORDS,
)

_CLASSES = frozenset(OWNER_WORDS_CLASSES)


def _in_message(wanted: str, message: str) -> bool:
    if any(wanted == flat(line) for line in (message, *message.splitlines())):
        return True
    return len(wanted.split()) >= OWNER_WORDS_MIN_WORDS and whole_words_in(wanted, flat(message))


def quote_is_yours(quote: str, messages: Iterable[str]) -> bool:
    wanted = flat(quote)
    return bool(wanted) and any(_in_message(wanted, message) for message in messages)


async def your_quote(config: Config, user_id: str, thread_id: str, quote: str | None) -> str:
    """The quote when it checks out as yours, else "". With no quote (W9, owner 2026-10-31: the bot forgot to quote
    you), your newest own message is the quote; the model check still decides whether it asks for this act."""
    if not thread_id:
        return ""
    messages = await your_messages(config, user_id, thread_id, limit=OWNER_WORDS_MESSAGES_MAX)
    if not quote:
        return messages[-1][:OWNER_WORDS_MAX_CHARS] if messages else ""
    return quote if quote_is_yours(quote, messages) else ""


def _class_of(r: ActResolution) -> str:
    """A click is read again from its own control, as ``act_commits`` does; a key keeps its resolved class."""
    return commit_class(r.target) if r.tool == "click" else r.commit


def words_may_cover(r: ActResolution, kind: FloorKind) -> bool:
    """True when a checked quote may stand in for the card at floor ``kind`` (the model check still decides)."""
    target = r.target
    if not r.owner_words or target is None or r.covered_by or r.refusal or r.space != "page":
        return False
    if target.secret_field or target.cross_origin_frame:
        return False
    if kind == "typed_text":
        return r.tool == "type" and not r.text_flags
    # Owner, 2026-11-03: text the bot wrote itself is always shown on the Send card first, whatever you said.
    return (kind == "commit_click" and r.tool != "type" and not r.own_text and _class_of(r) in _CLASSES
            and not _names_a_secret_change(r))


def _names_a_secret_change(r: ActResolution) -> bool:
    """Owner, 2026-11-03: a password or email change always shows its card, whatever your words said."""
    target = r.target
    words = f"{target.text} {target.visible_text} {target.form_submit_text}" if target is not None else ""
    said = set(normalise(words).replace("-", " ").split()) | set(normalise(words).split())
    return any(word in said for word in OWNER_WORDS_NEVER_WORDS)
