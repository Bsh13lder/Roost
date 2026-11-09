"""Voice's pure pieces: the WAV check, the words a reply is spoken from, and a bot's voice settings."""

from __future__ import annotations

import struct

import pytest

from roost.voice.constants import (
    DEFAULT_VOICE,
    SPEAKERS,
    SPEEDS,
    TONES,
    VOICE_MAX_SECONDS,
    VOICE_PART_CHARS_MAX,
    VOICE_TEXT_CHARS_MAX,
)
from roost.voice.settings import VoiceSettings, voice_dump, voice_load
from roost.voice.speech_text import speech_parts, speech_words
from roost.voice.wav import WavError, encode_wav, read_wav


def _wav(rate: int = 16000, channels: int = 1, bits: int = 16, frames: int = 1600) -> bytes:
    return encode_wav(b"\x00\x00" * frames * channels, rate, channels=channels, bits=bits)


def test_a_clean_wav_reads_back():
    info = read_wav(_wav(frames=8000))
    assert (info.rate, info.channels, info.bits) == (16000, 1, 16)
    assert info.seconds == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [b"", b"RIFF", b"OggS" + b"\x00" * 60, b"RIFF\x00\x00\x00\x00WAVEjunk"])
def test_anything_but_a_wav_is_refused(bad):
    with pytest.raises(WavError):
        read_wav(bad)


def test_stereo_8bit_and_odd_rates_are_refused():
    with pytest.raises(WavError):
        read_wav(_wav(channels=2))
    with pytest.raises(WavError):
        read_wav(_wav(rate=4000))
    with pytest.raises(WavError):
        read_wav(encode_wav(b"\x00" * 100, 16000, bits=8))


def test_too_long_is_refused():
    with pytest.raises(WavError, match="seconds"):
        read_wav(_wav(rate=8000, frames=8000 * (VOICE_MAX_SECONDS + 1)))


def test_a_data_size_past_the_end_is_refused():
    raw = bytearray(_wav())
    at = raw.index(b"data") + 4
    raw[at:at + 4] = struct.pack("<I", 10_000_000)
    with pytest.raises(WavError):
        read_wav(bytes(raw))


def test_speech_words_drop_markdown_and_keep_link_words():
    text = "## Done\n**Added** the task. See [the board](https://x.example/a) and `code`.\n```\nprint(1)\n```\nBye!"
    words = speech_words(text)
    assert "##" not in words and "**" not in words and "https" not in words
    assert "the board" in words and "(code)" in words and "print" not in words
    assert words.endswith("Bye!")


def test_speech_words_are_capped():
    assert len(speech_words("word. " * 5000)) <= VOICE_TEXT_CHARS_MAX


def test_parts_split_on_sentences_and_stay_short():
    text = " ".join(f"Sentence number {i} is here." for i in range(60))
    parts = speech_parts(text)
    assert len(parts) > 1
    assert all(0 < len(p) <= VOICE_PART_CHARS_MAX for p in parts)
    assert all(p.endswith(".") for p in parts)
    assert " ".join(parts) == speech_words(text)


def test_one_huge_sentence_is_cut_at_words():
    parts = speech_parts("word " * 400)
    assert all(len(p) <= VOICE_PART_CHARS_MAX for p in parts)
    assert not any(p.startswith(" ") or p.endswith(" ") for p in parts)


def test_nothing_to_say_is_no_parts():
    assert speech_parts("```\nonly code\n```") == ["(code)"]
    assert speech_parts("   ") == []


def test_settings_default_and_round_trip():
    assert voice_load(None) == DEFAULT_VOICE
    settings = VoiceSettings(speaker="serena", tone="cheerful", speed=1.25, read_aloud=True)
    assert voice_load(voice_dump(settings)) == settings


def test_bad_stored_settings_fall_back_to_the_defaults():
    assert voice_load('{"speaker":"nobody","tone":"angry","speed":9}') == DEFAULT_VOICE
    assert voice_load("not json") == DEFAULT_VOICE


def test_the_lists_are_consistent():
    assert DEFAULT_VOICE.speaker in {s.id for s in SPEAKERS}
    assert DEFAULT_VOICE.tone in TONES
    assert DEFAULT_VOICE.speed in SPEEDS
    assert TONES["natural"].instruct is None
    assert all(t.instruct is None or t.instruct.endswith(".") for t in TONES.values())
