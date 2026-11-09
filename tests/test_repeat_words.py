"""Repeat words (design 2026-10-20 §3) become a Madrid cron, and read back."""

from __future__ import annotations

import pytest

from roost.tasks.due import Due
from roost.tasks.repeat_words import REPEAT_PROBLEM_TEXT, find_repeat, readable

NO_HINT = None


def _cron(text: str, hint: Due | None = NO_HINT) -> str | None:
    found = find_repeat(text, due_hint=hint)
    return None if found is None else found.cron


@pytest.mark.parametrize(("typed", "cron"), [
    ("daily", "0 9 * * *"), ("every day", "0 9 * * *"), ("cada día", "0 9 * * *"), ("todos los días", "0 9 * * *"),
    ("weekdays", "0 9 * * 1-5"), ("every weekday", "0 9 * * 1-5"), ("entre semana", "0 9 * * 1-5"),
    ("laborables", "0 9 * * 1-5"),
    ("weekly", "0 9 * * 1"), ("semanal", "0 9 * * 1"), ("cada semana", "0 9 * * 1"),
    ("monthly", "0 9 1 * *"), ("mensual", "0 9 1 * *"), ("cada mes", "0 9 1 * *"),
    ("yearly", "0 9 1 1 *"), ("anual", "0 9 1 1 *"), ("cada año", "0 9 1 1 *"),
])
def test_daily_weekdays_weekly_monthly_yearly_en_es(typed, cron):
    found = find_repeat(f"Water plants {typed}", due_hint=NO_HINT)
    assert (found.cron, found.problem, found.words) == (cron, None, typed)


def test_the_span_covers_exactly_the_words():
    text = "Water plants every day at 7am please"
    found = find_repeat(text, due_hint=NO_HINT)
    assert text[found.start:found.end] == found.words == "every day at 7am"


def test_every_monday_and_thursday():
    assert _cron("every Monday and Thursday") == "0 9 * * 1,4"
    assert _cron("cada lunes y jueves") == "0 9 * * 1,4"
    assert _cron("todos los lunes") == "0 9 * * 1"
    assert _cron("every Sunday") == "0 9 * * 0"
    assert _cron("every Friday, Monday") == "0 9 * * 1,5"


def test_monthly_on_the_1st():
    assert _cron("monthly on the 1st") == "0 9 1 * *"
    assert _cron("every month on the 15th") == "0 9 15 * *"
    assert _cron("el día 1 de cada mes") == "0 9 1 * *"
    assert _cron("cada mes el 20") == "0 9 20 * *"
    assert find_repeat("monthly on the 40th", due_hint=NO_HINT).problem == REPEAT_PROBLEM_TEXT
    assert _cron("yearly on 15 March") == "0 9 15 3 *"


def test_repeat_at_a_time():
    assert _cron("every day at 7") == "0 19 * * *"                 # the PM guess
    assert _cron("every day at 7am") == "0 7 * * *"
    assert _cron("cada día a las 8") == "0 8 * * *"
    assert _cron("every Monday at 09:30") == "30 9 * * 1"
    assert _cron("weekdays 8:15") == "15 8 * * 1-5"


def test_the_due_hint_gives_the_time_and_the_day():
    timed = Due("2026-10-28T07:30:00+01:00", None)             # a Wednesday
    assert _cron("daily", timed) == "30 7 * * *"
    assert _cron("weekly", timed) == "30 7 * * 3"
    assert _cron("monthly", timed) == "30 7 28 * *"
    assert _cron("yearly", timed) == "30 7 28 10 *"
    assert _cron("weekly", Due("2026-11-01", None)) == "0 9 * * 0"      # a Sunday, day-only: 09:00
    assert _cron("every Friday", timed) == "30 7 * * 5"


def test_unsayable_repeats_are_a_problem():
    for typed in ("every other weekday", "every 2 mondays", "every 500 days"):
        found = find_repeat(f"Clean {typed}", due_hint=NO_HINT)
        assert (found.cron, found.problem, found.words) == (None, REPEAT_PROBLEM_TEXT, typed)


def test_no_repeat_words_is_none():
    assert find_repeat("Buy milk tomorrow", due_hint=NO_HINT) is None
    assert find_repeat("The daily planet", due_hint=NO_HINT) is not None     # words, not meaning: the chip's × undoes it


@pytest.mark.parametrize(("cron", "words"), [
    ("0 9 * * *", "every day 09:00"), ("0 9 * * 1-5", "every weekday 09:00"),
    ("0 9 * * 1", "every Monday 09:00"), ("30 7 * * 1,4", "every Monday and Thursday 07:30"),
    ("0 8 * * 0,2,6", "every Sunday, Tuesday and Saturday 08:00"),
    ("0 9 1 * *", "every month on the 1st 09:00"), ("0 9 22 * *", "every month on the 22nd 09:00"),
    ("0 9 11 * *", "every month on the 11th 09:00"), ("15 19 15 3 *", "every year on 15 March 19:15"),
    ("0 5 * * *", "every day 05:00"),
])
def test_readable_round_trips(cron, words):
    assert readable(cron) == words
    assert _cron(words) == cron


def test_a_cron_it_cannot_say_is_returned_as_it_is():
    assert readable("*/5 * * * *") == "*/5 * * * *"
    assert readable("0 9 1 * 1") == "0 9 1 * 1"
