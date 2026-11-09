"""What went wrong in a run, kept in memory until the run ends (docs/plans/2026-10-31-roost-lessons.md §2).

Signals carry only Roost's own facts: the kind, the host, the act's class and how many times. Never a page's words,
a control's label, the bot's ``expect`` text or anything typed: those come from or near outside content, and a
lesson is built only from trusted text so its Skill card is not marked "from web content" (§4)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal, Mapping

from roost.lessons.constants import LESSON_SIGNAL_RUNS_KEPT, LESSON_SIGNALS_PER_RUN_MAX

SignalKind = Literal["expect_missed", "asked_again", "declined"]


@dataclass(frozen=True)
class LessonSignal:
    kind: SignalKind     # expect_missed: an act left the page as it was; asked_again: a second card for the same
                         # control in one run; declined: you said No to a card of this run
    host: str            # the page's host ("" when none)
    action: str          # the act's commit class ("submit", "browsing", …) or the tool's name
    count: int = 1


class LessonSignals:
    """One per gateway (``app.state.lesson_signals``). ``record`` while a run works, ``take`` once when it ends."""

    def __init__(self) -> None:
        self._runs: Mapping[str, tuple[LessonSignal, ...]] = MappingProxyType({})

    def record(self, run_id: str, signal: LessonSignal) -> None:
        """The same kind, host and action again adds to its count; at most ``LESSON_SIGNALS_PER_RUN_MAX`` per run."""
        if not run_id:
            return
        kept = self._runs.get(run_id, ())
        same = next((s for s in kept if (s.kind, s.host, s.action) == (signal.kind, signal.host, signal.action)), None)
        if same is not None:
            updated = tuple(replace(s, count=s.count + signal.count) if s is same else s for s in kept)
        elif len(kept) >= LESSON_SIGNALS_PER_RUN_MAX:
            return
        else:
            updated = (*kept, signal)
        runs = {k: v for k, v in self._runs.items() if k != run_id}
        if len(runs) >= LESSON_SIGNAL_RUNS_KEPT:            # a run that never ended: the oldest is dropped
            runs = dict(list(runs.items())[1:])
        self._runs = MappingProxyType({**runs, run_id: updated})

    def take(self, run_id: str) -> tuple[LessonSignal, ...]:
        """This run's signals, forgotten as they are handed over."""
        found = self._runs.get(run_id, ())
        self._runs = MappingProxyType({k: v for k, v in self._runs.items() if k != run_id})
        return found
