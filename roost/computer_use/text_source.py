"""Where text the bot types may come from, and what it says about itself.

``type`` is approved only when its text appears verbatim (after NFC and collapsing whitespace) in an
approved source, as whole words and at least ``CU_TYPE_APPROVED_MIN_CHARS`` long, or as a whole message or line
(so text can't be spelled out one letter at a time): your own messages in this chat, the approved ``type`` steps of answered cards in this
chat, or a note or document of yours that no run wrote after reading outside content. A bot's reply,
a teammate's line, a tool result and a page are never sources. ``text_flags`` marks contact details
(R9: an email address or a phone number you never gave the bot, ``contact_sources.py``) and secrets, which go to the
hard floor whatever the source. Owner, 2026-11-03: typing anything else never asks, approved or not."""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from roost.approvals.models import steps_from_json
from roost.computer_use.models import TextSourceIn
from roost.config import Config
from roost.constants import CU_APPROVED_CARDS_MAX, CU_APPROVED_MESSAGES_MAX, CU_TYPE_APPROVED_MIN_CHARS
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.documents.render import document_text
from roost.documents.store import DocumentStore
from roost.memory.secrets import looks_secret
from roost.notes.store import NoteStore
from roost.computer_use.contact import has_contact
from roost.computer_use.contact_sources import allowed_contacts

logger = logging.getLogger(__name__)

TYPE_TOOL = "type"
_EMPTY: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class ApprovedTexts:
    messages: tuple[str, ...]
    cards: Mapping[str, str]       # card id -> the text of its approved type steps
    notes: Mapping[str, str]       # note or document id -> its text (untainted, yours)
    contacts: frozenset[str] = frozenset()   # emails and phones you gave the bot (``contact.contact_details``)


def flat(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _candidates(source: TextSourceIn, texts: ApprovedTexts) -> tuple[str, ...]:
    if source.kind == "message":
        return texts.messages
    if source.kind == "card":
        if source.id is None:
            return tuple(texts.cards.values())
        found = texts.cards.get(source.id)
        return (found,) if found is not None else ()
    found = texts.notes.get(source.id) if source.id is not None else None
    return (found,) if found is not None else ()


def _word_edge(text: str, index: int) -> bool:
    """True when ``index`` sits between words (or at an end) in ``text``."""
    if index <= 0 or index >= len(text):
        return True
    return not (text[index - 1].isalnum() and text[index].isalnum())


def whole_words_in(wanted: str, candidate: str) -> bool:
    start = candidate.find(wanted)
    while start != -1:
        if _word_edge(candidate, start) and _word_edge(candidate, start + len(wanted)):
            return True
        start = candidate.find(wanted, start + 1)
    return False


def _approved_in(wanted: str, candidate: str) -> bool:
    if any(wanted == flat(line) for line in (candidate, *candidate.splitlines())):
        return True
    return len(wanted) >= CU_TYPE_APPROVED_MIN_CHARS and whole_words_in(wanted, flat(candidate))


def text_is_approved(text: str, source: TextSourceIn, texts: ApprovedTexts) -> bool:
    """True when ``text`` appears verbatim in the source it names (whitespace and NFC forgiven): as whole words
    of at least ``CU_TYPE_APPROVED_MIN_CHARS`` characters, or as a whole message or line."""
    wanted = flat(text)
    return bool(wanted) and any(_approved_in(wanted, candidate) for candidate in _candidates(source, texts))


def text_flags(text: str, contacts: frozenset[str] = frozenset()) -> frozenset[str]:
    """``contact``: an email address or a phone number that is not in ``contacts`` (yours). ``secret``: it looks
    like a password, code, key, or card or bank number."""
    flags = set()
    if has_contact(text, contacts):
        flags.add("contact")
    if looks_secret(text):
        flags.add("secret")
    return frozenset(flags)


async def your_messages(config: Config, user_id: str, thread_id: str,
                        limit: int = CU_APPROVED_MESSAGES_MAX) -> tuple[str, ...]:
    """Your own words in this chat, oldest first: role ``user``, kind ``text``, written by you (no bot author),
    never tainted, the newest ``limit``. Card answer lines are never sources: they hold a title built from the
    bot's arguments or an option it wrote."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT body FROM messages WHERE user_id = ? AND thread_id = ? AND role = 'user' "
            "AND kind = 'text' AND author_bot_id IS NULL AND tainted = 0 "
            "ORDER BY seq DESC LIMIT ?", (user_id, thread_id, limit))).fetchall()
    if not rows:
        return ()
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "messages:body")
    return tuple(body for row in reversed(rows) if (body := decrypt_field(row["body"], dek, aad, fallback="")))


def _typed_text(steps_text: str) -> str:
    typed = (step.arguments.get("text") for step in steps_from_json(steps_text) if step.tool == TYPE_TOOL)
    return "\n".join(text for text in typed if isinstance(text, str) and text)


async def _approved_cards(config: Config, user_id: str, thread_id: str) -> Mapping[str, str]:
    """The approved ``type`` steps of cards you said Yes to in this chat."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT id, steps FROM approval_cards WHERE user_id = ? AND thread_id = ? AND state = 'approved' "
            "ORDER BY created_at DESC LIMIT ?", (user_id, thread_id, CU_APPROVED_CARDS_MAX))).fetchall()
    if not rows:
        return _EMPTY
    dek = await get_user_dek(config, user_id)
    aad = user_aad(user_id, "approval_cards:steps")
    found = {row["id"]: _typed_text(decrypt_field(row["steps"], dek, aad, fallback="[]") or "[]") for row in rows}
    return MappingProxyType({card_id: text for card_id, text in found.items() if text})


async def _note_text(config: Config, user_id: str, note_id: str) -> str | None:
    note = await NoteStore(config).get(user_id, note_id)
    return None if note is None or note.tainted else note.content


async def _document_text(config: Config, user_id: str, document_id: str) -> str | None:
    document = await DocumentStore(config).get(user_id, document_id)
    if document is None or document.meta.tainted:
        return None
    try:
        return await asyncio.to_thread(document_text, document)
    except ValueError:
        logger.warning("Document %s could not be read as a typing source", document_id)
        return None


async def _named_records(config: Config, user_id: str, refs: Iterable[TextSourceIn]) -> Mapping[str, str]:
    """Notes and documents named by ``refs``: yours and untainted, else simply not approved."""
    found: dict[str, str] = {}
    for ref in refs:
        if ref.id is None or ref.id in found or ref.kind not in ("note", "document"):
            continue
        reader = _note_text if ref.kind == "note" else _document_text
        text = await reader(config, user_id, ref.id)
        if text:
            found[ref.id] = text
    return MappingProxyType(found)


async def load_approved_texts(config: Config, user_id: str, thread_id: str,
                              refs: Iterable[TextSourceIn], *, bot_id: str | None = None) -> ApprovedTexts:
    """Everything a ``type`` in this chat may quote. Every query names ``user_id``. With ``bot_id``, also the contact
    details you gave that bot (your messages, its instructions and memories)."""
    messages = await your_messages(config, user_id, thread_id)
    contacts = await allowed_contacts(config, user_id, bot_id, messages) if bot_id is not None else frozenset()
    return ApprovedTexts(
        messages=messages,
        cards=await _approved_cards(config, user_id, thread_id),
        notes=await _named_records(config, user_id, refs),
        contacts=contacts,
    )
