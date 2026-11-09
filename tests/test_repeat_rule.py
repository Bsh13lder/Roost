"""The richer repeat rule (Amendment T): validated JSON kept in the task's `recurring` text."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from tz_helpers import MADRID_TZ
from roost.tasks.recurrence import next_occurrence_fields, validate_cron
from roost.tasks.repeat_rule import RepeatRule, is_rule, next_day, parse_rule, readable_rule, rule_json
from roost.tasks.repeat_words import readable


def test_round_trip_is_canonical_json():
    text = rule_json(RepeatRule(every=2, unit="week", weekday=0))
    assert text == '{"v":1,"every":2,"unit":"week","weekday":0,"from_completion":false}'
    assert parse_rule(text) == RepeatRule(every=2, unit="week", weekday=0)
    assert is_rule(text) and not is_rule("0 9 * * 1")


@pytest.mark.parametrize("bad", [
    "{", "[]", '{"v":2,"every":1,"unit":"day"}', '{"v":1,"every":0,"unit":"day"}',
    '{"v":1,"every":1000,"unit":"day"}', '{"v":1,"every":1,"unit":"hour"}',
    '{"v":1,"every":1,"unit":"day","weekday":1}', '{"v":1,"every":1,"unit":"week","weekday":7}',
    '{"v":1,"every":1,"unit":"day","extra":1}', '{"v":1,"every":true,"unit":"day"}',
])
def test_bad_rules_are_refused_in_plain_words(bad):
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_validate_cron_accepts_a_rule_and_keeps_crons():
    text = '{"v":1,"every":3,"unit":"day","from_completion":true}'
    assert validate_cron(text) == rule_json(parse_rule(text))
    assert validate_cron(" 0 9 * * 1 ") == "0 9 * * 1"
    with pytest.raises(ValueError):
        validate_cron('{"v":1,"every":0,"unit":"day"}')


@pytest.mark.parametrize(("rule", "start", "expected"), [
    (RepeatRule(every=3, unit="day"), date(2026, 10, 20), date(2026, 10, 23)),
    (RepeatRule(every=2, unit="week"), date(2026, 10, 20), date(2026, 11, 3)),
    (RepeatRule(every=2, unit="week", weekday=0), date(2026, 10, 19), date(2026, 11, 2)),
    (RepeatRule(every=2, unit="week", weekday=0), date(2026, 10, 21), date(2026, 11, 2)),   # from a Wednesday
    (RepeatRule(every=1, unit="week", weekday=0), date(2026, 10, 19), date(2026, 10, 26)),
    (RepeatRule(every=1, unit="month"), date(2026, 1, 31), date(2026, 2, 28)),
    (RepeatRule(every=2, unit="month"), date(2026, 10, 20), date(2026, 12, 20)),
])
def test_next_day(rule, start, expected):
    assert next_day(rule, start) == expected


def test_readable():
    assert readable_rule(RepeatRule(every=2, unit="week", weekday=0)) == "every other Monday"
    assert readable_rule(RepeatRule(every=2, unit="day")) == "every other day"
    assert readable_rule(RepeatRule(every=3, unit="week")) == "every 3 weeks"
    assert readable_rule(RepeatRule(every=1, unit="month", from_completion=True)) == "every month, when done"
    assert readable(rule_json(RepeatRule(every=3, unit="day"))) == "every 3 days"


NOW = datetime(2026, 10, 20, 14, 0, tzinfo=MADRID_TZ).astimezone(timezone.utc)


def test_due_based_interval_follows_the_old_due():
    rule = rule_json(RepeatRule(every=3, unit="day"))
    due, rem = next_occurrence_fields(rule, orig_due="2026-10-19", orig_reminder=None, now=NOW)
    assert (due, rem) == ("2026-10-22", None)          # 19 -> 22, in the future


def test_due_based_interval_skips_dates_already_past():
    rule = rule_json(RepeatRule(every=3, unit="day"))
    due, _ = next_occurrence_fields(rule, orig_due="2026-10-01", orig_reminder=None, now=NOW)
    assert due == "2026-10-22"                          # 1,4,...,19 are past; 22 is next


def test_from_completion_counts_from_today():
    rule = rule_json(RepeatRule(every=3, unit="day", from_completion=True))
    due, _ = next_occurrence_fields(rule, orig_due="2026-10-01", orig_reminder=None, now=NOW)
    assert due == "2026-10-23"


def test_timed_due_keeps_its_time_of_day():
    rule = rule_json(RepeatRule(every=1, unit="week", from_completion=True))
    due, _ = next_occurrence_fields(rule, orig_due="2026-10-14T18:30:00+02:00", orig_reminder=None, now=NOW)
    assert due == "2026-10-27T18:30:00+01:00"


def test_every_other_monday_from_completion():
    rule = rule_json(RepeatRule(every=2, unit="week", weekday=0, from_completion=True))
    due, _ = next_occurrence_fields(rule, orig_due="2026-10-19", orig_reminder=None, now=NOW)
    assert due == "2026-11-02"


from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_the_next_occurrence_carries_the_star_the_estimate_and_follows_the_rule():
    c = _client()
    rule = rule_json(RepeatRule(every=3, unit="day", from_completion=True))
    made = c.post("/api/tasks", json={"title": "Water", "due_date": "2026-10-19", "recurring": rule,
                                      "starred": True, "estimate_minutes": 45}, headers=O)
    assert made.status_code in (200, 201), made.text
    assert made.json()["recurring"] == rule and made.json()["repeat_text"] == "every 3 days, when done"
    done = c.post(f"/api/tasks/{made.json()['id']}/complete", headers=O)
    assert done.status_code == 200, done.text
    (nxt,) = c.get("/api/tasks", headers=O).json()
    assert nxt["recurring"] == rule and nxt["starred"] is True and nxt["estimate_minutes"] == 45
    assert nxt["due_date"] > "2026-10-19"


def test_a_bad_rule_over_http_is_a_422():
    c = _client()
    made = c.post("/api/tasks", json={"title": "x", "recurring": '{"v":1,"every":0,"unit":"day"}'}, headers=O)
    assert made.status_code == 422
