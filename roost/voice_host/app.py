"""The voice service's HTTP face (127.0.0.1:18804 only): every route needs a request signed with ``voice.secret``
(the same ``X-Roost-*`` scheme as the keeper's, its own secret). Hearing and speaking each run one at a time in a
worker thread, and at the same time as each other (a call hears the next turn while the last reply is spoken);
warming takes both. Nothing heard or said is logged: ``roost.voice.timing`` keeps lengths and times at INFO.

- ``GET /health`` → ``{"ok": true, "loaded": [...], "warm": <both loaded>}`` (no lock: it answers while a job runs)
- ``POST /transcribe`` — a WAV body (``read_wav``'s rules) → ``{"text"}``
- ``POST /hear`` — the hear envelope (``roost/voice/envelope.py``: a hint of context terms, a language and whether
  this is a live partial, then the WAV) → ``{"text"}`` (voice tuning D1); the log keeps the hint's size, never
  its words
- ``POST /warm`` → ``{"ok": true}`` once both models are loaded (a call is about to start)
- ``POST /speak`` — ``{"text", "speaker", "tone"}`` → ``audio/wav``; the tone's words come from ``TONES``, never
  from the request."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.desk.signing import NonceCache, verify
from roost.voice.constants import SPEAKER_IDS, TONES, VOICE_PART_CHARS_MAX
from roost.voice.envelope import EnvelopeError, HearHint, unpack_hear
from roost.voice.wav import WavError, WavInfo, read_wav
from roost.voice_host.engine import Engine

logger = logging.getLogger(__name__)
TIMING_LOGGER = "roost.voice.timing"
timing = logging.getLogger(TIMING_LOGGER)

_UNSIGNED = "missing or invalid request signature"
_IDLE_CHECK_S = 30.0


class SpeakIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=VOICE_PART_CHARS_MAX)
    speaker: str
    tone: str

    @field_validator("speaker")
    @classmethod
    def _speaker(cls, value: str) -> str:
        if value not in SPEAKER_IDS:
            raise ValueError("unknown speaker")
        return value

    @field_validator("tone")
    @classmethod
    def _tone(cls, value: str) -> str:
        if value not in TONES:
            raise ValueError("unknown tone")
        return value


async def _signed(request: Request) -> bytes:
    body = await request.body()
    ok = verify(request.app.state.secret, request.method, request.url.path, body, request.headers,
                now=int(time.time()), seen=request.app.state.nonces)
    if not ok:
        raise HTTPException(status_code=401, detail=_UNSIGNED)
    return body


Signed = Depends(_signed)


async def _unload_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(_IDLE_CHECK_S)
        async with app.state.hear_job, app.state.speak_job:
            await asyncio.to_thread(app.state.engine.unload_idle, time.monotonic())


def _is_warm(engine: Engine) -> bool:
    return {"hear", "speak"} <= set(engine.loaded())


def create_app(secret: str, engine: Engine, *, unload_loop: bool = True) -> FastAPI:
    timing.setLevel(logging.INFO)   # always on, whatever the root level: durations and sizes only

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_unload_loop(app)) if unload_loop else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()

    app = FastAPI(title="Roost voice", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.secret = secret
    app.state.engine = engine
    app.state.nonces = NonceCache()
    app.state.hear_job = asyncio.Lock()
    app.state.speak_job = asyncio.Lock()
    _add_routes(app, engine)
    return app


def _add_routes(app: FastAPI, engine: Engine) -> None:
    @app.get("/health")
    async def health(_: bytes = Signed) -> dict[str, object]:
        return {"ok": True, "loaded": engine.loaded(), "warm": _is_warm(engine)}

    async def _hear(recording: WavInfo, hint: HearHint) -> dict[str, str]:
        started = time.monotonic()
        async with app.state.hear_job:
            text = await asyncio.to_thread(engine.hear, recording, hint)
        timing.info("voice: heard %.1f s in %.1f s (%d chars, %d terms%s%s)", recording.seconds,
                    time.monotonic() - started, len(text), len(hint.terms),
                    f", {hint.language}" if hint.language else "", ", partial" if hint.partial else "")
        return {"text": text}

    @app.post("/transcribe")
    async def transcribe(body: bytes = Signed) -> dict[str, str]:
        try:
            recording = read_wav(body)
        except WavError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await _hear(recording, HearHint())

    @app.post("/hear")
    async def hear(body: bytes = Signed) -> dict[str, str]:
        try:
            hint, wav = unpack_hear(body)
            recording = read_wav(wav)
        except (EnvelopeError, WavError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await _hear(recording, hint)

    @app.post("/warm")
    async def warm(_: bytes = Signed) -> dict[str, bool]:
        started = time.monotonic()
        async with app.state.hear_job, app.state.speak_job:
            await asyncio.to_thread(engine.warm)
        timing.info("voice: warm in %.1f s", time.monotonic() - started)
        return {"ok": True}

    @app.post("/speak")
    async def speak(body: bytes = Signed) -> Response:
        try:
            wanted = SpeakIn.model_validate_json(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Give text, a listed speaker and a listed tone.") from exc
        started = time.monotonic()
        async with app.state.speak_job:
            audio = await asyncio.to_thread(engine.speak, wanted.text, wanted.speaker, TONES[wanted.tone].instruct)
        timing.info("voice: spoke %d chars in %.1f s (%d bytes)", len(wanted.text), time.monotonic() - started,
                    len(audio))
        return Response(content=audio, media_type="audio/wav")
