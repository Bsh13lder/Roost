"""The Pay card, P4: card values are checked by hand with fixed words, never echoed back.

``roost/payments/checks.py``: Luhn, expiry (MM/YY, not past, at most 20 years ahead), CVC (3 digits, 4 for Amex),
name, brand. Each refusal is a fixed sentence that never holds the value."""

from __future__ import annotations

from datetime import date

import pytest

from roost.payments.checks import CardCheckError, brand_of, check_cvc, check_exp, check_name, check_number

_TODAY = date(2026, 11, 6)


@pytest.mark.parametrize(("raw", "digits", "brand"), [
    ("4242 4242 4242 4242", "4242424242424242", "visa"),
    ("5555-5555-5555-4444", "5555555555554444", "mastercard"),
    ("2223003122003222", "2223003122003222", "mastercard"),
    ("378282246310005", "378282246310005", "amex"),
    ("6011111111111117", "6011111111111117", "discover"),
])
def test_a_good_number_is_kept_as_digits_with_its_brand(raw, digits, brand):
    assert check_number(raw) == digits and brand_of(digits) == brand


@pytest.mark.parametrize("raw", ["4242 4242 4242 4241", "1234", "abcd efgh ijkl mnop", "", "4" * 25])
def test_a_bad_number_is_refused_without_its_value(raw):
    with pytest.raises(CardCheckError) as caught:
        check_number(raw)
    assert raw.strip() == "" or raw not in str(caught.value)


@pytest.mark.parametrize(("raw", "kept"), [("12/28", "12/28"), ("1/27", "01/27"), ("11 / 2026", "11/26"),
                                           ("0330", "03/30")])
def test_an_expiry_is_kept_as_mm_yy(raw, kept):
    assert check_exp(raw, _TODAY) == kept


@pytest.mark.parametrize("raw", ["10/26", "13/28", "00/28", "12/60", "soon", ""])
def test_a_past_or_odd_expiry_is_refused(raw):
    with pytest.raises(CardCheckError):
        check_exp(raw, _TODAY)


def test_a_cvc_is_three_digits_or_four_for_amex():
    assert check_cvc("123", "visa") == "123"
    assert check_cvc("1234", "amex") == "1234"
    for bad, brand in (("12", "visa"), ("1234", "visa"), ("12a", "visa"), ("123", "amex")):
        with pytest.raises(CardCheckError):
            check_cvc(bad, brand)


def test_a_name_is_trimmed_and_capped():
    assert check_name("  ana   garcia ") == "ana garcia"
    for bad in ("", "x" * 81, "ana\x00garcia"):
        with pytest.raises(CardCheckError):
            check_name(bad)


def test_a_four_digit_year_must_be_this_century():
    with pytest.raises(CardCheckError):
        check_exp("12/2125", _TODAY)
    assert check_exp("12/2030", _TODAY) == "12/30"


def test_with_no_number_a_security_code_may_be_three_or_four_digits():
    assert check_cvc("1234", "card") == "1234" and check_cvc("123", "card") == "123"


@pytest.mark.parametrize(("text", "shown"), [
    ("Card 4242 4242 4242 4242 ready", "Card [card number hidden] ready"),
    ("Number: 4242-4242-4242-4242.", "Number: [card number hidden]."),
    ("Order 1234567890123 placed", "Order 1234567890123 placed"),          # fails Luhn: an order number stays
    ("Call 600 123 456", "Call 600 123 456"),
])
def test_card_numbers_are_hidden_from_page_text(text, shown):
    from roost.desk.card_redact import hide_card_numbers
    assert hide_card_numbers(text) == shown
