"""local days and months for expenses (an expense at 00:30 on 1 Nov is November)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from roost.timezones import local_tz
from roost.tasks.day_words import find_day

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_YESTERDAY = frozenset({"yesterday", "ayer"})
_TODAY = frozenset({"today", "hoy"})
# A trailing clock time ("at 9", "a las 21:00", "9pm") carries no information
# for a day-only field — strip it before matching "yesterday"/"today" so a
# phrase like "yesterday at 9" is read as yesterday, not handed to the
# forward-looking task parser below (which would read only "at 9" and,
# because it ignores `now`, can land on tomorrow).
_TRAILING_CLOCK_TIME = re.compile(
    r"\s+(?:at\s+|a\s+las\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?$", re.IGNORECASE,
)
_DAYS_AGO = re.compile(r"^(\d+)\s+days?\s+ago$", re.IGNORECASE)
_HACE_DIAS = re.compile(r"^hace\s+(\d+)\s+d[ií]as?$", re.IGNORECASE)


def _local(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(local_tz())


def today_madrid(now: datetime | None = None) -> str:
    return _local(now).date().isoformat()


def current_month(now: datetime | None = None) -> str:
    return _local(now).strftime("%Y-%m")


def month_bounds(month: str) -> tuple[str, str]:
    """``[first day, first day of next month)`` as ISO dates."""
    match = _MONTH.match(month)
    if match is None:
        raise ValueError(f"“{month}” is not a month like 2026-10.")
    year, number = int(match.group(1)), int(match.group(2))
    first = date(year, number, 1)
    following = date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
    return first.isoformat(), following.isoformat()


def _named_day(value: str, now: datetime | None) -> str | None:
    """"yesterday"/"today" (and Spanish), with any trailing clock time dropped."""
    bare = _TRAILING_CLOCK_TIME.sub("", value).strip().casefold()
    if bare in _TODAY:
        return today_madrid(now)
    if bare in _YESTERDAY:
        return (_local(now).date() - timedelta(days=1)).isoformat()
    return None


def _days_ago(value: str, now: datetime | None) -> str | None:
    """"N days ago" / "hace N días" — relative to `now`, not the real clock."""
    match = _DAYS_AGO.match(value) or _HACE_DIAS.match(value)
    if match is None:
        return None
    return (_local(now).date() - timedelta(days=int(match.group(1)))).isoformat()


def _iso_date(value: str) -> str | None:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _day_words_date(value: str, now: datetime | None) -> str | None:
    """Only accept a result that reads the WHOLE phrase (``day_words``, backwards first: "15 march" is
    this year's, "friday" the latest one). A day that only reads forward ("tomorrow") is returned too,
    so the future-date guard in ``parse_spent_at`` can refuse it by name."""
    clock = _local(now)
    for direction in ("past", "forward"):
        reading = find_day(value, now=clock, direction=direction)
        if reading is not None and not (value[:reading.start] + value[reading.end:]).strip():
            return reading.day.isoformat()
    return None


def _resolve_spent_day(value: str, now: datetime | None) -> str | None:
    return (
        _named_day(value, now)
        or _days_ago(value, now)
        or _iso_date(value)
        or _day_words_date(value, now)
    )


def parse_spent_at(text: str | None, now: datetime | None = None) -> str:
    value = (text or "").strip()
    today = today_madrid(now)
    if not value:
        return today
    try:
        resolved = _resolve_spent_day(value, now)
    except OverflowError:   # "99999999999 days ago", "in 99999999 days": past the calendar's reach
        resolved = None
    if resolved is None:
        raise ValueError(f"I could not read a date in “{value}”. Try 2026-10-12 or yesterday.")
    if resolved > today:
        raise ValueError(f"“{value}” is a future date; the latest I can log is {today}.")
    return resolved
