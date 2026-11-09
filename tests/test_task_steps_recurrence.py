"""Harvested checklist and recurrence helpers, on Roost's types and Madrid time."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from roost.tasks.recurrence import next_occurrence_fields, series_ended, validate_cron
from roost.tasks.steps import cascade_steps, steps_from_json, steps_from_titles, steps_to_json


def test_titles_become_open_steps_that_survive_a_json_round_trip():
    steps = steps_from_titles(["passport", " ", "charger"])
    assert [(s.title, s.done) for s in steps] == [("passport", False), ("charger", False)]
    assert steps_from_json(steps_to_json(steps)) == steps


def test_completing_a_task_ticks_open_steps_as_cascaded_and_keeps_real_ticks():
    first, second = steps_from_titles(["a", "b"])
    ticked = (replace(first, done=True, completed_at="2026-10-01T10:00:00+00:00"), second)
    done = cascade_steps(ticked)
    assert (done[0].cascaded, done[0].completed_at) == (False, "2026-10-01T10:00:00+00:00")
    assert (done[1].done, done[1].cascaded) == (True, True)


def test_a_weekly_task_comes_back_next_week_at_the_same_madrid_time():
    now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)          # a Monday, 12:00 Madrid
    due, reminder = next_occurrence_fields(
        "0 9 * * 1", orig_due="2026-10-12T09:00:00+02:00", orig_reminder="2026-10-12T07:00:00+00:00", now=now,
    )
    assert due == "2026-10-19T09:00:00+02:00"
    assert reminder == "2026-10-19T07:00:00+00:00"


def test_a_date_only_recurring_task_stays_date_only():
    now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    assert next_occurrence_fields("0 9 * * 1", orig_due="2026-10-12", orig_reminder=None, now=now)[0] == "2026-10-19"


def test_a_series_ends_after_its_last_day_in_madrid():
    assert series_ended("2026-10-19", "2026-10-19", "2026-10-19T19:00:00+00:00") is False   # 21:00 Madrid, same day
    assert series_ended("2026-10-19", "2026-10-26", None) is True
    assert series_ended(None, "2030-01-01", None) is False


def test_validate_cron_accepts_cron_and_refuses_prose():
    assert validate_cron("0 9 * * 1") == "0 9 * * 1"
    assert validate_cron(None) is None
    with pytest.raises(ValueError, match="cron"):
        validate_cron("every monday")
