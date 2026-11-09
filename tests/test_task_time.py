"""Dates on Europe/Madrid time (M1 D6) — the harvested nl_time behind parse_due."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from tz_helpers import MADRID_TZ
from roost.tasks import nl_time
from roost.tasks.due import build_schedule, parse_due
from roost.tasks.reminders import resolve_pre_reminders


def _madrid(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=MADRID_TZ)


def test_tomorrow_at_9_is_a_timed_due_with_its_reminder():
    tomorrow = datetime.now(MADRID_TZ).date() + timedelta(days=1)
    due = parse_due("tomorrow at 9")
    assert due.due_date == _madrid(tomorrow, 9).isoformat()
    assert due.reminder_at == _madrid(tomorrow, 9).astimezone(timezone.utc).isoformat()


def test_tomorrow_at_9_across_the_dst_change(monkeypatch):
    monkeypatch.setattr(nl_time, "_today_local", lambda tz=None: date(2026, 10, 24))
    due = parse_due("tomorrow at 9")
    assert due.due_date == "2026-10-25T09:00:00+01:00"        # winter time from 25 Oct 2026
    assert due.reminder_at == "2026-10-25T08:00:00+00:00"


def test_a_date_only_due_stays_date_only():
    assert (parse_due("2026-10-20").due_date, parse_due("2026-10-20").reminder_at) == ("2026-10-20", None)
    tomorrow = (datetime.now(MADRID_TZ).date() + timedelta(days=1)).isoformat()
    assert (parse_due("tomorrow").due_date, parse_due("tomorrow").reminder_at) == (tomorrow, None)


def test_a_naive_iso_time_is_madrid_wall_clock():
    due = parse_due("2026-12-01T18:30")
    assert (due.due_date, due.reminder_at) == ("2026-12-01T18:30:00+01:00", "2026-12-01T17:30:00+00:00")


def test_an_unreadable_due_is_refused():
    with pytest.raises(ValueError, match="could not read a date"):
        parse_due("someday-ish")


def test_no_due_is_no_due():
    assert (parse_due(None).due_date, parse_due("  ").reminder_at) == (None, None)


def test_a_timed_due_gets_a_30_minute_advance_reminder_by_default():
    schedule = build_schedule("2026-12-01T09:00", None, None)
    assert schedule.pre_reminders == ("2026-12-01T07:30:00+00:00",)
    assert build_schedule("2026-12-01T09:00", None, []).pre_reminders == ()
    assert build_schedule("2026-12-01", None, None).pre_reminders == ()


def test_explicit_offsets_and_a_bad_offset():
    assert resolve_pre_reminders(["-2h", "-30m"], "2026-12-01T08:00:00+00:00") == (
        "2026-12-01T06:00:00+00:00", "2026-12-01T07:30:00+00:00",
    )
    with pytest.raises(ValueError, match="offset"):
        resolve_pre_reminders(["soonish"], "2026-12-01T08:00:00+00:00")
    with pytest.raises(ValueError, match="reminder time"):
        resolve_pre_reminders(["-30m"], None)


@pytest.mark.parametrize("text", ["in 99999999 days", "9999-12-31T23:59:59+00:00", "0001-01-01T00:00:00+23:59"])
def test_a_day_past_the_end_of_the_calendar_is_a_plain_refusal(text):
    with pytest.raises(ValueError, match="could not read a date"):    # not an OverflowError
        parse_due(text)



@pytest.mark.parametrize("due", ["0001-01-01T00:00", "0001-01-01T00:20:00+00:00"])
def test_a_due_in_the_calendars_first_hour_is_a_plain_refusal_not_an_overflow(due):
    """Redesign P3 leftover: the default advance reminder (30 minutes before) used to underflow to a 500."""
    with pytest.raises(ValueError, match="before the first day of the calendar"):
        build_schedule(due, None, None)
    assert build_schedule(due, None, []).pre_reminders == ()


@pytest.mark.parametrize("text, minutes", [("in 1h", 60), ("in 2hrs", 120), ("in 30m", 30), ("in 45 min", 45)])
def test_short_units_set_a_reminder_that_far_ahead(text, minutes):
    """Owner, 2026-10-26: "buy milk, remind me after 1 hr" -- "in 1h" was read as today with no time, so no reminder."""
    due = parse_due(text)
    assert due.reminder_at is not None
    ahead = datetime.fromisoformat(due.reminder_at) - datetime.now(timezone.utc)
    assert abs(ahead - timedelta(minutes=minutes)) < timedelta(minutes=1)
