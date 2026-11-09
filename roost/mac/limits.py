"""``MacLimits``: how many Mac writes each bot made lately, in memory.

A parked run can't reset the count, because it lives here and not in the run. Writes the user approved
do not count (the executor never calls ``note_write``)."""

from __future__ import annotations

import time
from typing import Callable

from roost.constants import MAC_WRITES_WINDOW_S


class MacLimits:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._writes: dict[str, tuple[float, ...]] = {}

    def writes(self, bot_id: str) -> int:
        """This bot's unapproved writes in the last ``MAC_WRITES_WINDOW_S`` seconds."""
        return len(self._recent(bot_id))

    def note_write(self, bot_id: str) -> None:
        self._writes = {**self._writes, bot_id: (*self._recent(bot_id), self._clock())}

    def _recent(self, bot_id: str) -> tuple[float, ...]:
        cutoff = self._clock() - MAC_WRITES_WINDOW_S
        return tuple(at for at in self._writes.get(bot_id, ()) if at > cutoff)
