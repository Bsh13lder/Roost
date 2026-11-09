"""The money maths (Amendment T), shared by the task budget token and, in Batch B, the expense line:
``2x31``, ``12+8``, ``100/4``. Pure and exact: ``Decimal`` only, at most ``EXPRESSION_MAX_TERMS`` numbers,
``x`` ``×`` ``*`` before ``/`` before ``+`` as usual (``*``, ``x``, ``×`` and ``/`` bind first), no brackets,
no minus, no division by zero. The result is rounded to the cent (half up) and must be more than 0 and at
most ``MAX_EXPENSE_AMOUNT``. Numbers follow ``number_value`` (``1.200,50``, ``12,5``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from roost.constants import EXPRESSION_MAX_TERMS, MAX_EXPENSE_AMOUNT
from roost.money.amounts import CENT, MAX_NUMBER_DIGITS, number_value, too_many_digits

NUMBER_PATTERN = r"\d[\d.,]*\d|\d"
OPERATOR_PATTERN = r"[xX×*+/]"
EXPRESSION_PATTERN = rf"(?:{NUMBER_PATTERN})(?:{OPERATOR_PATTERN}(?:{NUMBER_PATTERN})){{0,{EXPRESSION_MAX_TERMS - 1}}}"

UNREADABLE_TEXT = "I could not read “{text}” as a sum. Use numbers with x, + or /, like 2x31."
TOO_MANY_TEXT = f"A sum can have at most {EXPRESSION_MAX_TERMS} numbers."
DIVIDE_BY_ZERO_TEXT = "Can't divide by zero."
TOO_LONG_TEXT = f"A number can have at most {MAX_NUMBER_DIGITS} digits."
# Six numbers of 12 digits multiply to 72 digits: this precision keeps every product exact (never rounded silently).
_WORKING_PRECISION = 80
RANGE_TEXT = f"An amount must be more than 0 and at most {MAX_EXPENSE_AMOUNT:,}."
_SHOWN = {"x": "×", "X": "×", "×": "×", "*": "×", "+": "+", "/": "/"}
_SPLIT = re.compile(rf"({OPERATOR_PATTERN})")


class ExpressionError(ValueError):
    """A sum that can't be used; the message is a plain sentence for the user."""


@dataclass(frozen=True)
class MoneyMath:
    value: Decimal                 # the result, to the cent
    shown: str | None              # "2×31"; ``None`` for a single number (nothing was worked out)


def has_operator(text: str) -> bool:
    return _SPLIT.search(text) is not None


def _number(word: str, text: str) -> Decimal:
    value = number_value(word)
    if value is None and re.fullmatch(r"\d[\d.,]*", word) and too_many_digits(word):
        raise ExpressionError(TOO_LONG_TEXT)
    if value is None:
        raise ExpressionError(UNREADABLE_TEXT.format(text=text))
    return value


def _tidy(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _terms(numbers: list[Decimal], operators: list[str]) -> list[Decimal]:
    """Fold every × and / into the number before it; what is left are + terms."""
    terms = [numbers[0]]
    for operator, number in zip(operators, numbers[1:]):
        if operator == "+":
            terms.append(number)
        elif operator == "/":
            if number == 0:
                raise ExpressionError(DIVIDE_BY_ZERO_TEXT)
            terms[-1] = terms[-1] / number
        else:
            terms[-1] = terms[-1] * number
    return terms


def evaluate(text: str) -> MoneyMath:
    """The sum in ``text`` (digits and operators, no money sign). ``ExpressionError`` when it can't be used."""
    clean = text.strip().replace(" ", "")
    if not re.fullmatch(rf"(?:{NUMBER_PATTERN})(?:{OPERATOR_PATTERN}(?:{NUMBER_PATTERN}))*", clean):
        raise ExpressionError(UNREADABLE_TEXT.format(text=text.strip()))
    parts = _SPLIT.split(clean)
    words, operators = parts[0::2], parts[1::2]
    if len(words) > EXPRESSION_MAX_TERMS:
        raise ExpressionError(TOO_MANY_TEXT)
    numbers = [_number(word, text.strip()) for word in words]
    try:
        return _worked(numbers, operators)
    except InvalidOperation as exc:
        raise ExpressionError(RANGE_TEXT) from exc


def _worked(numbers: list[Decimal], operators: list[str]) -> MoneyMath:
    shown = "".join(f"{_tidy(numbers[0])}" if index == 0 else f"{_SHOWN[operators[index - 1]]}{_tidy(number)}"
                    for index, number in enumerate(numbers))
    with localcontext() as context:
        context.prec = _WORKING_PRECISION
        total = sum(_terms(numbers, operators), Decimal(0)).quantize(CENT, rounding=ROUND_HALF_UP)
    if not 0 < total <= MAX_EXPENSE_AMOUNT:
        raise ExpressionError(RANGE_TEXT)
    return MoneyMath(total, shown if operators else None)
