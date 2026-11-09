"""Words that name a box (B3, owner decision 2026-10-23; ``docs/plans/2026-10-23-roost-tabs-signin-flow.md``).

``names_a_code``: a one-time, verification or PIN code box by its id, name, placeholder or label, but never a promo,
zip, postal or gift code. ``names_a_login``: a sign-in page's user-name box. Whole words, casefolded, accents
stripped (``commit_words.normalise``). Pure."""

from __future__ import annotations

from roost.computer_use.commit_words import normalise

CODE_NAME_WORDS: tuple[str, ...] = (
    "otp", "totp", "2fa", "mfa", "passcode", "pin", "one time code", "one time password", "verification",
    "verification code", "security code", "auth code", "authentication code", "code", "codigo", "verificacion",
)
NOT_A_SECRET_CODE: tuple[str, ...] = (
    "promo", "promotion", "promotional", "zip", "postal", "postcode", "discount", "gift", "coupon", "referral",
    "voucher", "invite", "invitation", "country", "area", "source", "tracking", "descuento", "cupon",
)
LOGIN_NAME_WORDS: tuple[str, ...] = (
    "login", "log in", "signin", "sign in", "username", "user name", "usuario", "identifier",
)


def _has(words: str, phrase: str) -> bool:
    return f" {phrase} " in f" {words} "


def _any(words: str, phrases: tuple[str, ...]) -> bool:
    return any(_has(words, normalise(phrase)) for phrase in phrases)


def names_a_code(names: str) -> bool:
    words = normalise(names)
    return _any(words, CODE_NAME_WORDS) and not _any(words, NOT_A_SECRET_CODE)


def names_a_login(names: str) -> bool:
    return _any(normalise(names), LOGIN_NAME_WORDS)
