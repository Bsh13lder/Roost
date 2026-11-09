"""The safe date grammar (design 2026-10-20 §2): a number is a date only beside a month, d/m, ISO or "the"."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from roost.money.months import parse_spent_at
from tz_helpers import MADRID_TZ
from roost.tasks import nl_time
from roost.tasks.day_words import find_clock, find_day, guess_hour
from roost.tasks.quick_line import read_date

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=MADRID_TZ)     # a Tuesday


def _day(text: str, direction="forward"):
    reading = find_day(text, now=NOW, direction=direction)
    return None if reading is None else reading.day.isoformat()


@pytest.mark.parametrize("line", ["Buy 3 apples", "iPhone 15 case", "Room 101", "Groceries 45 eur",
                                  "Pay 1.200€ rent", "Item 2045", "Version 2.5"])
def test_lone_numbers_are_never_dates(line):
    assert find_day(line, now=NOW) is None
    due, rest = read_date(line)
    assert due.due_date is None and rest == line


def test_day_and_month_names_en_and_es():
    assert _day("15 march") == "2027-03-15"
    assert _day("3 de noviembre") == "2026-11-03"
    assert _day("march 15") == "2027-03-15"
    assert _day("15th of March") == "2027-03-15"
    assert _day("3 de noviembre de 2028") == "2028-11-03"
    reading = find_day("Nov 3 at 9:30", now=NOW)
    assert (reading.day.isoformat(), reading.time) == ("2026-11-03", time(9, 30))
    assert "Nov 3" == reading.words


def test_numeric_dates_are_day_first():
    assert _day("3/11") == "2026-11-03"
    assert _day("11/3") == "2027-03-11"
    assert _day("31/02") is None
    assert _day("2026-11-03") == "2026-11-03"
    assert _day("3/11/2027") == "2027-11-03"
    assert _day("3/11/27") is None


def test_named_days_and_pasado_manana():
    assert _day("pasado mañana") == "2026-10-22"
    assert _day("day after tomorrow") == "2026-10-22"
    assert _day("mañana") == "2026-10-21"
    parsed = nl_time.parse("Cena pasado mañana", tz=MADRID_TZ)
    assert parsed.remaining == "Cena"


def test_bare_weekdays_and_anchored_ones():
    assert _day("Friday") == "2026-10-23"
    assert _day("viernes") == "2026-10-23"
    assert _day("Tuesday") == "2026-10-27"
    assert _day("el viernes que viene") == "2026-10-23"
    assert _day("on sun") == "2026-10-25"
    assert _day("sun cream") == "2026-10-25"          # short forms are whole words (user ruling 2026-10-20)
    assert find_day("sunny cream", now=NOW) is None
    assert nl_time.parse("sunny cream", tz=MADRID_TZ).due_date is None


def test_week_and_month_phrases():
    assert _day("next week") == "2026-10-26"
    assert _day("la semana que viene") == "2026-10-26"
    assert _day("end of month") == "2026-10-31"
    assert _day("fin de mes") == "2026-10-31"
    assert _day("next month") == "2026-11-01"
    assert _day("el mes que viene") == "2026-11-01"
    assert _day("este finde") == "2026-10-24"
    assert _day("this weekend") == "2026-10-24"
    assert _day("end of week") == "2026-10-23"
    assert _day("the 15th") == "2026-11-15"
    assert _day("el día 15") == "2026-11-15"
    assert _day("el 25") == "2026-10-25"
    assert find_day("el 15 €", now=NOW) is None
    assert _day("in 2 weeks") == "2026-11-03"
    assert _day("en 2 semanas") == "2026-11-03"
    assert _day("in 2 months") == "2026-12-20"


def test_am_pm_guess():
    five = find_day("Call mom at 5", now=NOW)
    assert (five.day.isoformat(), five.time) == ("2026-10-20", time(17, 0))
    nine = find_day("Call mom at 9", now=NOW)
    assert (nine.day.isoformat(), nine.time) == ("2026-10-21", time(9, 0))
    night = find_day("Cena a las 9 de la noche", now=NOW)
    assert (night.day.isoformat(), night.time) == ("2026-10-20", time(21, 0))
    assert find_day("a las 15", now=NOW).time == time(15, 0)
    assert find_day("tomorrow at 9", now=NOW).time == time(9, 0)
    assert find_day("tomorrow 9pm", now=NOW).time == time(21, 0)
    assert find_day("tonight at 9", now=NOW).time == time(21, 0)
    assert find_clock("at noon").time == time(12, 0)
    assert find_clock("21:00").time == time(21, 0)


@pytest.mark.parametrize(("hour", "suffix", "expected"), [
    (5, None, 17), (9, None, 9), (12, None, 12), (15, None, 15), (9, "pm", 21), (12, "am", 0),
    (9, "mañana", 9), (9, "noche", 21), (12, "noche", 0), (3, "tarde", 15)])
def test_guess_hour(hour, suffix, expected):
    assert guess_hour(hour, suffix) == expected


def test_past_direction_for_expense_days():
    assert _day("ayer", "past") == "2026-10-19"
    assert _day("anteayer", "past") == "2026-10-18"
    assert _day("hace 3 días", "past") == "2026-10-17"
    assert _day("3 days ago", "past") == "2026-10-17"
    assert _day("el viernes pasado", "past") == "2026-10-16"
    assert _day("last friday", "past") == "2026-10-16"
    assert _day("friday", "past") == "2026-10-16"
    assert _day("15 march", "past") == "2026-03-15"
    assert _day("3/11", "past") == "2025-11-03"
    assert parse_spent_at("el viernes pasado", NOW) == "2026-10-16"
    assert parse_spent_at("15 march", NOW) == "2026-03-15"
    assert parse_spent_at("anteayer", NOW) == "2026-10-18"
    with pytest.raises(ValueError):
        parse_spent_at("tomorrow", NOW)


@pytest.mark.parametrize(("typed", "due", "title"), [
    ("Buy 3 apples", None, "Buy 3 apples"),
    ("15 march", "2027-03-15", ""),
    ("3/11", "2026-11-03", ""),
    ("11/3", "2027-03-11", ""),
    ("31/02", None, "31/02"),
    ("3 de noviembre", "2026-11-03", ""),
    ("pasado mañana", "2026-10-22", ""),
    ("Call mom at 5", "2026-10-20T17:00:00+02:00", "Call mom"),
    ("Call mom at 9", "2026-10-21T09:00:00+02:00", "Call mom"),
    ("Cena a las 9 de la noche", "2026-10-20T21:00:00+02:00", "Cena"),
    ("Friday", "2026-10-23", ""),
    ("viernes", "2026-10-23", ""),
    ("Tuesday", "2026-10-27", ""),
    ("next week", "2026-10-26", ""),
    ("fin de mes", "2026-10-31", ""),
    ("el mes que viene", "2026-11-01", ""),
    ("the 15th", "2026-11-15", ""),
    ("el día 15", "2026-11-15", ""),
    ("Nov 3 at 9:30", "2026-11-03T09:30:00+01:00", ""),
    ("en 2 semanas", "2026-11-03", ""),
    # owner, 2026-11-08: a time with no day and no "at" was dropped ("13:00", "10:00 am" stayed in the title)
    ("Call mom 15:00", "2026-10-20T15:00:00+02:00", "Call mom"),
    ("Call mom 13:00", "2026-10-21T13:00:00+02:00", "Call mom"),
    ("Call mom 10:00 am", "2026-10-21T10:00:00+02:00", "Call mom"),
    ("Call mom 10am", "2026-10-21T10:00:00+02:00", "Call mom"),
    ("Call mom 9 pm", "2026-10-20T21:00:00+02:00", "Call mom"),
    ("Dentist 9:30", "2026-10-21T09:30:00+02:00", "Dentist"),
    ("Buy 2 apples for 10", None, "Buy 2 apples for 10"),
])
def test_every_design_table_row(monkeypatch, typed, due, title):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr(nl_time, "datetime", FrozenDatetime)
    monkeypatch.setattr(nl_time, "_today_local", lambda tz=None: date(2026, 10, 20))
    got, rest = read_date(typed)
    assert (got.due_date, " ".join(rest.split())) == (due, title)


async def test_a_quick_line_reads_its_days_as_of_the_moment_it_was_given():
    # owner, 2026-11-08: a line the phone kept offline is read as of when it was typed (offline tasks O4)
    from roost.tasks.quick_line import read_quick_line

    class NoProjects:
        async def names(self, user_id):
            return ()

        async def resolve(self, *args, **kwargs):
            return None

    then = datetime(2026, 10, 20, 22, 0, tzinfo=MADRID_TZ)
    for text, due in (("Call mom tomorrow", "2026-10-21"), ("Call mom tomorrow at 10", "2026-10-21T10:00:00+02:00"),
                      ("Call mom 13:00", "2026-10-21T13:00:00+02:00"), ("Call mom in 2 days", "2026-10-22")):
        line = await read_quick_line(NoProjects(), "u", text, now=then)
        assert (line.due.due_date or "").startswith(due), text
