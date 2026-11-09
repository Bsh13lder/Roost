"""Card boxes (the Pay card, P1; ``docs/plans/2026-11-05-roost-pay-card.md``).

``card_part`` says which part of a payment card a box holds: ``number``, ``exp``, ``exp_month``, ``exp_year``,
``cvc`` or ``name`` (``""`` for any other box). It reads the box's ``autocomplete`` first (``cc-number`` …), then
its id, name, placeholder and label (EN + ES). Expiry and name words count only beside a card word, so a passport's
"Fecha de caducidad" or a passenger's "Name" is not a card box; CVC words are a card's own. A card box is a secret
box: the bot never types or picks there, only Roost's Pay card does. Pure."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from roost.computer_use.commit_words import normalise

CARD_PARTS: Final = ("number", "exp", "exp_month", "exp_year", "cvc", "name")
CARD_BOX_TAGS: Final = frozenset({"input", "select"})
CARD_INPUT_TYPES: Final = frozenset({"", "text", "number", "tel", "password"})

CARD_AUTOCOMPLETE: Final[Mapping[str, str]] = {
    "cc-number": "number", "cc-exp": "exp", "cc-exp-month": "exp_month", "cc-exp-year": "exp_year",
    "cc-csc": "cvc", "cc-name": "name", "cc-given-name": "name", "cc-family-name": "name",
}
CARD_WORDS: Final = ("card", "tarjeta", "cc", "credit", "debit", "credito", "debito")
NOT_A_PAYMENT_CARD: Final = ("gift", "loyalty", "membership", "id", "identity", "regalo", "fidelizacion", "socio",
                             "identidad", "sim", "student", "estudiante")
NUMBER_WORDS: Final = ("cardnumber", "ccnumber", "cardnum", "ccnum", "card number", "card no", "numero de tarjeta",
                       "numero tarjeta", "num tarjeta")
CVC_WORDS: Final = ("cvc", "cvv", "cvc2", "cvv2", "csc", "cardcvc", "cardcvv", "card security code", "security code",
                    "codigo de seguridad", "card code")
EXP_MONTH_WORDS: Final = ("expiry month", "expiration month", "exp month", "expmonth", "mes de caducidad",
                          "mes caducidad", "mes de vencimiento", "mes")
EXP_YEAR_WORDS: Final = ("expiry year", "expiration year", "exp year", "expyear", "ano de caducidad",
                         "ano caducidad", "ano de vencimiento", "ano")
EXP_WORDS: Final = ("expiry", "expiration", "expires", "exp date", "expdate", "valid thru", "valid through",
                    "mm yy", "mm aa", "mm aaaa", "caducidad", "vencimiento", "fecha de expiracion", "caduca")
NAME_WORDS: Final = ("name on card", "cardholder", "card holder", "holder name", "cardname", "titular",
                     "nombre del titular", "nombre en la tarjeta", "name")
# Only these need no card word beside them: they never name anything but a payment card.
SELF_EVIDENT: Final = ("mm yy", "mm aa", "mm aaaa", "cardholder", "titular")


def _has(words: str, phrase: str) -> bool:
    return f" {phrase} " in f" {words} "


def _any(words: str, phrases: tuple[str, ...]) -> bool:
    return any(_has(words, normalise(phrase)) for phrase in phrases)


def _card_box(extra: Mapping[str, Any]) -> bool:
    tag = str(extra.get("tag", ""))
    return tag == "select" or (tag == "input" and str(extra.get("input_type", "")) in CARD_INPUT_TYPES)


def _by_autocomplete(extra: Mapping[str, Any]) -> str:
    tokens = str(extra.get("autocomplete", "")).lower().split()
    return next((CARD_AUTOCOMPLETE[token] for token in tokens if token in CARD_AUTOCOMPLETE), "")


def _by_names(names: str) -> str:
    words = normalise(names)
    if not words or _any(words, NOT_A_PAYMENT_CARD):
        return ""
    if _any(words, NUMBER_WORDS):
        return "number"
    if _any(words, CVC_WORDS) and (_any(words, CARD_WORDS) or not _has(words, "security code")):
        return "cvc"
    carded = _any(words, CARD_WORDS) or _any(words, SELF_EVIDENT)
    if not carded:
        return ""
    for part, phrases in (("exp_month", EXP_MONTH_WORDS), ("exp_year", EXP_YEAR_WORDS), ("exp", EXP_WORDS),
                          ("name", NAME_WORDS)):
        if _any(words, phrases):
            return part
    return ""


def card_part(extra: Mapping[str, Any]) -> str:
    """The card part a box holds, or ``""``. ``extra`` is the box's DOM facts (``page_targets._extra``)."""
    if str(extra.get("tag", "")) not in CARD_BOX_TAGS or not _card_box(extra):
        return ""
    return _by_autocomplete(extra) or _by_names(str(extra.get("field_names", "")))
