"""The "Not remembered" line: when ``remember`` is refused for a reason the user's own click can overcome (the
run read a web page), the chat gets a ``memory_offer`` line with a Remember it button instead of a blank.

The line's body is sealed JSON ``{"text", "kind", "importance", "memory_id"}``; ``memory_id`` is set once the
user pressed Remember it. The line is tainted (its text came from a run that read the web), it is never
replayed to the model, and pressing the button twice saves once."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import MAX_RECORD_ID_LENGTH, MEMORY_IMPORTANCE_MAX, MEMORY_IMPORTANCE_MIN, MEMORY_TEXT_MAX_CHARS
from roost.events.hub import EventHub
from roost.memory.models import Memory, MemoryDraft, MemoryKind
from roost.memory.service import MemoryService
from roost.talk.store import Message, TalkStore, message_out

MEMORY_OFFER_KIND = "memory_offer"
OFFERED_TOOL_TEXT = (
    "Not saved yet. Tell the user plainly that it is not saved and that they can tap Remember it in the chat to save it. Never say you saved it."
)
OFFER_REASON_TEXT = "I read a web page in this run, so I can't save memories myself."
NOT_REMEMBERED_PREVIEW = "Not remembered"
_END_MARKS = (".", "!", "?", "…")


class OfferBody(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    text: str = Field(min_length=1, max_length=MEMORY_TEXT_MAX_CHARS)
    kind: MemoryKind
    importance: int = Field(ge=MEMORY_IMPORTANCE_MIN, le=MEMORY_IMPORTANCE_MAX)
    memory_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)


@dataclass(frozen=True)
class AcceptedOffer:
    message: Message
    memory: Memory


def _sentence(text: str) -> str:
    return text if text.endswith(_END_MARKS) else f"{text}."


def offer_line(text: str) -> str:
    """``Not remembered: <text>. I read a web page in this run, so I can't save memories myself.``"""
    return f"Not remembered: {_sentence(text)} {OFFER_REASON_TEXT}"


def remembered_line(text: str) -> str:
    return f"Remembered: {_sentence(text)}"


def offer_body(text: str, kind: str, importance: int, memory_id: str | None = None) -> str:
    return json.dumps({"text": text, "kind": kind, "importance": importance, "memory_id": memory_id})


def parse_offer(body: str) -> OfferBody | None:
    """The line's body, or ``None`` for one that is not an offer's JSON."""
    try:
        return OfferBody.model_validate_json(body)
    except ValidationError:
        return None


def offer_preview(body: str) -> str:
    """The chat list's words for the line: never its JSON."""
    offer = parse_offer(body)
    if offer is None:
        return NOT_REMEMBERED_PREVIEW
    return remembered_line(offer.text) if offer.memory_id else offer_line(offer.text)


async def post_memory_offer(talk: TalkStore, events: EventHub, user_id: str, thread_id: str, bot_id: str,
                            text: str, kind: str, importance: int) -> Message:
    """Tainted, like the run it came from; ``memory_offer`` is not a model kind, so it is never replayed."""
    message = await talk.add_message(user_id, thread_id, "activity", offer_body(text, kind, importance),
                                     tainted=True, kind=MEMORY_OFFER_KIND, author_bot_id=bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message


async def _offer_in_thread(talk: TalkStore, user_id: str, thread_id: str,
                           message_id: str) -> tuple[Message, OfferBody] | None:
    message = await talk.get_message(user_id, message_id)
    if message is None or message.thread_id != thread_id or message.kind != MEMORY_OFFER_KIND:
        return None
    offer = parse_offer(message.body)
    return None if offer is None else (message, offer)


async def accept_offer(talk: TalkStore, memories: MemoryService, user_id: str, thread_id: str,
                       message_id: str) -> AcceptedOffer | None:
    """Save the offered memory as the user's own word (``source='user'``, never tainted: the user read the
    whole text and chose it). ``None``: no such offer of this user's in this thread. ``MemoryRefused``
    propagates. A second press finds the same memory (the store keeps one per text and scope)."""
    found = await _offer_in_thread(talk, user_id, thread_id, message_id)
    if found is None:
        return None
    message, offer = found
    bot_id = None if offer.kind == "about_you" else message.author_bot_id
    draft = MemoryDraft(kind=offer.kind, text=offer.text, bot_id=bot_id, source="user", created_by_bot=None,
                        importance=offer.importance, pinned=False, tainted=False)
    result = await memories.save(user_id, draft)
    if offer.memory_id != result.memory.id:
        body = offer_body(offer.text, offer.kind, offer.importance, result.memory.id)
        await talk.replace_body(user_id, message.id, body)
        message = replace(message, body=body)
    return AcceptedOffer(message, result.memory)
