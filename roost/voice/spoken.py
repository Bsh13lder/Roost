"""Which messages can be read aloud and with what words: a bot's own text reply, or a Report's text (its headline
when it has none). Anything else — your messages, cards, lines, reactions — has nothing to say. A small in-memory
cache keeps the last parts made, so playing a reply again is instant; it never reaches disk."""

from __future__ import annotations

from collections import OrderedDict

from pydantic import ValidationError

from roost.routines.models import ReportBody
from roost.talk.chat_feel import shown_reply
from roost.talk.store import Message
from roost.voice.constants import VOICE_CACHE_PARTS
from roost.voice.speech_text import speech_parts

_BOT_ROLE = "bot"
_TEXT_KIND = "text"
_REPORT_KIND = "report"


def message_parts(message: Message) -> list[str]:
    """The parts ``message`` is spoken in; empty when there is nothing to read aloud."""
    if message.role != _BOT_ROLE:
        return []
    if message.kind == _TEXT_KIND:
        return speech_parts(shown_reply(message.body))   # the "On it: …" lead is the working line, never read aloud
    if message.kind == _REPORT_KIND:
        try:
            report = ReportBody.model_validate_json(message.body)
        except ValidationError:
            return []
        return speech_parts(report.text or report.headline)
    return []


CacheKey = tuple[str, int, str, str]   # message id, part, speaker, tone


class SpeechCache:
    def __init__(self, size: int = VOICE_CACHE_PARTS) -> None:
        self._size = size
        self._parts: OrderedDict[CacheKey, bytes] = OrderedDict()

    def get(self, key: CacheKey) -> bytes | None:
        audio = self._parts.get(key)
        if audio is not None:
            self._parts.move_to_end(key)
        return audio

    def put(self, key: CacheKey, audio: bytes) -> None:
        self._parts[key] = audio
        self._parts.move_to_end(key)
        while len(self._parts) > self._size:
            self._parts.popitem(last=False)
