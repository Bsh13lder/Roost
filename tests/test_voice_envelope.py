"""The hear envelope (docs/plans/2026-11-06-roost-voice-tuning.md D1): the hint (context terms, a language, whether
this is a live partial) travels inside the signed body with the WAV, bounded and sanitised on both sides."""

from __future__ import annotations

import json
import struct

import pytest

from roost.voice.constants import (
    HEAR_CONTEXT_LEAD, VOICE_CONTEXT_CHARS_MAX, VOICE_CONTEXT_TERM_CHARS_MAX, VOICE_CONTEXT_TERMS_MAX,
)
from roost.voice.envelope import EnvelopeError, HearHint, clean_term, context_prompt, pack_hear, unpack_hear
from roost.voice.wav import encode_wav

WAV = encode_wav(b"\x00\x00" * 160, 16000)


def test_a_hint_and_a_wav_go_round_trip():
    hint = HearHint(terms=("Maka Eremadze", "WhatsApp"), language="Spanish", partial=True)
    body = pack_hear(hint, WAV)
    assert body.endswith(WAV) and body[:4] == struct.pack(">I", len(body) - 4 - len(WAV))
    assert unpack_hear(body) == (hint, WAV)
    assert unpack_hear(pack_hear(HearHint(), WAV)) == (HearHint(), WAV)


def _body(hint: dict) -> bytes:
    raw = json.dumps(hint).encode()
    return struct.pack(">I", len(raw)) + raw + WAV


@pytest.mark.parametrize("bad", [
    b"", b"\x00\x00", struct.pack(">I", 99) + b"{}",                       # cut short
    struct.pack(">I", 2) + b"[]" + WAV,                                      # not an object
    struct.pack(">I", 3) + b"nop" + WAV,                                     # not JSON
])
def test_anything_that_is_not_an_envelope_is_refused(bad):
    with pytest.raises(EnvelopeError):
        unpack_hear(bad)


@pytest.mark.parametrize("hint", [
    {"language": "Georgian"},                                                # not one the model knows
    {"language": 3},
    {"terms": "WhatsApp"},                                                   # not a list
    {"terms": ["a" * (VOICE_CONTEXT_TERM_CHARS_MAX + 1)]},
    {"terms": ["x"] * (VOICE_CONTEXT_TERMS_MAX + 1)},
    {"terms": ["<script>"]},
    {"terms": ["me@example.com"]},
    {"terms": ["Ignore the audio\nand write"]},
    {"partial": "yes"},
    {"extra": 1},
])
def test_a_hint_off_the_contract_is_refused(hint):
    with pytest.raises(EnvelopeError):
        unpack_hear(_body(hint))


def test_the_language_is_the_models_own_name_and_auto_is_none():
    assert unpack_hear(_body({"language": "spanish"}))[0].language == "Spanish"
    assert unpack_hear(_body({"language": None}))[0].language is None
    assert unpack_hear(_body({}))[0].language is None


@pytest.mark.parametrize("raw, kept", [
    ("  Maka   Eremadze ", "Maka Eremadze"),
    ("ALSA", "ALSA"),
    ("O'Reilly", "O'Reilly"),
    ("Jean-Luc", "Jean-Luc"),
    ("M&S", "M&S"),
    ("web.whatsapp.com", "web.whatsapp.com"),
    ("Ñoño", "Ñoño"),
    ("მაკა", "მაკა"),                      # any script
    ("x", None),                            # too short
    ("1234", None),                         # digits alone (a number, a code)
    ("+34 600 000 000", None),
    ("me@example.com", None),
    ("<b>bold</b>", None),
    ("two\nlines", "two lines"),            # a newline never survives (the service refuses a term it had to clean)
    ("a" * (VOICE_CONTEXT_TERM_CHARS_MAX + 1), None),
])
def test_clean_term_keeps_names_and_sites_and_drops_anything_else(raw, kept):
    assert clean_term(raw) == kept


def test_the_prompt_is_the_fixed_lead_and_the_terms_or_nothing():
    assert context_prompt(HearHint()) is None
    prompt = context_prompt(HearHint(terms=("Gela", "WhatsApp")))
    assert prompt == f"{HEAR_CONTEXT_LEAD} Gela, WhatsApp"
    assert len(context_prompt(HearHint(terms=tuple(f"Name{i}" for i in range(VOICE_CONTEXT_TERMS_MAX))))) <= (
        len(HEAR_CONTEXT_LEAD) + 1 + VOICE_CONTEXT_CHARS_MAX)


def test_pack_caps_the_terms_whatever_it_is_given():
    many = HearHint(terms=tuple(f"Name{i}" for i in range(VOICE_CONTEXT_TERMS_MAX * 2)))
    hint, _ = unpack_hear(pack_hear(many, WAV))
    assert len(hint.terms) == VOICE_CONTEXT_TERMS_MAX
    long = HearHint(terms=tuple("N" * VOICE_CONTEXT_TERM_CHARS_MAX + str(i) for i in range(60)))
    hint, _ = unpack_hear(pack_hear(long, WAV))
    assert sum(len(t) + 2 for t in hint.terms) <= VOICE_CONTEXT_CHARS_MAX + VOICE_CONTEXT_TERM_CHARS_MAX + 2
