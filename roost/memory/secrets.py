"""The secret filter: a memory never holds a password, code, key or card or bank number."""

from __future__ import annotations

import re

_SAID_SECRET = re.compile(r"\b(?:password|passwd|passcode|pin|api[ _-]?key|secret key|access key|token|"
                          r"private key|seed phrase|recovery phrase|cvv|cvc)\b\s*(?:is|was|=|:)\s*\S+", re.I)
# Security review (memory Task 10): "password for gmail is …", "la contraseña de gmail es …" -- up to
# three words may sit between the keyword and its verb, in English or Spanish. "pin" stays out of
# this one, so "My PIN pad is broken" is still an ordinary fact.
_SAID_SECRET_LOOSE = re.compile(r"\b(?:password|passwd|passcode|contraseña|contrasena|clave|api[ _-]?key|token)\b"
                                r"(?:\s+\S+){0,3}?\s*(?:is|was|es|era|=|:)\s*\S+", re.I)
# "wifi password hunter2": no verb at all, so the value must look like one (a digit or a symbol).
_BARE_SECRET = re.compile(r"\b(?:password|passwd|contraseña|contrasena|clave)\s+(?=\S*[\d!@#$%^&*])\S{4,}", re.I)
_CODE = re.compile(r"\b(?:code|otp|pin|2fa|código|codigo)\b\D{0,15}\b\d{4,8}\b", re.I)
_CODE_FIRST = re.compile(r"\b\d{4,8}\b\D{0,15}\b(?:code|otp|2fa|código|codigo)\b", re.I)
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")            # then a Luhn check on its digits
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b", re.I)
_TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{24,}\b")
_KEY_PREFIX = re.compile(r"\b(?:sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|xox[abp]-[A-Za-z0-9-]{8,}|AKIA[A-Z0-9]{12,})")
_PATTERNS = (_SAID_SECRET, _SAID_SECRET_LOOSE, _BARE_SECRET, _CODE, _CODE_FIRST, _IBAN, _TOKEN, _KEY_PREFIX)

SECRET_REFUSAL_TEXT = ("That looks like a password, code, key, or card or bank number, and those are never kept "
                       "in memory.")


def _luhn(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _has_card_number(text: str) -> bool:
    return any(_luhn(re.sub(r"\D", "", match.group(0))) for match in _CARD.finditer(text))


def looks_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PATTERNS) or _has_card_number(text)
