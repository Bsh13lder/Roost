"""Richer repeat words (Amendment T): every other X, every N units, every!/when done."""

from __future__ import annotations

import pytest

from roost.tasks.repeat_rule import RepeatRule, rule_json
from roost.tasks.repeat_words import find_repeat, readable


def _rule(**fields) -> str:
    return rule_json(RepeatRule(**fields))


@pytest.mark.parametrize(("typed", "rule"), [
    ("every other day", dict(every=2, unit="day")),
    ("every 3 days", dict(every=3, unit="day")),
    ("every 2 weeks", dict(every=2, unit="week")),
    ("every other week", dict(every=2, unit="week")),
    ("every 2 months", dict(every=2, unit="month")),
    ("every other month", dict(every=2, unit="month")),
    ("every 2 years", dict(every=24, unit="month")),
    ("cada 2 semanas", dict(every=2, unit="week")),
    ("cada otro día", dict(every=2, unit="day")),
    ("cada 10 días", dict(every=10, unit="day")),
    ("every other Monday", dict(every=2, unit="week", weekday=0)),
    ("cada otro lunes", dict(every=2, unit="week", weekday=0)),
    ("every! Monday", dict(every=1, unit="week", weekday=0, from_completion=True)),
    ("every! 3 days", dict(every=3, unit="day", from_completion=True)),
    ("every! day", dict(every=1, unit="day", from_completion=True)),
    ("every! other week", dict(every=2, unit="week", from_completion=True)),
    ("every day when done", dict(every=1, unit="day", from_completion=True)),
    ("every 3 days when done", dict(every=3, unit="day", from_completion=True)),
    ("every month when done", dict(every=1, unit="month", from_completion=True)),
    ("every Monday when done", dict(every=1, unit="week", weekday=0, from_completion=True)),
])
def test_rich_repeats_become_a_rule(typed, rule):
    found = find_repeat(f"Water plants {typed} now", due_hint=None)
    assert found.problem is None and found.rule == _rule(**rule)
    assert found.words == typed


def test_a_weekday_rule_also_has_a_cron_for_its_first_day():
    found = find_repeat("Gym every other Monday at 7am", due_hint=None)
    assert found.cron == "0 7 * * 1" and found.words == "every other Monday at 7am"
    assert find_repeat("Gym every 3 days", due_hint=None).cron is None


def test_a_clock_goes_with_the_words_and_when_done_follows_it():
    found = find_repeat("Pills every 2 days at 8am when done", due_hint=None)
    assert found.words == "every 2 days at 8am when done" and found.clock == (8, 0)
    assert found.rule == _rule(every=2, unit="day", from_completion=True)


@pytest.mark.parametrize("typed", [
    "every other weekday", "every 2 mondays", "every! weekday", "every Monday and Thursday when done",
    "every 0 days", "every 400 days", "yearly when done",
])
def test_what_a_rule_cannot_say_is_a_problem(typed):
    found = find_repeat(typed, due_hint=None)
    assert found.rule is None and found.cron is None and found.problem


def test_plain_repeats_are_unchanged():
    found = find_repeat("every Monday", due_hint=None)
    assert (found.cron, found.rule) == ("0 9 * * 1", None)
    assert find_repeat("every Monday and Thursday", due_hint=None).cron == "0 9 * * 1,4"


def test_readable_reads_a_rule():
    assert readable(find_repeat("every other Monday", due_hint=None).rule) == "every other Monday"
