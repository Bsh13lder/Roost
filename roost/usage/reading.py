"""The usage reading, the 10% reserve and the full limit's rules (all pure).

A ``UsageSource`` returns what is left of the user's usage limit, or ``None`` when Roost cannot read it. Nothing
here can read one yet, so ``NoUsageSource`` ships: with no reading the full limit never applies and its switch
refuses, because the reserve cannot be checked without one. The full limit is a per-bot setting
(``bots.full_limit_until``) that only ``PUT /api/bots/{id}/full-limit`` writes; no tool can."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from roost.bots.models import Bot
from roost.constants import USAGE_RESERVE_FRACTION
from roost.work.runs import seconds_until_madrid_midnight

FULL_LIMIT_REFUSAL = "Roost can't read your usage limit yet, so this stays off."


@dataclass(frozen=True)
class UsageReading:
    remaining_fraction: float          # 0.0 to 1.0 of the limit still available
    resets_at: datetime | None         # when the limit resets (aware), if known


class UsageSource(Protocol):
    async def read(self) -> UsageReading | None: ...


class NoUsageSource:
    """No way to read the limit: always ``None``."""

    async def read(self) -> UsageReading | None:
        return None


def in_reserve(reading: UsageReading | None) -> bool:
    """True when a reading shows no more than the reserve left. No reading is not "in the reserve"."""
    return reading is not None and reading.remaining_fraction <= USAGE_RESERVE_FRACTION


def full_limit_active(bot: Bot, reading: UsageReading | None, now: datetime) -> bool:
    """The bot's full limit is on, not yet ended, and a reading exists to check the reserve against."""
    if reading is None or bot.full_limit_until is None:
        return False
    try:
        until = datetime.fromisoformat(bot.full_limit_until)
    except ValueError:
        return False
    return until.tzinfo is not None and until > now


def full_limit_end(reading: UsageReading, now: datetime) -> datetime:
    """Until the reading's reset, or the next local midnight when it gives none (or a reset already past)."""
    if reading.resets_at is not None and reading.resets_at > now:
        return reading.resets_at.astimezone(timezone.utc)
    return now.astimezone(timezone.utc) + timedelta(seconds=seconds_until_madrid_midnight(now))
