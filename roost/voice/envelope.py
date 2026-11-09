"""The hear envelope (docs/plans/2026-11-06-roost-voice-tuning.md D1): what the gateway tells the voice service about
a recording besides the sound. The request signature covers the body only (``roost/desk/signing.py``), so the hint
travels inside it: a 4-byte length, the hint's JSON, then the WAV. Both sides import this module, so it has no
dependency past pydantic and the constants.

A ``HearHint`` is a few context terms (names, site names: words the owner wrote or chose, never a secret), the
hearing model's own name for a language (or ``None`` to let it listen), and whether this is a live partial. Terms are
sanitised by ``clean_term`` (letters of any script, digits, spaces and ``' - . &``; never an address, digits alone or
anything that could read as markup) and bounded by count and characters, on the way in and on the way out."""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

from roost.voice.constants import (
    HEAR_CONTEXT_LEAD,
    VOICE_CONTEXT_CHARS_MAX,
    VOICE_CONTEXT_TERM_CHARS_MAX,
    VOICE_CONTEXT_TERM_CHARS_MIN,
    VOICE_CONTEXT_TERMS_MAX,
    VOICE_HEAR_HINT_BYTES_MAX,
    VOICE_LANGUAGES,
)

_LENGTH = struct.Struct(">I")
_TERM = re.compile(r"^[^\W_][\w' .&-]*$", re.UNICODE)     # starts with a letter or digit; no markup, no newline
_DIGITS_ONLY = re.compile(r"^[\d .+-]+$")
_ASR_NAMES = {lang.asr.lower(): lang.asr for lang in VOICE_LANGUAGES}


class EnvelopeError(ValueError):
    """Not an envelope this module accepts."""


@dataclass(frozen=True)
class HearHint:
    terms: tuple[str, ...] = ()     # clean terms, already bounded
    language: str | None = None     # the model's own name ("Spanish"), or None: auto-detect
    partial: bool = False           # a live partial of a recording still going


def clean_term(raw: str) -> str | None:
    """``raw`` as one context term, or ``None`` when it cannot be one: too short or long, digits alone (a number, a
    phone, a code), an address, or any character outside letters, digits, spaces and ``' - . &``."""
    term = " ".join(str(raw).split())
    if not VOICE_CONTEXT_TERM_CHARS_MIN <= len(term) <= VOICE_CONTEXT_TERM_CHARS_MAX:
        return None
    if "@" in term or _DIGITS_ONLY.match(term) or not _TERM.match(term):
        return None
    return term


def bounded_terms(terms: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """The clean terms, without case duplicates, at most ``VOICE_CONTEXT_TERMS_MAX`` and about
    ``VOICE_CONTEXT_CHARS_MAX`` characters in all (the first ones win)."""
    kept: list[str] = []
    seen: set[str] = set()
    used = 0
    for raw in terms:
        term = clean_term(raw)
        if term is None or term.casefold() in seen:
            continue
        if len(kept) >= VOICE_CONTEXT_TERMS_MAX or used + len(term) > VOICE_CONTEXT_CHARS_MAX:
            break
        seen.add(term.casefold())
        kept.append(term)
        used += len(term) + 2
    return tuple(kept)


class _HintIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    terms: list[str] = Field(default_factory=list, max_length=VOICE_CONTEXT_TERMS_MAX)
    language: str | None = None
    partial: StrictBool = False

    @field_validator("terms")
    @classmethod
    def _terms(cls, value: list[str]) -> list[str]:
        for raw in value:
            if not isinstance(raw, str) or clean_term(raw) != raw:
                raise ValueError("a term is not clean")
        return value

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = _ASR_NAMES.get(value.lower())
        if name is None:
            raise ValueError("not a language the hearing model knows")
        return name


def pack_hear(hint: HearHint, wav: bytes) -> bytes:
    """The body ``POST /hear`` takes: the bounded hint as JSON behind its length, then the WAV."""
    data = {"terms": list(bounded_terms(hint.terms)), "language": hint.language, "partial": hint.partial}
    raw = json.dumps(data, ensure_ascii=False).encode()
    return _LENGTH.pack(len(raw)) + raw + wav


def unpack_hear(body: bytes) -> tuple[HearHint, bytes]:
    """The hint and the WAV in ``body``; ``EnvelopeError`` for anything off the contract."""
    if len(body) < _LENGTH.size:
        raise EnvelopeError("The envelope is cut short.")
    (length,) = _LENGTH.unpack_from(body)
    if length > VOICE_HEAR_HINT_BYTES_MAX or _LENGTH.size + length > len(body):
        raise EnvelopeError("The envelope's hint does not fit.")
    raw = body[_LENGTH.size:_LENGTH.size + length]
    try:
        hint = _HintIn.model_validate_json(raw)
    except ValidationError as exc:
        raise EnvelopeError("The envelope's hint is not the contract's.") from exc
    return (HearHint(terms=bounded_terms(hint.terms), language=hint.language, partial=hint.partial),
            body[_LENGTH.size + length:])


def context_prompt(hint: HearHint) -> str | None:
    """What the hearing model reads before it writes: the fixed lead and the terms, or nothing."""
    if not hint.terms:
        return None
    return f"{HEAR_CONTEXT_LEAD} {', '.join(hint.terms)}"
