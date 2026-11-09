"""System notices a run posts into a thread (spec §4.2): stored as
``role="system"`` with a ``kind`` the face styles, and published live."""

from __future__ import annotations

from typing import Sequence

from roost.constants import DROPPED_PREVIEW_CHARS
from roost.events.hub import EventHub
from roost.talk.store import Message, MessageKind, TalkStore, message_out
from roost.work.models import WorkItem, WorkState


async def post_notice(
    talk: TalkStore, events: EventHub, user_id: str, thread_id: str, body: str,
    *, kind: MessageKind = "notice",
) -> Message:
    message = await talk.add_message(user_id, thread_id, role="system", body=body, kind=kind)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message


def preview(text: str, limit: int = DROPPED_PREVIEW_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def interrupted_note(call: str) -> str:
    return f"Interrupted, outcome unknown: {call}. The bot will check before repeating it."


def restart_dropped_note(task: str) -> str:
    return (f"Dropped after a restart: “{preview(task)}”. "
            "The bot that asked will ask again if it still needs it.")


def stop_note(items: Sequence[WorkItem], done: Sequence[str] = ()) -> str:
    """"Stopped.", what the run did ("Done so far: Added a task.") and what waited and was dropped."""
    waiting = [item for item in items if item.state is WorkState.QUEUED]
    parts = ["Stopped."]
    if done:
        parts.append(f"Done so far: {', '.join(done)}.")
    if waiting:
        noun = "message" if len(waiting) == 1 else "messages"
        quoted = ", ".join(f"“{preview(item.body)}”" for item in waiting)
        parts.append(f"Dropped {len(waiting)} waiting {noun}: {quoted}.")
    return " ".join(parts)


def off_duty_note(bot_name: str) -> str:
    return f"{bot_name} is off duty. This waits until you bring it back."


def daily_limit_note(bot_name: str, cap: int) -> str:
    runs = "run" if cap == 1 else "runs"
    return (f"Daily limit reached: {bot_name} has done {cap} {runs} today. "
            "Waiting messages stay queued and run after midnight.")
