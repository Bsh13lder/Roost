"""The quick line's tokens (design 2026-10-20 §3): priority, star, estimate, reminder, amount."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from tz_helpers import MADRID_TZ
from roost.tasks.due import Due
from roost.tasks.line_tokens import read_amount_words, read_tokens, reminder_from

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=MADRID_TZ)


@pytest.mark.parametrize(("typed", "level"), [
    ("Pay rent !!!", "urgent"), ("Pay rent !!", "high"), ("Pay rent !", "medium"), ("Pay rent !-", "low"),
    ("Pay rent !alta", "high"), ("Pay rent !baja", "low"), ("Pay rent !urgente", "urgent"),
    ("Pay rent !medium", "medium"), ("Pay rent !Low", "low"),
])
def test_priority_shorthand(typed, level):
    tokens = read_tokens(typed)
    assert (tokens.priority, tokens.rest) == (level, "Pay rent")


def test_priority_words_only_at_the_edges():
    assert read_tokens("Pagar luz urgente").priority == "urgent"
    assert read_tokens("Pagar luz urgente").rest == "Pagar luz"
    assert read_tokens("asap call Ana").priority == "urgent"
    kept = read_tokens("dar de baja el seguro")
    assert (kept.priority, kept.rest) == (None, "dar de baja el seguro")
    assert read_tokens("urgent care appointment").priority == "urgent"       # first word: documented
    assert read_tokens("Plan urgent trip").priority is None                  # middle word
    assert read_tokens("urgent").rest == "urgent"                            # a lone word is the title


def test_two_priorities_last_wins_with_a_warning():
    tokens = read_tokens("Dinner 30€ !high !low")
    assert (tokens.priority, tokens.rest) == ("low", "Dinner")
    assert tokens.warnings == ("Two priorities: kept !low.",)


def test_star_tokens():
    for typed in ("Call Ana *", "* Call Ana", "Call Ana !star", "Call Ana !fav"):
        tokens = read_tokens(typed)
        assert (tokens.star, tokens.rest) == (True, "Call Ana")
    assert read_tokens("5 * 3 table").star is True        # a lone * is a star by design
    assert read_tokens("2*3").star is False


@pytest.mark.parametrize(("typed", "minutes"), [
    ("~30m", 30), ("~2h", 120), ("~1h30", 90), ("~90min", 90), ("~1,5h", 90), ("~1.5h", 90), ("~45 min", 45)])
def test_estimates(typed, minutes):
    tokens = read_tokens(f"Paint wall {typed}")
    assert (tokens.estimate_minutes, tokens.rest, tokens.warnings) == (minutes, "Paint wall", ())


def test_unusable_estimates_warn_and_their_words_stay():
    for typed in ("~0m", "~9999h"):
        tokens = read_tokens(f"Paint {typed}")
        assert tokens.estimate_minutes is None and typed in tokens.rest and len(tokens.warnings) == 1
    two = read_tokens("Paint ~1h ~2h")
    assert (two.estimate_minutes, two.rest) == (120, "Paint") and "Two estimates" in two.warnings[0]


def test_reminders():
    assert read_tokens("Call ^9am").reminder_words == "^9am"
    assert read_tokens("Call ^17:30").rest == "Call"
    assert read_tokens("Call ^1h before").reminder_words == "^1h before"
    assert read_tokens("Call ^30m antes").reminder_words == "^30m antes"
    assert read_tokens("Call remind me at 9").reminder_words == "remind me at 9"
    assert read_tokens("Call avísame 1h antes").reminder_words == "avísame 1h antes"
    assert read_tokens("Call recuérdame a las 9").rest == "Call"


def test_reminder_moments():
    timed = Due("2026-12-01T10:00:00+01:00", "2026-12-01T09:00:00+00:00")
    assert reminder_from("^1h before", timed, now=NOW) == "2026-12-01T08:00:00+00:00"
    assert reminder_from("^30m antes", timed, now=NOW) == "2026-12-01T08:30:00+00:00"
    assert reminder_from("^9am", timed, now=NOW) == "2026-12-01T08:00:00+00:00"
    assert reminder_from("remind me at 9", timed, now=NOW) == "2026-12-01T08:00:00+00:00"
    assert reminder_from("^1h", timed, now=NOW) == "2026-12-01T08:00:00+00:00"
    day_only = Due("2026-12-01", None)
    assert reminder_from("^1h before", day_only, now=NOW) == "2026-12-01T07:00:00+00:00"      # from 09:00 Madrid
    assert reminder_from("^1h30 before", day_only, now=NOW) == "2026-12-01T06:30:00+00:00"
    assert reminder_from("^17:30", day_only, now=NOW) == "2026-12-01T16:30:00+00:00"
    assert reminder_from("^9am", Due(None, None), now=NOW) == "2026-10-21T07:00:00+00:00"     # next 9am
    assert reminder_from("^5pm", Due(None, None), now=NOW) == "2026-10-20T15:00:00+00:00"


def test_a_reminder_before_with_no_due_is_a_plain_sentence():
    with pytest.raises(ValueError, match="“\\^1h before” needs a due date."):
        reminder_from("^1h before", Due(None, None), now=NOW)
    with pytest.raises(ValueError, match="could not read a time"):
        reminder_from("^soon", Due(None, None), now=NOW)


@pytest.mark.parametrize(("typed", "value", "currency"), [
    ("1.200€", "1200.00", "EUR"), ("€1,200.50", "1200.50", "EUR"), ("1.200,50€", "1200.50", "EUR"),
    ("£12,50", "12.50", "GBP"), ("$12.5", "12.50", "USD"), ("€200", "200.00", "EUR"), ("200€", "200.00", "EUR"),
    ("€1.200.000", "1200000.00", "EUR"), ("€ 30", "30.00", "EUR")])
def test_amounts_with_thousands(typed, value, currency):
    assert read_amount_words(f"Pay {typed} rent") == (Decimal(value), currency, typed)
    tokens = read_tokens(f"Pay {typed} rent")
    assert (tokens.amount, tokens.currency, tokens.rest) == (Decimal(value), currency, "Pay rent")


@pytest.mark.parametrize("typed", ["1,2345€", "€1.2.3", "€12,345,67", "45 eur"])
def test_odd_amounts_are_not_read(typed):
    assert read_amount_words(f"Pay {typed}") is None


def test_vendor_and_skip():
    tokens = read_tokens('€12 lunch vendor:"El Corte Inglés"')
    assert tokens.vendor == "El Corte Inglés" and tokens.rest == "lunch"
    assert read_tokens("€12 lunch tienda:Mercadona").vendor == "Mercadona"
    skipped = read_tokens("Pay €5 !high *", frozenset({"amount", "priority", "star"}))
    assert (skipped.amount, skipped.priority, skipped.star, skipped.rest) == (None, None, False, "Pay €5 !high *")


def test_the_whole_line_in_order():
    tokens = read_tokens("Call plumber !! * ~1h ^30m before €200")
    assert (tokens.priority, tokens.star, tokens.estimate_minutes, tokens.reminder_words, tokens.amount) == (
        "high", True, 60, "^30m before", Decimal("200.00"))
    assert tokens.rest == "Call plumber"
