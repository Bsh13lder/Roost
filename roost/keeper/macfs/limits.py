"""A sliding-minute cap on Mac file steps per bot (``rate_limited``, HTTP 429)."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from roost.constants import MAC_OPS_PER_MINUTE
from roost.keeper.macfs.errors import MacFsError

_WINDOW_S = 60.0


class OpsLimiter:
    def __init__(self, limit: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._clock = clock
        self._taken: dict[str, deque[float]] = {}

    def take(self, bot_id: str) -> None:
        now = self._clock()
        limit = self._limit if self._limit is not None else MAC_OPS_PER_MINUTE
        recent = self._taken.setdefault(bot_id, deque())
        while recent and now - recent[0] >= _WINDOW_S:
            recent.popleft()
        if len(recent) >= limit:
            raise MacFsError("rate_limited")
        recent.append(now)
