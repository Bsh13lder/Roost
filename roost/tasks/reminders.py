# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/tasks/pre_reminders.py lines 36-79 @ 21e1002, adapted for Roost

"""Advance reminders as data (M1 D6): negative offsets like -30m against the
reminder time; firing them is M3."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Sequence

from roost.constants import DEFAULT_PRE_REMINDERS

TOO_EARLY_TEXT = "The advance reminder {entry} would fall before the first day of the calendar. Pick a later time."

_OFFSET_RE = re.compile(
    r"^-\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$",
    re.IGNORECASE,
)


def parse_offset_against(value: str, base: datetime) -> datetime | None:
    """Parse a negative relative offset like ``-2h`` as ``base - offset``.

    Returns ``None`` when ``value`` isn't a valid non-zero offset.
    """
    if not value:
        return None
    match = _OFFSET_RE.match(value.strip())
    if not match:
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    if days == 0 and hours == 0 and minutes == 0:
        return None
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base - timedelta(days=days, hours=hours, minutes=minutes)


def parse_iso_datetime(value: str) -> datetime | None:
    """Parse an ISO-8601 datetime string → UTC-aware datetime, or ``None``.

    An aware input is converted to UTC (the docstring always promised this;
    until 2026-07-30 a ``+02:00`` value kept its offset and every timestamp
    derived from it inherited the same 2h skew against the daemon's lexical
    string compare). A naive input is still read as UTC — by the time values
    reach this module they are canonical UTC-aware (``_normalize_reminder_to_utc``
    runs at every write boundary); naive-as-UTC only remains as the least-wrong
    reading for un-migrated legacy strings.
    """
    try:
        dt = datetime.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _instant(entry: str, base: datetime) -> datetime | None:
    """One advance reminder's instant, or ``None`` when ``entry`` is neither
    an offset nor a time. A reminder in the calendar's first hours (year 1)
    has no room before it: ``base - 30m`` overflows, which is a plain
    refusal (``ValueError``), never a crash (redesign P3)."""
    try:
        return parse_offset_against(entry, base) or parse_iso_datetime(entry)
    except OverflowError as exc:
        raise ValueError(TOO_EARLY_TEXT.format(entry=entry)) from exc


def resolve_pre_reminders(entries: Sequence[str] | None, reminder_at: str | None) -> tuple[str, ...]:
    """UTC ISO instants for ``entries`` (offsets like -30m, or ISO times).
    ``None`` means LazyClaw's default (30 minutes before) when there is a
    reminder; ``[]`` means none."""
    if reminder_at is None:
        if entries:
            raise ValueError("Advance reminders need a reminder time.")
        return ()
    base = parse_iso_datetime(reminder_at)
    if base is None:
        raise ValueError(f"{reminder_at!r} is not a date and time.")
    wanted = DEFAULT_PRE_REMINDERS if entries is None else tuple(entries)
    instants = tuple(_instant(entry, base) for entry in wanted)
    bad = [entry for entry, instant in zip(wanted, instants) if instant is None]
    if bad:
        raise ValueError(f"{bad[0]!r} is not an offset like -30m or a date and time.")
    return tuple(sorted({instant.astimezone(timezone.utc).isoformat() for instant in instants}))
