"""A bot's voice settings as stored (schema v37 ``bots.voice``: fixed ids, a number, switches and a language code, no
user words), as the route takes them (``VoiceIn``) and as a change to some of them (``VoicePatch``, shared by the
route and the bot's own ``set_my_voice``, so the lists are checked in one place). A stored value that no longer fits
reads as the defaults, never as an error. Voice tuning (docs/plans/2026-11-06-roost-voice-tuning.md D2, D3): the
switch is ``correct_speech`` and ``correct_english`` its alias both ways (an old row, an older client); ``language``
is ``auto`` or one of ``VOICE_LANGUAGE_IDS``, and an old row without it reads ``auto``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from roost.voice.constants import (
    DEFAULT_VOICE, SPEAKER_IDS, SPEEDS, TONES, VOICE_LANGUAGE_AUTO, VOICE_LANGUAGE_IDS, VoiceSettings,
)

__all__ = ["VoiceIn", "VoicePatch", "VoiceSettings", "apply_patch", "check_language", "check_speaker",
           "check_speed", "check_tone", "voice_dict", "voice_dump", "voice_from_dict", "voice_load"]

BAD_SPEAKER_TEXT = "Pick one of the listed voices."
BAD_TONE_TEXT = "Pick one of the listed tones."
BAD_SPEED_TEXT = "Pick one of the listed speeds."
BAD_LANGUAGE_TEXT = "Pick Auto-detect or one of the listed languages."

_CORRECT_KEY = "correct_speech"
_CORRECT_ALIAS = "correct_english"


def _valid(settings: VoiceSettings) -> bool:
    return (settings.speaker in SPEAKER_IDS and settings.tone in TONES and settings.speed in SPEEDS
            and (settings.language == VOICE_LANGUAGE_AUTO or settings.language in VOICE_LANGUAGE_IDS))


def _correct_from(data: Mapping[str, Any]) -> bool:
    """The switch under its new key, else its old one, else off."""
    if _CORRECT_KEY in data:
        return bool(data[_CORRECT_KEY])
    return bool(data.get(_CORRECT_ALIAS, False))


def voice_from_dict(data: Mapping[str, Any]) -> VoiceSettings | None:
    """The settings in a ``voice`` dict (a stored row, a ``bot_updated`` frame); ``None`` when it doesn't fit."""
    try:
        settings = VoiceSettings(speaker=str(data["speaker"]), tone=str(data["tone"]), speed=float(data["speed"]),
                                 read_aloud=bool(data.get("read_aloud", False)),
                                 correct_speech=_correct_from(data),
                                 language=str(data.get("language", VOICE_LANGUAGE_AUTO)))
    except (ValueError, TypeError, KeyError):
        return None
    return settings if _valid(settings) else None


def voice_load(raw: str | None) -> VoiceSettings:
    if not raw:
        return DEFAULT_VOICE
    try:
        data = json.loads(raw)
    except ValueError:
        return DEFAULT_VOICE
    if not isinstance(data, Mapping):
        return DEFAULT_VOICE
    return voice_from_dict(data) or DEFAULT_VOICE


def voice_dict(settings: VoiceSettings) -> dict[str, object]:
    """Both names of the switch go out, so an older client (a phone build) still reads it."""
    return {"speaker": settings.speaker, "tone": settings.tone, "speed": settings.speed,
            "read_aloud": settings.read_aloud, _CORRECT_KEY: settings.correct_speech,
            _CORRECT_ALIAS: settings.correct_speech, "language": settings.language}


def voice_dump(settings: VoiceSettings) -> str:
    return json.dumps(voice_dict(settings))


def check_speaker(value: str) -> str:
    if value not in SPEAKER_IDS:
        raise ValueError(BAD_SPEAKER_TEXT)
    return value


def check_tone(value: str) -> str:
    if value not in TONES:
        raise ValueError(BAD_TONE_TEXT)
    return value


def check_speed(value: float) -> float:
    if value not in SPEEDS:
        raise ValueError(BAD_SPEED_TEXT)
    return value


def check_language(value: str) -> str:
    if value != VOICE_LANGUAGE_AUTO and value not in VOICE_LANGUAGE_IDS:
        raise ValueError(BAD_LANGUAGE_TEXT)
    return value


@dataclass(frozen=True)
class VoicePatch:
    """A change to some of a bot's voice settings; ``None`` leaves that one as it is."""

    speaker: str | None = None
    tone: str | None = None
    speed: float | None = None
    read_aloud: bool | None = None
    correct_speech: bool | None = None
    language: str | None = None

    def fields(self) -> dict[str, Any]:
        """The fields this patch sets, by name."""
        return {name: value for name, value in vars(self).items() if value is not None}


def apply_patch(current: VoiceSettings, patch: VoicePatch) -> VoiceSettings:
    """``current`` with the patch's fields changed; a new value, never a mutation."""
    return replace(current, **patch.fields())


def merged_correct(correct_speech: bool | None, correct_english: bool | None) -> bool | None:
    """One answer from the switch's two names: the new one when given, else the old one."""
    return correct_speech if correct_speech is not None else correct_english


class VoiceIn(BaseModel):
    """``PUT /api/bots/{id}/voice``: every field from its fixed list; the switch (under either name) and the
    language optional (the stored value stays when they are absent)."""

    model_config = ConfigDict(extra="forbid")

    speaker: str
    tone: str
    speed: float
    read_aloud: StrictBool
    correct_speech: StrictBool | None = None
    correct_english: StrictBool | None = None
    language: str | None = None

    @field_validator("speaker")
    @classmethod
    def _speaker(cls, value: str) -> str:
        return check_speaker(value)

    @field_validator("tone")
    @classmethod
    def _tone(cls, value: str) -> str:
        return check_tone(value)

    @field_validator("speed")
    @classmethod
    def _speed(cls, value: float) -> float:
        return check_speed(value)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        return None if value is None else check_language(value)

    def patch(self) -> VoicePatch:
        return VoicePatch(speaker=self.speaker, tone=self.tone, speed=self.speed, read_aloud=self.read_aloud,
                          correct_speech=merged_correct(self.correct_speech, self.correct_english),
                          language=self.language)
