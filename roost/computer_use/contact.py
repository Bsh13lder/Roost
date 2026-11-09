"""Contact details in text a bot types (R9): an email address or a phone number, nothing else.

Owner, 2026-11-03: links, bare domains and @handles are no contact details (a cover letter names sites and tools),
and a detail you gave the bot yourself (in your own messages in the chat, its instructions or its memories, see
``contact_sources.py``) is yours to type. ``contact_details`` gives each detail in one normal form: ``mail:`` and the
address in lower case, ``tel:`` and the phone's digits. A phone needs at least ``PHONE_MIN_DIGITS`` digits, and a
range written with a spaced dash ("1500 - 2000"), an amount (a currency sign before it or a currency code after it)
and an ISO date are never phones."""

from __future__ import annotations

import re
from typing import Iterable

PHONE_MIN_DIGITS = 9                     # a Spanish mobile has 9; a 4-digit range has 8
CURRENCY_CODES: tuple[str, ...] = ("USD", "EUR", "GBP", "CAD", "AUD", "CHF", "MXN")
MAIL_PREFIX = "mail:"
TEL_PREFIX = "tel:"
_CURRENCY_SIGNS = "$€£¥"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{5,}\d(?![\w.])")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RANGE = re.compile(r"\d+\s+[-–]\s+\d+")
_SIGN_BEFORE = re.compile(rf"[{re.escape(_CURRENCY_SIGNS)}]\s*$")
_CODE_AFTER = re.compile(rf"\s*(?:{'|'.join(CURRENCY_CODES)})\b", re.IGNORECASE)


def _is_amount(text: str, start: int, end: int) -> bool:
    return bool(_SIGN_BEFORE.search(text[:start]) or _CODE_AFTER.match(text, end))


def _phone_digits(text: str, match: re.Match[str]) -> str:
    """The phone's digits, or "" when the match is a range, a date, an amount or too short."""
    found = match.group(0).strip()
    digits = "".join(char for char in found if char.isdigit())
    if len(digits) < PHONE_MIN_DIGITS or _ISO_DATE.fullmatch(found) or _RANGE.fullmatch(found):
        return ""
    return "" if _is_amount(text, match.start(), match.end()) else digits


def _phones(text: str) -> Iterable[str]:
    for match in _PHONE.finditer(text):
        digits = _phone_digits(text, match)
        if digits:
            yield f"{TEL_PREFIX}{digits}"


def contact_details(text: str) -> frozenset[str]:
    """Every email address and phone number in ``text``, in their normal form."""
    mails = (f"{MAIL_PREFIX}{found.casefold()}" for found in _EMAIL.findall(text))
    return frozenset((*mails, *_phones(text)))


def _same_phone(one: str, other: str) -> bool:
    """The same number with or without its country code: one's digits end the other's (at least a whole number)."""
    a, b = one[len(TEL_PREFIX):], other[len(TEL_PREFIX):]
    return a == b or (min(len(a), len(b)) >= PHONE_MIN_DIGITS and (a.endswith(b) or b.endswith(a)))


def _known(detail: str, allowed: frozenset[str]) -> bool:
    if detail in allowed:
        return True
    return detail.startswith(TEL_PREFIX) and any(
        known.startswith(TEL_PREFIX) and _same_phone(detail, known) for known in allowed)


def has_contact(text: str, allowed: frozenset[str] = frozenset()) -> bool:
    """True when ``text`` holds an email address or a phone number that is not in ``allowed``."""
    return any(not _known(detail, allowed) for detail in contact_details(text))
