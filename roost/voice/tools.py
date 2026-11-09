"""``VoiceTools``: the ``set_my_voice`` handler (§4). It validates the model's arguments with the same rules as the
Info tab's save (``roost/voice/settings.py``), changes ONLY the calling bot's settings through the one
``VoiceSettingsService`` (which publishes ``bot_updated``), and names the change in plain words for the result and
for the Ask card a run outside the user's clean 1:1 chat gets (``prepare`` / ``execute``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError, field_validator

from roost.approvals.models import PendingCall
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.voice.constants import (
    SET_MY_VOICE_TOOL, SPEAKERS, SPEEDS, TONES, VOICE_CHANGE_TITLE, VOICE_CHANGING_ACTIVITY, VOICE_LANGUAGE_AUTO,
    VOICE_LANGUAGE_AUTO_NAME, VOICE_LANGUAGE_BY_ID,
)
from roost.voice.service import VoiceSettingsService
from roost.voice.settings import (
    VoicePatch, check_language, check_speaker, check_speed, check_tone, merged_correct,
)

BAD_VOICE_ARGS = (
    "Refused: set_my_voice needs at least one of speaker (one of the listed voices), tone (one of the listed tones), "
    f"speed (one of {', '.join(str(s) for s in SPEEDS)}), read_aloud (true or false), correct_speech (true or false) "
    "or language (auto or one of the listed codes)."
)
_NOT_YOURS = "Refused: that bot isn't yours."
_SPEAKER_NAMES = {speaker.id: speaker.name for speaker in SPEAKERS}


class SetMyVoiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker: str | None = None
    tone: str | None = None
    speed: float | None = None
    read_aloud: StrictBool | None = None
    correct_speech: StrictBool | None = None
    correct_english: StrictBool | None = None   # the switch's old name (§4): still taken
    language: str | None = None

    @field_validator("speaker")
    @classmethod
    def _speaker(cls, value: str | None) -> str | None:
        return None if value is None else check_speaker(value)

    @field_validator("tone")
    @classmethod
    def _tone(cls, value: str | None) -> str | None:
        return None if value is None else check_tone(value)

    @field_validator("speed")
    @classmethod
    def _speed(cls, value: float | None) -> float | None:
        return None if value is None else check_speed(value)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        return None if value is None else check_language(value)

    def patch(self) -> VoicePatch:
        return VoicePatch(speaker=self.speaker, tone=self.tone, speed=self.speed, read_aloud=self.read_aloud,
                          correct_speech=merged_correct(self.correct_speech, self.correct_english),
                          language=self.language)


def parse_voice_args(arguments: dict[str, Any]) -> VoicePatch | None:
    """The patch the arguments ask for; ``None`` when they are off the lists or name nothing."""
    try:
        patch = SetMyVoiceArgs.model_validate(arguments).patch()
    except ValidationError:
        return None
    return patch if patch.fields() else None


def _words(patch: VoicePatch) -> list[str]:
    parts: list[str] = []
    if patch.speaker is not None:
        parts.append(f"voice {_SPEAKER_NAMES.get(patch.speaker, patch.speaker)}")
    if patch.tone is not None:
        parts.append(f"tone {TONES[patch.tone].name}")
    if patch.speed is not None:
        parts.append(f"speed {patch.speed:g}")
    if patch.read_aloud is not None:
        parts.append(f"read replies aloud {'on' if patch.read_aloud else 'off'}")
    if patch.correct_speech is not None:
        parts.append(f"Correct what I say {'on' if patch.correct_speech else 'off'}")
    if patch.language is not None:
        parts.append(f"language {_language_name(patch.language)}")
    return parts


def _language_name(code: str) -> str:
    if code == VOICE_LANGUAGE_AUTO:
        return VOICE_LANGUAGE_AUTO_NAME
    return VOICE_LANGUAGE_BY_ID[code].name if code in VOICE_LANGUAGE_BY_ID else code


def voice_changed_text(patch: VoicePatch) -> str:
    """The tool result: what changed, in fixed words ("Changed my voice: speed 1.5, tone Warm")."""
    return f"Changed my voice: {', '.join(_words(patch))}."


class VoiceTools:
    names: frozenset[str] = frozenset({SET_MY_VOICE_TOOL})

    def __init__(self, service: VoiceSettingsService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return VOICE_CHANGING_ACTIVITY

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        return await self.execute(name, arguments, ctx)

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        """The Ask card's step: the change in words; a bad call is refused with a sentence, no card."""
        patch = parse_voice_args(arguments)
        if patch is None:
            return BAD_VOICE_ARGS
        return PendingCall(tool=name, arguments=dict(patch.fields()), topic="team", title=VOICE_CHANGE_TITLE,
                           detail=", ".join(_words(patch)))

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """The stored call (a card's Yes) or the live one: only the calling bot's own settings change."""
        patch = parse_voice_args(resolved)
        if patch is None:
            return ToolOutcome(BAD_VOICE_ARGS, failed=True)
        updated = await self._service.save(ctx.user_id, ctx.bot_id, patch)
        if updated is None:
            return ToolOutcome(_NOT_YOURS, failed=True)
        return ToolOutcome(voice_changed_text(patch))
