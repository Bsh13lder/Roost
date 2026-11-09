"""The call registry (docs/plans/2026-10-30-roost-voice.md §3, contract A): which threads are in a voice call right
now. In memory only, no schema change: a client beats its thread's call when the call screen opens and every
``VOICE_CALL_HEARTBEAT_S`` after, and a call with no beat for ``VOICE_CALL_EXPIRES_S`` is over. The owner check is
the routes' (through the thread); here a thread id is the key. Sessions are frozen and replaced, never changed."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping

from roost.voice.constants import VOICE_CALL_EXPIRES_S


@dataclass(frozen=True)
class CallSession:
    thread_id: str
    bot_id: str
    user_id: str
    started_at: float       # the registry clock's reading at the first beat
    beat_at: float          # ... and at the newest one
    interrupted: str | None = None   # the reply the user cut off last, if any


class CallRegistry:
    def __init__(self, clock: Callable[[], float] = time.monotonic, expires_s: float = VOICE_CALL_EXPIRES_S) -> None:
        self._clock = clock
        self._expires_s = expires_s
        self._sessions: Mapping[str, CallSession] = MappingProxyType({})

    def _live(self, session: CallSession | None) -> CallSession | None:
        if session is None or self._clock() - session.beat_at >= self._expires_s:
            return None
        return session

    def _set(self, thread_id: str, session: CallSession | None) -> None:
        kept = {tid: s for tid, s in self._sessions.items() if tid != thread_id and self._live(s) is not None}
        if session is not None:
            kept[thread_id] = session
        self._sessions = MappingProxyType(kept)

    def get(self, thread_id: str) -> CallSession | None:
        """The thread's call, if one is active (a beat within ``expires_s``)."""
        return self._live(self._sessions.get(thread_id))

    def active(self, thread_id: str) -> bool:
        return self.get(thread_id) is not None

    def beat(self, user_id: str, thread_id: str, bot_id: str) -> CallSession:
        """Start the thread's call, or keep it alive; an expired one starts over clean."""
        now = self._clock()
        current = self.get(thread_id)
        if current is None:
            session = CallSession(thread_id=thread_id, bot_id=bot_id, user_id=user_id, started_at=now, beat_at=now)
        else:
            session = replace(current, beat_at=now)
        self._set(thread_id, session)
        return session

    def end(self, thread_id: str) -> None:
        """End the thread's call; nothing happens when there is none."""
        self._set(thread_id, None)

    def interrupt(self, thread_id: str, message_id: str) -> None:
        """The user cut the bot off while it spoke ``message_id``; nothing happens with no active call."""
        current = self.get(thread_id)
        if current is not None:
            self._set(thread_id, replace(current, interrupted=message_id))
