"""Amounts as ``Decimal`` (never float). Accepts the comma decimal a Spanish
user types ("12,50"); refuses anything ambiguous instead of guessing."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import StrictFloat, StrictInt, StrictStr

from roost.constants import MAX_EXPENSE_AMOUNT

# An amount in a JSON body: text ("12,50") or a number, never ``true`` / ``false`` (pydantic's lax int reads
# a boolean as 0 or 1, which ``parse_amount`` would then take for an amount).
JsonAmount = StrictStr | StrictInt | StrictFloat

CENT = Decimal("0.01")
MAX_NUMBER_DIGITS = 12      # integer digits in a typed number; more would overflow Decimal's precision


def _normalized(value: str | int | float | Decimal) -> str:
    text = str(value).strip().replace("€", "").replace(" ", "")
    if text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    return text


def parse_amount(value: str | int | float | Decimal) -> Decimal:
    try:
        amount = Decimal(_normalized(value))
    except InvalidOperation as exc:
        raise ValueError(f"“{value}” is not an amount. Use a number like 12.50.") from exc
    if not amount.is_finite() or amount <= 0 or amount > MAX_EXPENSE_AMOUNT:
        raise ValueError(f"An amount must be more than 0 and at most {MAX_EXPENSE_AMOUNT:,}.")
    if amount != amount.quantize(CENT):
        raise ValueError("An amount has at most 2 decimals.")
    return amount.quantize(CENT)


def optional_amount(value: str | int | float | Decimal | None) -> Decimal | None:
    """``None`` or a blank text is no amount: a tool's '' clears a budget
    (projects hub H5) or a task's budget slice. Anything else is ``parse_amount``'s."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_amount(value)


def amount_text(amount: Decimal) -> str:
    return f"{amount.quantize(CENT):.2f}"


_THOUSANDS_DIGITS = 3


def too_many_digits(text: str) -> bool:
    """More than ``MAX_NUMBER_DIGITS`` digits before a 1-2 digit decimal tail (``1,234,567`` counts 7)."""
    last = max(text.rfind("."), text.rfind(","))
    whole = text[:last] if 0 <= last and len(text) - last - 1 <= 2 else text
    return sum(char.isdigit() for char in whole) > MAX_NUMBER_DIGITS


def number_value(text: str) -> Decimal | None:
    """An amount's digits with their separators: one separator followed by exactly 3 digits is a
    thousands sign (``1.200``, ``1,200``); with both kinds the last is the decimal (``1.200,50``,
    ``1,200.50``); 1-2 digits after a lone separator are the decimal. Anything else is refused."""
    if not re.fullmatch(r"\d[\d.,]*", text) or text[-1] in ".," or too_many_digits(text):
        return None
    marks = [char for char in text if char in ".,"]
    if not marks:
        return Decimal(text)
    last = max(text.rfind("."), text.rfind(","))
    tail = text[last + 1:]
    kinds = set(marks)
    if len(kinds) == 2:
        thousands, decimal = ("." if text[last] == "," else ","), text[last]
    elif len(marks) > 1 or len(tail) == _THOUSANDS_DIGITS:
        thousands, decimal = text[last], None
    else:
        thousands, decimal = None, text[last]
    whole = text[:last] if decimal else text
    groups = whole.split(thousands) if thousands else [whole]
    if thousands and (not groups[0] or len(groups[0]) > _THOUSANDS_DIGITS
                      or any(len(group) != _THOUSANDS_DIGITS for group in groups[1:])):
        return None
    if decimal and not 1 <= len(tail) <= 2:
        return None
    try:
        value = Decimal("".join(groups) + ("." + tail if decimal else ""))
    except InvalidOperation:
        return None
    return value.quantize(Decimal("0.01"))
