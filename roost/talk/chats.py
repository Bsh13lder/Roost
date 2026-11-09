"""Home's chat list (S1.4): one row per bot (its own threads, not rooms) and
per room, each with its newest message as a one-line preview, newest first.
Bodies are decrypted here, server-side, and every read is scoped by user_id."""

from __future__ import annotations

import json
from typing import Any, Literal

from roost.bots.store import BotStore
from roost.instruction_proposals.texts import change_line
from roost.mac.activity import activity_line
from roost.talk.chat_feel import shown_reply
from roost.memory.offers import MEMORY_OFFER_KIND, offer_preview
from roost.programs.wrap import activity_line as program_line
from roost.constants import CHAT_PREVIEW_CHARS
from roost.rooms.store import RoomStore
from roost.stuck.texts import stuck_activity
from roost.talk.notices import preview
from roost.talk.store import Message, TalkStore
from roost.voice.constants import ENGLISH_FIX_KIND, ENGLISH_FIX_PREVIEW

PreviewKind = Literal["text", "handoff", "card", "notice"]


def _card_name(body: str) -> str:
    try:
        name = json.loads(body).get("name")
    except (ValueError, AttributeError):
        return "a bot"
    return name if isinstance(name, str) else "a bot"


def _memory_text(body: str) -> str | None:
    """The text of a ``memory_note`` line, or ``None`` for a body that isn't its JSON."""
    try:
        text = json.loads(body).get("text")
    except (ValueError, AttributeError):
        return None
    return text if isinstance(text, str) else None


def _card_host(body: str) -> str:
    """A Stuck card's host, or "" for a card with no web address (an
    ``ask_for_help`` card) or a body that isn't the card's JSON."""
    try:
        host = json.loads(body).get("host")
    except (ValueError, AttributeError):
        return ""
    return host if isinstance(host, str) else ""


REPORT_FALLBACK_PREVIEW = "A report"
ROUTINE_NOTE_FALLBACK_PREVIEW = "A routine update"
ROUTINE_PROPOSAL_PREVIEW = "Asking you: a routine"
SKILL_PROPOSAL_PREVIEW = "Skill proposal · {name}"
INSTRUCTIONS_PROPOSAL_PREVIEW = "Asking you: update my instructions"
KEY_REQUEST_PREVIEW = "Add a key · {service}"


def _json_text(body: str, key: str) -> str | None:
    """A string field of a message's JSON body, or ``None`` for a body that isn't that JSON."""
    try:
        value = json.loads(body).get(key)
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value.strip() else None


TASK_CARDS_ADDED_PREVIEW = "Added a task"
TASK_CARDS_ADDED_MANY_PREVIEW = "Added {count} tasks"
TASK_CARDS_SHOWN_PREVIEW = "Showed {count} tasks"
TASK_CARDS_FALLBACK_PREVIEW = "Showed tasks"


def _task_cards_preview(body: str) -> str:
    """A ``task_cards`` line in words: "Added a task", "Showed 6 tasks" (never its JSON)."""
    try:
        data = json.loads(body)
        count = len(data["task_ids"]) + int(data.get("more", 0))
        verb = data.get("verb")
    except (ValueError, TypeError, KeyError, AttributeError):
        return TASK_CARDS_FALLBACK_PREVIEW
    if verb == "added":
        return TASK_CARDS_ADDED_PREVIEW if count == 1 else TASK_CARDS_ADDED_MANY_PREVIEW.format(count=count)
    return TASK_CARDS_SHOWN_PREVIEW.format(count=count)


APPROVAL_DONE_PREVIEW = "Did what you approved"
APPROVAL_ASKING_PREVIEW = "Asking you"


def _approval_preview(body: str) -> str:
    """An Ask card's preview: "Asking you: <the first step's title>"."""
    try:
        titles = json.loads(body).get("steps")
    except (ValueError, AttributeError):
        return APPROVAL_ASKING_PREVIEW
    if isinstance(titles, list) and titles and isinstance(titles[0], str):
        return preview(f"{APPROVAL_ASKING_PREVIEW}: {titles[0]}", CHAT_PREVIEW_CHARS)
    return APPROVAL_ASKING_PREVIEW


def chat_preview(message: Message) -> tuple[str, PreviewKind]:
    """A ``card_answer`` line (role "user") previews like your own words: the last branch."""
    if message.kind == "bot_created":
        return f"Created {_card_name(message.body)}", "card"
    if message.kind == "suggestion":
        return f"Suggested {_card_name(message.body)}", "card"
    if message.kind == "stuck":
        return stuck_activity(_card_host(message.body)), "card"
    if message.kind == "approval":
        return _approval_preview(message.body), "card"
    if message.kind == "mac_activity":
        return activity_line(message.body), "notice"
    if message.kind == "instruction_change":
        return change_line(_json_text(message.body, "section") or "a section"), "notice"
    if message.kind == "program_activity":
        return preview(program_line(message.body), CHAT_PREVIEW_CHARS), "notice"
    if message.kind == "approval_result":
        return APPROVAL_DONE_PREVIEW, "notice"
    if message.kind == "task_cards":
        return _task_cards_preview(message.body), "notice"     # never the step's text: a read's file text stays out of the list
    if message.kind == "memory_note":
        text = _memory_text(message.body)
        return (preview(f"Remembered: {text}", CHAT_PREVIEW_CHARS) if text else "Remembered something"), "notice"
    if message.kind == ENGLISH_FIX_KIND:    # Correct my English: words, never the line's JSON (and never a chat row)
        return ENGLISH_FIX_PREVIEW, "notice"
    if message.kind == MEMORY_OFFER_KIND:
        return preview(offer_preview(message.body), CHAT_PREVIEW_CHARS), "notice"
    if message.kind == "handoff":
        return preview(message.body, CHAT_PREVIEW_CHARS), "handoff"
    if message.kind == "report":
        return preview(_json_text(message.body, "headline") or REPORT_FALLBACK_PREVIEW, CHAT_PREVIEW_CHARS), "notice"
    if message.kind in ("routine_note", "question_note"):
        text = _json_text(message.body, "text") or ROUTINE_NOTE_FALLBACK_PREVIEW
        return preview(text, CHAT_PREVIEW_CHARS), "notice"
    if message.kind == "routine_proposal":
        return ROUTINE_PROPOSAL_PREVIEW, "card"
    if message.kind == "instructions_proposal":    # Replies: words, never the card's JSON
        return INSTRUCTIONS_PROPOSAL_PREVIEW, "card"
    if message.kind == "connector_request":    # Connectors: words, never the card's JSON
        return preview(KEY_REQUEST_PREVIEW.format(service=_json_text(message.body, "service") or "a service"),
                       CHAT_PREVIEW_CHARS), "card"
    if message.kind == "skill_proposal":    # Skills: words, never the card's JSON
        return preview(SKILL_PROPOSAL_PREVIEW.format(name=_json_text(message.body, "name") or "a skill"),
                       CHAT_PREVIEW_CHARS), "card"
    if message.role in ("system", "activity"):
        return preview(message.body, CHAT_PREVIEW_CHARS), "notice"
    if message.role == "bot":
        return preview(shown_reply(message.body), CHAT_PREVIEW_CHARS), "text"
    return preview(message.body, CHAT_PREVIEW_CHARS), "text"


def _row(kind: str, row_id: str, name: str, created_at: str, message: Message | None,
         thread_id: str | None = None) -> dict[str, Any]:
    """A room always has its one thread, so its row names it even before the first message."""
    if message is None:
        return {"kind": kind, "id": row_id, "name": name, "thread_id": thread_id, "preview": None,
                "preview_kind": None, "from_you": False, "last_at": created_at, "tainted": False}
    text, preview_kind = chat_preview(message)
    return {"kind": kind, "id": row_id, "name": name, "thread_id": message.thread_id, "preview": text,
            "preview_kind": preview_kind, "from_you": message.role == "user" and message.author_bot_id is None,
            "last_at": message.created_at, "tainted": message.tainted}


async def chat_rows(*, user_id: str, bots: BotStore, talk: TalkStore, rooms: RoomStore) -> list[dict[str, Any]]:
    bot_rows = [_row("bot", bot.id, bot.name, bot.created_at, await talk.latest_for_bot(user_id, bot.id))
                for bot in await bots.list(user_id)]
    room_rows = [_row("room", room.id, room.name, room.created_at,
                      await talk.latest_in_thread(user_id, room.thread_id), room.thread_id)
                 for room in await rooms.list(user_id)]
    return sorted([*bot_rows, *room_rows], key=lambda row: row["last_at"], reverse=True)
