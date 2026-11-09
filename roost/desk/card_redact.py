"""Card numbers never reach the model (the Pay card, review 2026-11-06): many checkouts mirror the card number into a
"card preview" outside the box. Every page text the bot reads (a look's summary, ``read_text``) has each run of 13–19
digits (spaces or dashes between them) that passes the Luhn check replaced by fixed words. Pure."""

from __future__ import annotations

import re
from typing import Final

CARD_HIDDEN: Final = "[card number hidden]"
_RUN = re.compile(r"(?<!\d)\d(?:[ \-]?\d){12,18}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char) * (2 if position % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def _hide(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return CARD_HIDDEN if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)


def hide_card_numbers(text: str) -> str:
    return _RUN.sub(_hide, text)
