"""Crashed tab recovery (docs/plans/2026-10-30-roost-voice.md §4).

A tab whose renderer the computer's cgroup OOM-killed (Gela's Brave opening WhatsApp Web, 2026-10-31) keeps its
target and session, but never answers a command again: every call timed out, ``open_page`` said the browser "did not
answer", and nothing opened the page again. ``CrashWatch`` tells a crashed tab from a slow one: ``Inspector.targetCrashed``
seen on the tab's session (the client's standing listener, when it has one), or a ``Runtime.evaluate("1")`` probe
that fails or gets no answer within ``CDP_CRASH_PROBE_TIMEOUT_S``. ``PageKeepsCrashing`` is what the desk raises when
the fresh tab fails too: a ``DeskUnavailable`` with its own words, never "unavailable"."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from roost.constants import CDP_CRASH_EVENT, CDP_CRASH_PROBE_TIMEOUT_S, CRASHED_TAB_KEEPS_CRASHING_TEXT
from roost.desk import DeskUnavailable
from roost.desk.cdp import CdpReplyError

PROBE_EXPRESSION = "1"


class PageKeepsCrashing(DeskUnavailable):
    """The tab crashed, a fresh tab was opened at the same address, and that one failed too."""

    def __init__(self) -> None:
        super().__init__(CRASHED_TAB_KEEPS_CRASHING_TEXT)


class _Client(Protocol):
    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict: ...


class CrashWatch:
    def __init__(self, client: _Client) -> None:
        self._client = client
        listen = getattr(client, "listen", None)     # a page stand-in without a listener still gets the probe
        self._events: asyncio.Queue[dict[str, Any]] | None = (
            listen(frozenset({CDP_CRASH_EVENT})) if listen is not None else None)

    def seen(self, session_id: str) -> bool:
        """``Inspector.targetCrashed`` came for ``session_id`` since the last look (other sessions' events are dropped)."""
        if self._events is None:
            return False
        crashed = False
        while not self._events.empty():
            event = self._events.get_nowait()
            crashed = crashed or event.get("sessionId") == session_id
        return crashed

    async def answers(self, session_id: str) -> bool:
        """The tab evaluates a constant within the probe's time."""
        try:
            async with asyncio.timeout(CDP_CRASH_PROBE_TIMEOUT_S):
                await self._client.send("Runtime.evaluate", {"expression": PROBE_EXPRESSION, "returnByValue": True},
                                        session_id=session_id)
        except (CdpReplyError, TimeoutError):
            return False
        return True

    async def crashed(self, session_id: str) -> bool:
        """Whether the tab behind ``session_id`` is dead: its crash was seen, or it no longer answers."""
        return self.seen(session_id) or not await self.answers(session_id)
