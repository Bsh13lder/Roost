"""Fresh start (owner, 2026-10-25): a chat line that hides every earlier web reply from the bot's next runs.

``_age_taint`` (``roost/talk/turn.py``) treats every tainted row before the newest Fresh start line as aged:
its text reaches the model only as the placeholder and it no longer taints the run. Nothing is deleted, and
``search_chat`` still finds that text (reading it taints only that run)."""

from __future__ import annotations

from typing import Final

from roost.events.hub import EventHub
from roost.talk.notices import post_notice
from roost.talk.store import Message, TalkStore

FRESH_START_KIND: Final = "fresh_start"
FRESH_START_TEXT: Final = "Fresh start: earlier web content is hidden from me. I can still search for it if you ask."


async def post_fresh_start(talk: TalkStore, events: EventHub, user_id: str, thread_id: str) -> Message:
    """The Fresh start line (role ``system``, never replayed), published to every open screen."""
    return await post_notice(talk, events, user_id, thread_id, FRESH_START_TEXT, kind=FRESH_START_KIND)


def last_fresh_start(messages: tuple[Message, ...]) -> int:
    """The index of the newest Fresh start line among ``messages``; -1 when there is none."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].kind == FRESH_START_KIND:
            return i
    return -1
