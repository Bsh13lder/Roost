from datetime import date
from decimal import Decimal

import pytest

from roost.constants import PROJECT_COLORS
from roost.migrate.lazyclaw.values import (
    ValueAnomaly, cron_to_cadence, date_part, first_next_due, local_stamp, money, nearest_color,
    next_due_after, utc_stamp, currency,
)


@pytest.mark.parametrize("raw,expected", [
    (0.1 + 0.2, "0.30"), (12.5, "12.50"), (1e-9 + 5.0, "5.00"), (19.99, "19.99"),
    (100, "100.00"), (-7.25, "-7.25"), (0, "0.00"), (1234567.89, "1234567.89"),
])
def test_money_converts_through_repr_not_float(raw, expected):
    assert money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [0.005, 2.675, 1.234, 10.001, float("nan"), float("inf"), "x", True, None])
def test_money_drift_and_junk_are_anomalies(raw):
    with pytest.raises(ValueAnomaly):
        money(raw)


def test_currency():
    assert currency("EUR") == "EUR"
    assert currency(None, default="USD") == "USD"
    for bad in ("eur", "EU", "EURO", "E1R", "", None):
        with pytest.raises(ValueAnomaly):
            currency(bad)


@pytest.mark.parametrize("cron,expected", [
    ("0 0 1 * *", ("monthly", "1")), ("30 9 15 * *", ("monthly", "15")),
    ("0 9 * * 1", ("weekly", "1")), ("0 9 * * 7", ("weekly", "0")),
    ("0 0 5 3 *", ("yearly", "03-05")),
])
def test_cron_to_cadence(cron, expected):
    assert cron_to_cadence(cron) == expected


@pytest.mark.parametrize("cron", ["*/5 * * * *", "0 0 1,15 * *", "0 0 * * 1-5", "0 0 * * *",
                                  "0 0 32 * *", "0 0 1 13 *", "nonsense", "", "0 0 1 * 1"])
def test_cron_not_convertible(cron):
    assert cron_to_cadence(cron) is None


def test_next_due_after():
    assert next_due_after("monthly", "15", date(2026, 10, 20)) == date(2026, 11, 15)
    assert next_due_after("monthly", "15", date(2026, 10, 10)) == date(2026, 10, 15)
    assert next_due_after("monthly", "15", date(2026, 10, 15)) == date(2026, 11, 15)  # strictly after
    assert next_due_after("monthly", "31", date(2026, 1, 31)) == date(2026, 2, 28)
    assert next_due_after("monthly", "1", date(2026, 12, 20)) == date(2027, 1, 1)
    assert next_due_after("weekly", "1", date(2026, 10, 20)) == date(2026, 10, 26)  # Tue -> Mon
    assert next_due_after("weekly", "2", date(2026, 10, 20)) == date(2026, 10, 27)
    assert next_due_after("yearly", "03-05", date(2026, 10, 20)) == date(2027, 3, 5)
    assert next_due_after("yearly", "02-29", date(2027, 1, 1)) == date(2027, 2, 28)


def test_first_next_due_never_backfills():
    imp = date(2026, 10, 20)
    # charged on 1 Oct, import 20 Oct: next is 1 Nov, not a backfill of anything
    assert first_next_due("monthly", "1", "2026-10-01T00:00:05+00:00", imp) == date(2026, 11, 1)
    # a charge older than the import day is overridden by the import day
    assert first_next_due("monthly", "1", "2026-05-01 00:00:00", imp) == date(2026, 11, 1)
    # never charged
    assert first_next_due("monthly", "25", None, imp) == date(2026, 10, 25)
    # last charge in the "future" of the import day wins
    assert first_next_due("monthly", "1", "2026-10-25 00:00:00", imp) == date(2026, 11, 1)


def test_nearest_color():
    assert nearest_color(None) == PROJECT_COLORS[0]
    assert nearest_color("") == PROJECT_COLORS[0]
    assert nearest_color("junk") == PROJECT_COLORS[0]
    assert nearest_color("#ef4444") == "#ef4444"
    assert nearest_color("#FF0000") == "#ef4444"
    assert nearest_color("#0000ff") == "#3b82f6"
    assert nearest_color("#00f") == "#3b82f6"


def test_utc_stamp():
    assert utc_stamp("2026-03-04 05:06:07") == "2026-03-04T05:06:07+00:00"
    assert utc_stamp("2026-03-04T05:06:07+00:00") == "2026-03-04T05:06:07+00:00"
    assert utc_stamp("2026-03-04T05:06:07") == "2026-03-04T05:06:07+00:00"
    assert utc_stamp("2026-03-04T07:06:07+02:00") == "2026-03-04T05:06:07+00:00"
    assert utc_stamp("2026-03-04T05:06:07Z") == "2026-03-04T05:06:07+00:00"
    assert utc_stamp(None) is None and utc_stamp("") is None
    with pytest.raises(ValueAnomaly):
        utc_stamp("yesterday")


def test_local_stamp_and_date_part():
    assert local_stamp("2026-03-04T18:30:00") == "2026-03-04T18:30:00"  # copied as stored
    assert local_stamp("2026-03-04") == "2026-03-04"
    assert local_stamp("  ") is None and local_stamp(None) is None
    with pytest.raises(ValueAnomaly):
        local_stamp("soon")
    assert date_part("2026-03-04 05:06:07") == "2026-03-04"
    assert date_part("2026-03-04") == "2026-03-04"
    assert date_part(None) is None
    with pytest.raises(ValueAnomaly):
        date_part("04/03/2026")


def test_roost_anchor_is_a_date_that_keeps_the_day():
    from roost.migrate.lazyclaw.values import roost_anchor

    assert roost_anchor("monthly", "31", date(2027, 2, 28)) == date(2027, 1, 31)  # a month that has a 31st
    assert roost_anchor("monthly", "15", date(2026, 11, 15)) == date(2026, 11, 15)
    assert roost_anchor("weekly", "1", date(2026, 10, 26)) == date(2026, 10, 26)
    assert roost_anchor("yearly", "02-29", date(2027, 2, 28)) == date(2024, 2, 29)  # a leap year
    assert roost_anchor("yearly", "03-05", date(2027, 3, 5)) == date(2027, 3, 5)
