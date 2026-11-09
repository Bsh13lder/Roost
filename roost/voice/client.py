"""The gateway's way to the voice service: ``VoiceClient`` signs each request with ``voice.secret`` and maps every
failure to ``VoiceUnavailable`` (the service is off or unreachable) or ``VoiceFailed`` (it answered with an error).
``FakeVoice`` stands in under ``ROOST_VOICE=fake`` (tests and the scripted E2E). Recordings and replies are never
logged."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.voice.constants import (
    VOICE_HEALTH_CACHE_S,
    VOICE_HEALTH_TIMEOUT_S,
    VOICE_HEAR_FALLBACK_S,
    VOICE_HEAR_TIMEOUT_S,
    VOICE_SERVICE_TIMEOUT_S,
)
from roost.voice.envelope import HearHint, pack_hear
from roost.voice_host.engine import FakeEngine
from roost.voice.wav import read_wav

logger = logging.getLogger(__name__)

_NOT_FOUND = "404"


class VoiceUnavailable(Exception):
    """The voice service can't be reached."""


class VoiceFailed(Exception):
    """The voice service answered with an error."""


class Voice(Protocol):
    async def available(self) -> bool: ...

    async def transcribe(self, wav: bytes, hint: HearHint | None = None) -> str: ...

    async def speak(self, text: str, speaker: str, tone: str) -> bytes: ...

    async def warm(self) -> None: ...

    async def aclose(self) -> None: ...


_WARM_SLOTS = frozenset({"hear", "speak"})


class VoiceClient:
    """One keep-alive connection to the service for the whole process (``aclose`` at shutdown)."""

    def __init__(self, config: RoostConfig, transport: httpx.AsyncBaseTransport | None = None,
                 clock=time.monotonic) -> None:
        self._base = config.voice_url.rstrip("/")
        self._secret = config.voice_secret
        self._transport = transport
        self._clock = clock
        self._health: tuple[float, bool] | None = None
        self._warm_seen = False    # the health check has shown both models loaded
        self._hear_missing_at: float | None = None   # the service answered 404 to /hear (an old one) at this time
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport, timeout=VOICE_SERVICE_TIMEOUT_S)
        return self._client

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def _call(self, method: str, path: str, body: bytes, timeout_s: float,
                    content_type: str = "application/octet-stream") -> httpx.Response:
        headers = {**signed_headers(self._secret, method, path, body), "Content-Type": content_type}
        try:
            response = await self._http().request(method, self._base + path, content=body, headers=headers,
                                                  timeout=timeout_s)
        except httpx.HTTPError as exc:
            self._health = (self._clock(), False)
            raise VoiceUnavailable(type(exc).__name__) from exc
        if response.status_code != 200:
            logger.warning("voice service %s %s answered %s", method, path, response.status_code)
            raise VoiceFailed(str(response.status_code))
        return response

    def _note_health(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        loaded = payload.get("loaded")
        warm = payload.get("warm") is True or (isinstance(loaded, list) and _WARM_SLOTS <= set(map(str, loaded)))
        self._warm_seen = bool(warm)

    async def available(self) -> bool:
        """Whether the service answers its health check; remembered for ``VOICE_HEALTH_CACHE_S``."""
        now = self._clock()
        if self._health is not None and now - self._health[0] < VOICE_HEALTH_CACHE_S:
            return self._health[1]
        try:
            response = await self._call("GET", "/health", b"", VOICE_HEALTH_TIMEOUT_S)
            self._note_health(response.json())
            ok = True
        except (VoiceUnavailable, VoiceFailed, ValueError):
            ok = False
        self._health = (now, ok)
        return ok

    def _hear_route_missing(self) -> bool:
        at = self._hear_missing_at
        return at is not None and self._clock() - at < VOICE_HEAR_FALLBACK_S

    async def transcribe(self, wav: bytes, hint: HearHint | None = None) -> str:
        """The recording's words. Once the service has been seen warm, a transcript waits ``VOICE_HEAR_TIMEOUT_S``
        at most; before that the long wait allows for a model load. With a ``hint`` (voice tuning D1) the recording
        goes in the ``/hear`` envelope; a service too old to have that route (a 404) gets the plain ``/transcribe``
        instead, remembered for ``VOICE_HEAR_FALLBACK_S``, so dictation never breaks before ``make voice-update``."""
        timeout_s = VOICE_HEAR_TIMEOUT_S if self._warm_seen else VOICE_SERVICE_TIMEOUT_S
        if hint is not None and not self._hear_route_missing():
            try:
                response = await self._call("POST", "/hear", pack_hear(hint, wav), timeout_s)
                return str(response.json().get("text", "")).strip()
            except VoiceFailed as exc:
                if str(exc) != _NOT_FOUND:
                    raise
                self._hear_missing_at = self._clock()
                logger.warning("the voice service has no /hear yet (run make voice-update); hearing with no hints")
        response = await self._call("POST", "/transcribe", wav, timeout_s, "audio/wav")
        return str(response.json().get("text", "")).strip()

    async def speak(self, text: str, speaker: str, tone: str) -> bytes:
        body = json.dumps({"text": text, "speaker": speaker, "tone": tone}).encode()
        response = await self._call("POST", "/speak", body, VOICE_SERVICE_TIMEOUT_S, "application/json")
        read_wav(response.content)   # only a real WAV goes on to a browser or phone
        return response.content

    async def warm(self) -> None:
        await self._call("POST", "/warm", b"", VOICE_SERVICE_TIMEOUT_S)


@dataclass
class FakeVoice:
    """The fake engine behind the same calls, with no service: hears ``engine.heard`` and speaks silence."""

    engine: FakeEngine = field(default_factory=FakeEngine)
    on: bool = True

    async def available(self) -> bool:
        return self.on

    async def transcribe(self, wav: bytes, hint: HearHint | None = None) -> str:
        if not self.on:
            raise VoiceUnavailable("off")
        return self.engine.hear(read_wav(wav), hint or HearHint())

    async def speak(self, text: str, speaker: str, tone: str) -> bytes:
        if not self.on:
            raise VoiceUnavailable("off")
        return self.engine.speak(text, speaker, tone)

    async def warm(self) -> None:
        if not self.on:
            raise VoiceUnavailable("off")
        self.engine.warm()

    async def aclose(self) -> None:
        return None


def make_voice(config: RoostConfig) -> Voice:
    return FakeVoice() if config.voice_mode == "fake" else VoiceClient(config)
