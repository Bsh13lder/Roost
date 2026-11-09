"""``ExportScheduler`` — the debounced export job.

Every ``tasks_changed`` / ``notes_changed`` / ``money_changed`` / ``journal_changed`` frame pokes the user's
timer (an ``EventHub`` listener); the pass runs ``VAULT_EXPORT_DEBOUNCE_S`` after the last poke, so a burst
of changes is one pass. A poke while a pass is writing never cuts it short: one more pass follows it. A
``partial`` pass (the keeper's per-minute limit) is tried again after ``VAULT_EXPORT_RETRY_S``. The scheduler
only runs between ``start`` and ``stop`` (the gateway's lifespan): before that a poke does nothing. A pass
that fails is logged with its type only."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from roost.constants import VAULT_EXPORT_DEBOUNCE_S, VAULT_EXPORT_RETRY_S, VAULT_EXPORT_TRIGGERS
from roost.vault_export.store import ExportResult

log = logging.getLogger(__name__)

RunExport = Callable[[str], Awaitable[ExportResult]]


class ExportScheduler:
    def __init__(self, run: RunExport, *, delay: float = VAULT_EXPORT_DEBOUNCE_S,
                 retry: float = VAULT_EXPORT_RETRY_S) -> None:
        self._run = run
        self._delay = delay
        self._retry = retry
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._busy: frozenset[str] = frozenset()     # users whose pass is writing now
        self._again: frozenset[str] = frozenset()    # users poked while their pass was writing
        self._running = False

    def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        timers, self._timers = list(self._timers.values()), {}
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)

    def listener(self, user_id: str, event: dict[str, Any]) -> None:
        """For ``EventHub.add_listener``: a change to what the export writes pokes the user's timer."""
        if event.get("type") in VAULT_EXPORT_TRIGGERS:
            self.poke(user_id)

    def poke(self, user_id: str, delay: float | None = None) -> None:
        if not self._running:
            return
        if user_id in self._busy:
            self._again = self._again | {user_id}
            return
        previous = self._timers.get(user_id)
        if previous is not None and not previous.done():
            previous.cancel()
        self._timers = {**self._timers, user_id: asyncio.create_task(self._later(user_id, delay))}

    def pending(self, user_id: str) -> bool:
        timer = self._timers.get(user_id)
        return timer is not None and not timer.done()

    async def _later(self, user_id: str, delay: float | None) -> None:
        await asyncio.sleep(self._delay if delay is None else delay)
        self._busy = self._busy | {user_id}
        result: ExportResult | None = None
        try:
            result = await self._run(user_id)
        except Exception as exc:
            log.warning("a vault export pass failed: %s", type(exc).__name__)
        finally:
            self._busy = self._busy - {user_id}
            self._timers = {key: task for key, task in self._timers.items() if key != user_id}
        if user_id in self._again:
            self._again = self._again - {user_id}
            self.poke(user_id)
        elif result is not None and result.code == "partial":
            self.poke(user_id, self._retry)
