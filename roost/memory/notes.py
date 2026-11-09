"""The quiet "Remembered" line a bot posts in its chat after it saves a memory."""

from __future__ import annotations

import json

from roost.events.hub import EventHub
from roost.memory.models import Memory
from roost.talk.store import Message, TalkStore, message_out


def memory_note_body(memory: Memory) -> str:
    return json.dumps({"memory_id": memory.id, "kind": memory.kind, "text": memory.text})


async def post_memory_note(talk: TalkStore, events: EventHub, user_id: str, thread_id: str, bot_id: str,
                           memory: Memory) -> Message:
    """Never tainted and never replayed to the model (``memory_note`` is not a model kind)."""
    message = await talk.add_message(user_id, thread_id, "activity", memory_note_body(memory),
                                     kind="memory_note", author_bot_id=bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message
