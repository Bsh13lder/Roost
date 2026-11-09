"""Card value checks for the Pay card (P4). Pure; every refusal is a fixed sentence that never holds the value."""

from __future__ import annotations

import re
from datetime import date
from typing import Final

CARD_DIGITS_MIN: Final = 12
CARD_DIGITS_MAX: Final = 19
CARD_YEARS_AHEAD_MAX: Final = 20
CARD_NAME_MAX: Final = 80
CVC_DIGITS: Final = 3
AMEX_CVC_DIGITS: Final = 4

NUMBER_TEXT: Final = "That card number doesn't look right. Check it and try again."
EXP_TEXT: Final = "That expiry date doesn't look right, or the card has expired. Use MM/YY."
CVC_TEXT: Final = "The security code doesn't look right: 3 digits on the back (4 on the front for Amex)."
NAME_TEXT: Final = "The name on the card doesn't look right."

_SEPARATORS = re.compile(r"[\s-]")
_EXP = re.compile(r"^(\d{1,2})\s*/?\s*(\d{2}|\d{4})$")
_BRANDS: Final = (("amex", re.compile(r"^3[47]")), ("visa", re.compile(r"^4")),
                  ("mastercard", re.compile(r"^(5[1-5]|222[1-9]|22[3-9]|2[3-6]|27[01]|2720)")),
                  ("discover", re.compile(r"^(6011|65|64[4-9])")))


class CardCheckError(ValueError):
    """A card value failed its check; ``str()`` is the fixed sentence to show."""


def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char) * (2 if position % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def check_number(raw: str) -> str:
    digits = _SEPARATORS.sub("", raw or "")
    if not digits.isdigit() or not CARD_DIGITS_MIN <= len(digits) <= CARD_DIGITS_MAX or not _luhn_ok(digits):
        raise CardCheckError(NUMBER_TEXT)
    return digits


def brand_of(digits: str) -> str:
    return next((name for name, pattern in _BRANDS if pattern.match(digits)), "card")


def check_exp(raw: str, today: date) -> str:
    """``MM/YY``; the card is good through the end of its month, at most 20 years ahead."""
    found = _EXP.match((raw or "").strip())
    if found is None:
        raise CardCheckError(EXP_TEXT)
    year_text = found.group(2)
    if len(year_text) == 4 and not year_text.startswith("20"):
        raise CardCheckError(EXP_TEXT)
    month, year = int(found.group(1)), int(year_text[-2:]) + 2000
    if not 1 <= month <= 12 or (year, month) < (today.year, today.month) or year > today.year + CARD_YEARS_AHEAD_MAX:
        raise CardCheckError(EXP_TEXT)
    return f"{month:02d}/{year % 100:02d}"


def check_cvc(raw: str, brand: str) -> str:
    """3 digits (4 for Amex); with no number to tell the brand (``"card"``), 3 or 4."""
    want = {AMEX_CVC_DIGITS} if brand == "amex" else {CVC_DIGITS, AMEX_CVC_DIGITS} if brand == "card" else {CVC_DIGITS}
    value = (raw or "").strip()
    if not value.isdigit() or len(value) not in want:
        raise CardCheckError(CVC_TEXT)
    return value


def check_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if not name or len(name) > CARD_NAME_MAX or not name.isprintable():
        raise CardCheckError(NAME_TEXT)
    return name
