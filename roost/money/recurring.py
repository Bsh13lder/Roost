"""Repeating expenses, pure (Task 12, design §5).

A rule repeats on its anchor: weekly on the anchor's weekday, monthly on its day of the month (a short month
takes its last day, so "the 31st" is 28 Feb, 31 Mar, 30 Apr), yearly on its month and day (29 Feb is 28 Feb in a
common year). ``next_due`` is the next occurrence not yet made; the lazy catch-up (``recurring_store``) makes
every occurrence up to today and moves ``next_due`` past them."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from roost.constants import RECURRING_CADENCES
from roost.money.amounts import amount_text

WEEKLY, MONTHLY, YEARLY = RECURRING_CADENCES
_WEEK = 7


@dataclass(frozen=True)
class Recurring:
    """One row of ``money_recurring``. ``amount``, ``description``, ``vendor`` and ``cadence`` are ``enc:v2`` in
    the table; the days are plaintext ISO dates."""

    id: str
    user_id: str
    project_id: str
    amount: Decimal
    currency: str
    description: str | None
    vendor: str | None
    cadence: str
    anchor_day: str                 # YYYY-MM-DD: carries the weekday, the day of the month, or month and day
    next_due: str                   # YYYY-MM-DD: the next charge not made yet
    ends_on: str | None             # YYYY-MM-DD: the last day a charge may fall on
    created_at: str
    updated_at: str
    created_by_bot: str | None
    tainted: bool


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_occurrence(cadence: str, anchor_day: date, after: date) -> date:
    """The first occurrence of the rule strictly after ``after`` (never before the anchor itself)."""
    if after < anchor_day:
        return anchor_day
    if cadence == WEEKLY:
        return anchor_day + timedelta(days=_WEEK * ((after - anchor_day).days // _WEEK + 1))
    if cadence == MONTHLY:
        year, month = after.year, after.month
        while (found := _clamped(year, month, anchor_day.day)) <= after:
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return found
    if cadence == YEARLY:
        year = after.year
        while (found := _clamped(year, anchor_day.month, anchor_day.day)) <= after:
            year += 1
        return found
    raise ValueError(f"“{cadence}” is not a cadence: use weekly, monthly or yearly.")


def occurrences(rule: Recurring, through: date, limit: int) -> tuple[date, ...]:
    """The rule's occurrences from ``next_due`` up to ``through`` (inclusive) and ``ends_on``, at most ``limit``."""
    anchor, current = date.fromisoformat(rule.anchor_day), date.fromisoformat(rule.next_due)
    last = through if rule.ends_on is None else min(through, date.fromisoformat(rule.ends_on))
    found: list[date] = []
    while current <= last and len(found) < limit:
        found.append(current)
        current = next_occurrence(rule.cadence, anchor, current)
    return tuple(found)


@dataclass(frozen=True)
class UpcomingCharge:
    """A charge that is coming (not made yet): "Upcoming charges"."""

    recurring_id: str
    project_id: str
    day: str                        # YYYY-MM-DD
    amount: Decimal
    currency: str
    note: str | None


def upcoming_out(charge: UpcomingCharge) -> dict[str, Any]:
    return {"recurring_id": charge.recurring_id, "project_id": charge.project_id, "day": charge.day,
            "amount": amount_text(charge.amount), "currency": charge.currency, "note": charge.note}


def recurring_out(rule: Recurring, project: str = "", *, paused: bool = False) -> dict[str, Any]:
    """``RecurringOut``: amounts as strings. ``paused``: its project is archived."""
    return {"id": rule.id, "project_id": rule.project_id, "project": project, "amount": amount_text(rule.amount),
            "currency": rule.currency, "note": rule.description, "vendor": rule.vendor, "cadence": rule.cadence,
            "anchor_day": rule.anchor_day, "next_due": rule.next_due, "ends_on": rule.ends_on, "paused": paused,
            "created_at": rule.created_at, "tainted": rule.tainted}
