# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Milind Soni and OpenMausBot contributors
# Modified from OpenMausBot server/computer-control.ts and server/control-client.ts @ 3b1f6de by BlckIt, 2026:
# ported to Python asyncio as one in-memory hold per bot; no pleas, leases or HTTP client; refusal texts
# rewritten in our own words (roost/talk/instructions.py).
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy of the
# License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Who is driving a bot's computer: the person or the bot (S1.8).

- Only the person takes or gives back control, through HTTP routes. No model
  tool can.
- While the person holds it, the bot's browser calls are refused, not queued.
  A queued call would land after the person moved on, on whatever is then
  under it.
- A call made during a hold waits up to ``wait_seconds`` for the hand-back,
  and even then is not performed: the page may have changed.
- ``wait_taken`` is the other direction: a bot that is waiting on a page (the
  Stuck flow's wait for a check to pass) learns at once that the person took
  control, instead of sleeping on.
- Holds live in memory on purpose. A gateway restart clears them, so a stale
  hold can never brick a bot's computer.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Literal, NamedTuple

from roost.constants import CONTROL_WAIT_SECONDS

HandsOutcome = Literal["free", "handed_back", "still_held"]


class ControlMark(NamedTuple):
    """How many times the person has taken a bot's computer, and whether they hold it now. A desk that saw a
    different mark last time follows the tab in front once it is given back (``KeeperDesk``)."""

    epoch: int
    held: bool


@dataclass(frozen=True)
class Hold:
    since: float   # the clock's reading when the person took control


class ControlLock:
    def __init__(self, *, wait_seconds: float = CONTROL_WAIT_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._wait = wait_seconds
        self._clock = clock
        self._holds: dict[str, Hold] = {}
        self._released: dict[str, asyncio.Event] = {}
        self._taken: dict[str, asyncio.Event] = {}   # set by ``take``, for ``wait_taken``
        self._epochs: dict[str, int] = {}            # takes so far per bot (C3: the next act looks first)

    def held(self, bot_id: str) -> Hold | None:
        return self._holds.get(bot_id)

    def take(self, bot_id: str) -> Hold:
        """Idempotent: a second click never makes the hold look newer than it is."""
        current = self._holds.get(bot_id)
        if current is not None:
            return current
        hold = Hold(since=self._clock())
        self._holds = {**self._holds, bot_id: hold}
        self._epochs = {**self._epochs, bot_id: self._epochs.get(bot_id, 0) + 1}
        self._released = {**self._released, bot_id: asyncio.Event()}
        self._taken_event(bot_id).set()
        return hold

    def epoch(self, bot_id: str) -> int:
        """How many times the person has taken this bot's computer (in memory). A screen loop that saw a
        lower number last time looks again before it acts (C3, R8)."""
        return self._epochs.get(bot_id, 0)

    def mark(self, bot_id: str) -> ControlMark:
        return ControlMark(epoch=self.epoch(bot_id), held=bot_id in self._holds)

    def give_back(self, bot_id: str) -> None:
        event = self._released.get(bot_id)
        self._holds = {k: v for k, v in self._holds.items() if k != bot_id}
        self._released = {k: v for k, v in self._released.items() if k != bot_id}
        if event is not None:
            event.set()
        # A set "taken" event is spent with its hold, so the next wait starts fresh. One that is
        # not set stays: a call still waiting on it must hear of a later take.
        taken = self._taken.get(bot_id)
        if taken is not None and taken.is_set():
            self._taken = {k: v for k, v in self._taken.items() if k != bot_id}

    def forget(self, bot_id: str) -> None:
        """The bot was retired: a hold on its computer means nothing any more."""
        self.give_back(bot_id)
        self._taken = {k: v for k, v in self._taken.items() if k != bot_id}

    async def wait_for_hands(self, bot_id: str) -> HandsOutcome:
        event = self._released.get(bot_id)
        if bot_id not in self._holds or event is None:
            return "free"
        try:
            await asyncio.wait_for(event.wait(), timeout=self._wait)
        except TimeoutError:
            return "still_held"
        return "handed_back"

    async def wait_released(self, bot_id: str) -> None:
        """Returns at once when the person does not hold the computer, else when they give it back."""
        event = self._released.get(bot_id)
        if bot_id in self._holds and event is not None:
            await event.wait()

    async def wait_taken(self, bot_id: str, timeout: float) -> bool:
        """True as soon as the person holds the bot's computer: at once when they already do, else
        when they take control within ``timeout`` seconds. False when the time runs out."""
        if bot_id in self._holds:
            return True
        try:
            await asyncio.wait_for(self._taken_event(bot_id).wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True

    def _taken_event(self, bot_id: str) -> asyncio.Event:
        event = self._taken.get(bot_id)
        if event is None:
            event = asyncio.Event()
            self._taken = {**self._taken, bot_id: event}
        return event
