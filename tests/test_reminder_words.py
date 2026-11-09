"""A reminder speaks like a friend in the chat (owner, 2026-10-26, "like Grok"): the words depend only on which
reminder it is, never on chance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from roost.routines.reminder_words import reminder_text

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)      # Wednesday 21 October, 10:00 in Madrid


def _words(*, fire=NOW, base=NOW, due=None, title="Reply to Jin Hu"):
    return reminder_text(title, fire_at=fire, base_at=base, due_date=due)


@pytest.mark.parametrize(("minutes", "when"), [
    (30, "in 30 min"), (60, "in 1 h"), (90, "in 1 h 30 min"), (120, "in 2 h"), (600, "in 10 h"),
])
def test_an_advance_reminder_the_same_day_says_how_long(minutes, when):
    assert _words(base=NOW + timedelta(minutes=minutes)) == f"Heads-up: Reply to Jin Hu is {when}."


def test_an_advance_reminder_for_tomorrow_says_tomorrow_and_the_madrid_time():
    assert _words(base=NOW + timedelta(days=1)) == "Heads-up: Reply to Jin Hu is tomorrow at 10:00 Madrid."


def test_an_advance_reminder_further_out_names_the_day():
    assert _words(base=NOW + timedelta(days=2)) == "Heads-up: Reply to Jin Hu is on Friday 23 October at 10:00 Madrid."


def test_the_reminder_with_no_due_date_says_it_is_time():
    assert _words() == "It's time: Reply to Jin Hu (10:00 Madrid)."


def test_the_reminder_at_the_due_time_says_it_is_time():
    assert _words(due="2026-10-21T10:00") == "It's time: Reply to Jin Hu (10:00 Madrid)."


@pytest.mark.parametrize(("due", "when"), [
    ("2026-10-21", "today"),
    ("2026-10-21T17:30", "today at 17:30 Madrid"),
    ("2026-10-22", "tomorrow"),
    ("2026-10-22T09:00", "tomorrow at 09:00 Madrid"),
    ("2026-10-26", "on Monday 26 October"),
])
def test_the_reminder_before_a_later_due_says_when_it_is_due(due, when):
    assert _words(due=due) == f"Quick reminder: Reply to Jin Hu is due {when}."


def test_a_reminder_after_its_due_day_is_a_gentle_nudge():
    assert _words(due="2026-10-20") == "Gentle nudge: Reply to Jin Hu is still open."


def test_a_reminder_after_the_main_one_is_a_gentle_nudge():
    assert _words(base=NOW - timedelta(hours=2)) == "Gentle nudge: Reply to Jin Hu is still open."


def test_the_same_reminder_always_gets_the_same_words():
    assert {_words(due="2026-10-22") for _ in range(5)} == {"Quick reminder: Reply to Jin Hu is due tomorrow."}


# Owner, 2026-10-31: "Heads-up: Baptism ceremony is in 2 h" fired at 19:30 for a reminder at 21:30 while the
# ceremony was due tomorrow at 12:30. A heads-up names the task's due when it has one, never the reminder time.
def test_a_heads_up_before_an_evening_reminder_names_tomorrows_due():
    fire = datetime(2026, 10, 31, 18, 30, tzinfo=UTC)          # 19:30 Madrid
    base = datetime(2026, 10, 31, 20, 30, tzinfo=UTC)          # the reminder, 21:30 Madrid
    words = _words(fire=fire, base=base, due="2026-11-01T12:30:00+01:00", title="Baptism ceremony")
    assert words == "Heads-up: Baptism ceremony is tomorrow at 12:30 Madrid."


def test_a_heads_up_for_a_due_later_today_says_how_long_until_the_due():
    words = _words(base=NOW + timedelta(hours=1), due="2026-10-21T13:00:00+02:00")      # due 13:00 Madrid
    assert words == "Heads-up: Reply to Jin Hu is in 3 h."


def test_a_heads_up_for_a_due_day_without_a_time_names_the_day():
    words = _words(base=NOW + timedelta(hours=10), due="2026-10-22")
    assert words == "Heads-up: Reply to Jin Hu is tomorrow."


def test_a_heads_up_whose_due_already_passed_keeps_the_reminder_time():
    words = _words(base=NOW + timedelta(hours=2), due="2026-10-20T09:00:00+02:00")
    assert words == "Heads-up: Reply to Jin Hu is in 2 h."
