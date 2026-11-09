"""Speak-ahead's words (docs/plans/2026-10-30-roost-voice.md §3, contract B): a reply's streamed text cut into the
parts a call speaks as they close. The numbering is prefix-stable: ``call_parts(text)`` is a prefix of
``call_parts(text + more)``, so a part spoken early is never renamed. Part 0 is cut at a clause (``, ; :``) once
its sentence passes ``VOICE_FIRST_PART_CHARS_MAX``, so the first sound comes before the sentence ends; later parts
are one closed sentence each, a long one cut at words under ``VOICE_PART_CHARS_MAX``; the open tail is spoken only
when the reply is done. The "On it: …" lead is never spoken. Pure."""

from __future__ import annotations

import re

from roost.talk.chat_feel import shown_reply
from roost.voice.constants import VOICE_FIRST_PART_CHARS_MAX, VOICE_FIRST_PART_CUTS, VOICE_PART_CHARS_MAX
from roost.voice.speech_text import cut_long, speech_words

_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s+")
_LEAD_LINE = re.compile(r"^\s*On it\s*[:,—-][^\n]*\n+", re.IGNORECASE)
_LEAD_START = re.compile(r"^\s*On it\s*[:,—-]", re.IGNORECASE)


def _closed_and_open(text: str) -> tuple[tuple[str, ...], str]:
    """Whitespace after the last terminator closes the last sentence too, so the text's end is kept as it is."""
    pieces = _SENTENCE_END.split(text.lstrip())
    if not pieces or not pieces[-1].strip():
        return tuple(p for p in pieces if p.strip()), ""
    return tuple(pieces[:-1]), pieces[-1].rstrip()


def split_sentences(text: str) -> tuple[str, ...]:
    """The closed sentences of ``text``: each ends with a terminator followed by whitespace."""
    return _closed_and_open(text)[0]


def open_tail(text: str) -> str:
    """What follows the last closed sentence (the sentence still being written)."""
    return _closed_and_open(text)[1]


def _spoken_prefix(text: str, done: bool) -> str | None:
    """``text`` without its "On it: …" lead; None while the lead's line end is not known yet."""
    if _LEAD_LINE.match(text):
        return _LEAD_LINE.sub("", text, count=1)
    if _LEAD_START.match(text):
        return shown_reply(text) if done else None
    return text


def _first_cut(sentence: str) -> int | None:
    """Where part 0 ends inside a long first sentence: after the last clause mark within the cap, if any."""
    if len(sentence) <= VOICE_FIRST_PART_CHARS_MAX:
        return None
    head = sentence[:VOICE_FIRST_PART_CHARS_MAX]
    for at in range(len(head) - 1, 0, -1):
        if head[at] in VOICE_FIRST_PART_CUTS and at + 1 < len(sentence) and sentence[at + 1] == " ":
            return at + 1
    return None


def _pieces(sentence: str) -> tuple[str, ...]:
    return tuple(cut_long(sentence) if len(sentence) > VOICE_PART_CHARS_MAX else [sentence])


def _first_parts(first: str, closed: bool) -> tuple[tuple[str, ...], str]:
    """Part 0 and what is left of the first sentence: a long first sentence gives its first clause at once
    (even while still open), a closed one is spoken whole, and an open short one is not ready yet."""
    cut = _first_cut(first)
    if cut is not None:
        return (first[:cut],), first[cut:].strip()
    return (_pieces(first) if closed else ()), ""


def call_parts(text: str, done: bool) -> tuple[str, ...]:
    """The parts of ``text`` ready to be spoken; with ``done`` the open tail becomes the last part(s)."""
    plain = _spoken_prefix(text, done)
    if plain is None:
        return ()
    words = speech_words(plain) + (" " if plain[-1:].isspace() else "")   # speech_words trims; keep the end's signal
    sentences, tail = _closed_and_open(words)
    if done and tail:
        sentences, tail = (*sentences, tail), ""
    if not sentences:
        return _first_parts(tail, closed=False)[0] if tail else ()
    parts, rest = _first_parts(sentences[0], closed=True)
    for sentence in (*([rest] if rest else ()), *sentences[1:]):
        parts = (*parts, *_pieces(sentence))
    return parts
