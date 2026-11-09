"""The words a bot's reply is spoken from: its markdown made plain, capped, and cut into parts small enough to speak
one at a time (the first part plays while the next is made). Pure."""

from __future__ import annotations

import re

from roost.voice.constants import VOICE_CODE_WORDS, VOICE_PART_CHARS_MAX, VOICE_TEXT_CHARS_MAX

_FENCE = re.compile(r"```.*?(```|$)", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_WIKILINK = re.compile(r"\[\[([^\]|]*)(\|([^\]]*))?\]\]")
_LINE_MARKS = re.compile(r"^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|[-*_]{3,}\s*$)", re.M)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1")
_TABLE_BAR = re.compile(r"\s*\|\s*")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.M)   # a table's |---|---| row
# Emoji and other pictographs: symbols, dingbats, flags, the variation selector and the joiner that build them.
_EMOJI = re.compile(
    "[\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D"
    "\U0001F000-\U0001F2FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF\U0001F1E6-\U0001F1FF]"
)
_SPACES = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s+")


def speech_words(text: str) -> str:
    """``text`` as plain words: code becomes "(code)", a link its own words, a bare address nothing, list and heading
    marks, a table's rule row and emoji go; at most ``VOICE_TEXT_CHARS_MAX`` characters, cut at a word."""
    plain = _FENCE.sub(f" {VOICE_CODE_WORDS} ", text)
    plain = _TABLE_RULE.sub("", plain)
    plain = _EMOJI.sub("", plain)
    plain = _INLINE_CODE.sub(VOICE_CODE_WORDS, plain)
    plain = _IMAGE.sub(r"\1", plain)
    plain = _WIKILINK.sub(lambda m: m.group(3) or m.group(1), plain)
    plain = _LINK.sub(r"\1", plain)
    plain = _BARE_URL.sub("", plain)
    plain = _LINE_MARKS.sub("", plain)
    plain = _EMPHASIS.sub(r"\2", plain)
    plain = _TABLE_BAR.sub(" ", plain)
    plain = _SPACES.sub(" ", plain).strip()
    if len(plain) <= VOICE_TEXT_CHARS_MAX:
        return plain
    return plain[:VOICE_TEXT_CHARS_MAX].rsplit(" ", 1)[0]


def cut_long(sentence: str) -> list[str]:
    """One sentence longer than ``VOICE_PART_CHARS_MAX`` cut at words into pieces that fit."""
    pieces: list[str] = []
    current = ""
    for word in sentence.split(" "):
        word = word[:VOICE_PART_CHARS_MAX]
        if current and len(current) + 1 + len(word) > VOICE_PART_CHARS_MAX:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    return [*pieces, current] if current else pieces


def speech_parts(text: str) -> list[str]:
    """``speech_words(text)`` in parts of at most ``VOICE_PART_CHARS_MAX``, whole sentences where they fit; joined
    with single spaces they give the words back."""
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(speech_words(text)):
        for piece in cut_long(sentence) if len(sentence) > VOICE_PART_CHARS_MAX else [sentence]:
            if current and len(current) + 1 + len(piece) > VOICE_PART_CHARS_MAX:
                parts.append(current)
                current = piece
            else:
                current = f"{current} {piece}" if current else piece
    return [*parts, current] if current else parts
