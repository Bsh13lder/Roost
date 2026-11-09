"""Pure value conversions for the LazyClaw importer. No I/O, no database."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from roost.constants import DEFAULT_PROJECT_COLOR, PROJECT_COLORS
from roost.migrate.lazyclaw.constants import (
    CADENCE_MONTHLY, CADENCE_WEEKLY, CADENCE_YEARLY, CENT, CURRENCY_LENGTH, DRIFT_LIMIT,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_HEX3 = re.compile(r"^#?([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$")
_HEX6 = re.compile(r"^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$")
_DAY_OF_MONTH = re.compile(r"^(?:[1-9]|[12]\d|3[01])$")
_MONTH = re.compile(r"^(?:[1-9]|1[0-2])$")
_WEEKDAY = re.compile(r"^[0-7]$")
_NUMBER = re.compile(r"^\d+$")


class ValueAnomaly(ValueError):
    """A LazyClaw value that cannot be imported as it stands. The report lists it."""


# --- money ---------------------------------------------------------------------------

def money(value: object) -> Decimal:
    """A LazyClaw ``REAL`` amount as cents. ``Decimal(repr(value))``, never ``Decimal(float)``.

    A value that is not within 0.000001 of its cent-rounded self is an anomaly.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueAnomaly(f"Not an amount: {type(value).__name__}.")
    try:
        exact = Decimal(repr(value))
    except InvalidOperation as exc:
        raise ValueAnomaly("Not an amount.") from exc
    if not exact.is_finite():
        raise ValueAnomaly("Amount is not a finite number.")
    cents = exact.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if abs(cents - exact) > DRIFT_LIMIT:
        raise ValueAnomaly(f"Amount {exact} does not fit in whole cents.")
    return cents


def currency(value: object, default: str | None = None) -> str:
    if value is None and default is not None:
        return default
    if (not isinstance(value, str) or len(value) != CURRENCY_LENGTH
            or not (value.isascii() and value.isalpha() and value.isupper())):
        raise ValueAnomaly("A currency must be 3 upper-case letters.")
    return value


# --- cron -> cadence --------------------------------------------------------------------

def cron_to_cadence(expression: str | None) -> tuple[str, str] | None:
    """``M H D * *`` monthly, ``M H * * W`` weekly, ``M H D Mo *`` yearly; anything else None.

    Returns ``(cadence, anchor_day)``: the day of the month ("15"), the weekday as 0-6 with
    Sunday 0 ("1"), or "MM-DD".
    """
    parts = (expression or "").split()
    if len(parts) != 5 or not (_NUMBER.match(parts[0]) and _NUMBER.match(parts[1])):
        return None
    _, _, dom, month, dow = parts
    if _DAY_OF_MONTH.match(dom) and month == "*" and dow == "*":
        return CADENCE_MONTHLY, str(int(dom))
    if dom == "*" and month == "*" and _WEEKDAY.match(dow):
        return CADENCE_WEEKLY, str(int(dow) % 7)
    if _DAY_OF_MONTH.match(dom) and _MONTH.match(month) and dow == "*":
        return CADENCE_YEARLY, f"{int(month):02d}-{int(dom):02d}"
    return None


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _next_monthly(day: int, after: date) -> date:
    candidate = _clamped(after.year, after.month, day)
    if candidate > after:
        return candidate
    year, month = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
    return _clamped(year, month, day)


def _next_weekly(weekday: int, after: date) -> date:
    # Python: Monday 0; cron: Sunday 0.
    cron_today = (after.weekday() + 1) % 7
    return after + timedelta(days=(weekday - cron_today) % 7 or 7)


def _next_yearly(anchor: str, after: date) -> date:
    month, day = (int(x) for x in anchor.split("-"))
    this_year = _clamped(after.year, month, day)
    return this_year if this_year > after else _clamped(after.year + 1, month, day)


def next_due_after(cadence: str, anchor_day: str, after: date) -> date:
    """The first occurrence strictly after ``after``."""
    if cadence == CADENCE_MONTHLY:
        return _next_monthly(int(anchor_day), after)
    if cadence == CADENCE_WEEKLY:
        return _next_weekly(int(anchor_day), after)
    if cadence == CADENCE_YEARLY:
        return _next_yearly(anchor_day, after)
    raise ValueAnomaly(f"Unknown cadence {cadence!r}.")


def first_next_due(cadence: str, anchor_day: str, last_charged_at: str | None, import_day: date) -> date:
    """First occurrence after ``max(last charge, import day)``: Roost never backfills a charge."""
    charged = date_part(last_charged_at)
    floor = max(date.fromisoformat(charged), import_day) if charged else import_day
    return next_due_after(cadence, anchor_day, floor)


# --- colour ------------------------------------------------------------------------------

def _rgb(text: str) -> tuple[int, int, int] | None:
    short, long = _HEX3.match(text), _HEX6.match(text)
    if short:
        return tuple(int(c * 2, 16) for c in short.groups())  # type: ignore[return-value]
    if long:
        return tuple(int(c, 16) for c in long.groups())  # type: ignore[return-value]
    return None


def nearest_color(value: str | None) -> str:
    """The nearest ``PROJECT_COLORS`` entry; None or junk gives the first."""
    rgb = _rgb((value or "").strip())
    if rgb is None:
        return DEFAULT_PROJECT_COLOR

    def distance(palette_hex: str) -> int:
        other = _rgb(palette_hex) or (0, 0, 0)
        return sum((a - b) ** 2 for a, b in zip(rgb, other))

    return min(PROJECT_COLORS, key=distance)


# --- timestamps ------------------------------------------------------------------------------

def _parse(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueAnomaly("Not a date or time.") from exc


def utc_stamp(value: str | None) -> str | None:
    """A LazyClaw stamp ("YYYY-MM-DD HH:MM:SS", UTC, or ISO) as ISO UTC with +00:00."""
    if value is None or not value.strip():
        return None
    parsed = _parse(value)
    aware = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    return aware.astimezone(timezone.utc).isoformat()


def local_stamp(value: str | None) -> str | None:
    """Due dates and reminders are copied as stored (a naive time is the local wall clock)."""
    if value is None or not value.strip():
        return None
    _parse(value)
    return value.strip()


def date_part(value: str | None) -> str | None:
    """The ``YYYY-MM-DD`` part of a stored date or stamp."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    if not _DATE_RE.match(text):
        raise ValueAnomaly("Not a date.")
    try:
        date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueAnomaly("Not a date.") from exc
    return text[:10]


def roost_anchor(cadence: str, anchor_day: str, next_due: date) -> date:
    """Roost's ``money_recurring.anchor_day`` is a date that carries the rule's day (monthly: the day
    of the month; weekly: the weekday; yearly: month and day). ``next_due`` is such a date unless a
    short month clamped it, so a day-31 rule is anchored in a month that has a 31st."""
    if cadence == CADENCE_WEEKLY:
        return next_due
    if cadence == CADENCE_MONTHLY:
        day, year, month = int(anchor_day), next_due.year, next_due.month
        while calendar.monthrange(year, month)[1] < day:
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        return date(year, month, day)
    month, day = (int(x) for x in anchor_day.split("-"))
    year = next_due.year
    while calendar.monthrange(year, month)[1] < day:
        year -= 1
    return date(year, month, day)
