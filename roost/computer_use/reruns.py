"""``ScreenReruns``: a card's approved screen act, run outside any run (``ApprovedCalls``).

Kept apart from ``roost/computer_use/runner.py`` (the loop itself) so that file stays small."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from roost.approvals.models import PendingCall, StepOutcome
from roost.computer_use import session as loop
from roost.computer_use.runner import LINUX, NO_SCREEN_TEXT, ComputerUse, CuRun
from roost.config import Config
from roost.desk.control import ControlLock
from roost.events.hub import EventHub
from roost.lessons.signals import LessonSignals


def card_signal_key(card_id: str) -> str:
    """The run id an approved card's re-run works (and records its lesson signals) under."""
    return f"card:{card_id}"


async def _quiet(_: str) -> None:
    """An approved re-run has no live run to announce in: the card's result line says what happened."""


class ScreenReruns:
    """Runs a card's approved act outside any run (``ApprovedCalls``): the bot's own Linux computer, its own
    lease (``card:<id>``), this chat's fence, and the same re-resolve before the click."""

    def __init__(self, config: Config, bots: Any, desks: Any, gate: Any, events: EventHub,
                 leases: loop.ComputerUseLease, control: ControlLock | None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 signals: LessonSignals | None = None) -> None:
        self._config = config
        self._bots = bots
        self._desks = desks
        self._gate = gate
        self._events = events
        self._leases = leases
        self._control = control
        self._sleep = sleep
        self._signals = signals

    async def rerun(self, user_id: str, card: Any, step: PendingCall) -> StepOutcome:
        bot = await self._bots.get(user_id, card.bot_id)
        if bot is None or bot.computer != LINUX:
            return StepOutcome(False, NO_SCREEN_TEXT)
        computer = ComputerUse(
            CuRun(self._config, user_id, bot.id, card.thread_id, card_signal_key(card.id)),
            desk=self._desks.for_bot(bot.id, bot.computer), gate=self._gate, events=self._events,
            leases=self._leases, control=self._control, announce=_quiet, sleep=self._sleep,
            signals=self._signals,
        )
        return await computer.rerun(step)
