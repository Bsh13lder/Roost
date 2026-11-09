"""``LimitState``: where a bot stands against its daily run cap and the usage reserve (the scheduler and the runner
both ask)."""

from __future__ import annotations

from dataclasses import dataclass

from roost.usage.reading import UsageReading


@dataclass(frozen=True)
class LimitState:
    count: int                              # runs the bot has started today (local)
    cap: int                                # runs it may start today
    at_cap: bool
    full_limit: bool = False                # the bot's full limit is on, not ended, and a reading exists
    in_reserve: bool = False                # the reading shows no more than the 10% reserve
    reading: UsageReading | None = None

    @property
    def capped(self) -> bool:
        """At the daily cap with no way past it: the full limit lifts the cap only outside the reserve."""
        return self.at_cap and not (self.full_limit and not self.in_reserve)
