"""Money values (M1 D7): amounts as Decimal, months as Madrid months."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from roost.money.amounts import amount_text, parse_amount
from roost.money.months import current_month, month_bounds, parse_spent_at, today_madrid


@pytest.mark.parametrize("raw", ["12,50", "12.50", 12.5, "12.5", "€12,50", " 12.50 "])
def test_amounts_accept_a_comma_decimal(raw):
    assert parse_amount(raw) == Decimal("12.50")
    assert amount_text(parse_amount(raw)) == "12.50"


@pytest.mark.parametrize("raw", ["1.234,56", "12.505", "0", "-3", "abc", "nan", "inf", "1000000.01"])
def test_bad_amounts_are_refused_with_a_reason(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_months_are_madrid_months():
    just_after_midnight = datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)   # 00:30 on 1 Nov in Madrid
    assert today_madrid(just_after_midnight) == "2026-11-01"
    assert current_month(just_after_midnight) == "2026-11"
    assert month_bounds("2026-12") == ("2026-12-01", "2027-01-01")
    with pytest.raises(ValueError):
        month_bounds("2026-13")


def test_spent_at_words_and_dates():
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    assert parse_spent_at(None, now) == "2026-10-13"
    assert parse_spent_at("yesterday", now) == "2026-10-12"
    assert parse_spent_at("ayer", now) == "2026-10-12"
    assert parse_spent_at("2026-10-01", now) == "2026-10-01"
    with pytest.raises(ValueError, match="date"):
        parse_spent_at("whenever", now)


def test_spent_at_yesterday_or_today_with_a_clock_time_keeps_the_day():
    # "yesterday at 9" must stay yesterday, not drift onto tomorrow because
    # only "at 9" got recognized by the forward-looking task-deadline parser.
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    assert parse_spent_at("yesterday at 9", now) == "2026-10-12"
    assert parse_spent_at("ayer a las 9", now) == "2026-10-12"
    assert parse_spent_at("today at 9pm", now) == "2026-10-13"
    assert parse_spent_at("hoy a las 21:00", now) == "2026-10-13"


def test_spent_at_n_days_ago():
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    assert parse_spent_at("2 days ago", now) == "2026-10-11"
    assert parse_spent_at("hace 2 días", now) == "2026-10-11"
    assert parse_spent_at("hace 2 dias", now) == "2026-10-11"


def test_spent_at_refuses_a_future_day():
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="future"):
        parse_spent_at("tomorrow", now)
    with pytest.raises(ValueError, match="future"):
        parse_spent_at("2026-10-20", now)


def test_spent_at_refuses_a_partially_read_phrase():
    # nl_time's day-of-month rule reads the bare "2" in "2 days ago" and
    # leaves "days ago" unread — must not silently land on the wrong day.
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="date"):
        parse_spent_at("sometime around 2 days ago-ish", now)


@pytest.mark.parametrize("text", ["99999999999 days ago", "hace 99999999999 días", "in 99999999 days"])
def test_spent_at_past_the_end_of_the_calendar_is_a_plain_refusal(text):
    with pytest.raises(ValueError, match="could not read a date"):    # not an OverflowError
        parse_spent_at(text)
