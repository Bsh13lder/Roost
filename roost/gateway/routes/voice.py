"""Voice (docs/plans/2026-10-30-roost-voice.md): what you say becomes text, and a bot's reply can be heard.

- ``GET /api/voice`` — whether the Mac's voice service answers, and the voices, tones and speeds to pick from.
- ``PUT /api/bots/{bot_id}/voice`` — a bot's voice, tone, speed and Read replies aloud (owner only).
- ``GET /api/bots/{bot_id}/voice/sample?speaker=&tone=`` — a fixed sample line in that voice, for Try it.
- ``POST /api/voice/transcribe?bot_id=`` — a WAV recording (``read_wav``'s rules) → ``{"text"}``; one at a time per
  user. The text goes back to the composer: only your Send makes it a message, so it is your own words like typing.
  With ``bot_id`` (voice tuning D1/D2) the hearing model reads that bot's hint first: names and site names from your
  own words and choices, and the bot's chosen language.
- ``POST /api/voice/partial?bot_id=`` — the recording so far (at most ``VOICE_PARTIAL_MAX_S``) while the mic is still
  open → ``{"text"}``, the live words (voice tuning D4); one hearing per user: a partial while one is heard is
  a 429 the client skips, and a final transcript waits for the partial in flight instead of being refused.
- ``POST /api/voice/correct`` — ``{"text", "bot_id"}`` → ``{"corrected", "fixes", "changed"}``: Correct what I say
  before the send (voice tuning D3), on the worker model with that bot's hint; off, slow or nothing to fix gives
  the words back unchanged with ``changed: false``.
- ``POST /api/voice/warm`` — load both models now, as a call opens, so the first answer doesn't wait for them;
  with ``{"bot_id"}`` it also pre-makes that bot's fixed call lines in the background.
- ``GET /api/threads/{thread_id}/messages/{message_id}/speech`` → ``{"parts", "speed"}`` and
  ``…/speech/{part}`` → ``audio/wav`` in the bot's voice: only a bot's reply or Report in your own thread.

A service that can't be reached is a 503 with ``VOICE_OFF_TEXT``. Recordings and audio are never stored or logged.
Call mode's routes (the registry, live speech, the fixed lines) are in ``roost/gateway/routes/voice_live.py``."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, TypeVar

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.bots.service import bot_out
from roost.constants import MAX_RECORD_ID_LENGTH
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.voice.client import VoiceFailed, VoiceUnavailable
from roost.voice.constants import (
    SPEAKER_IDS,
    SPEAKERS,
    SPEEDS,
    TONES,
    VOICE_BAD_AUDIO_TEXT,
    VOICE_BUSY_TEXT,
    VOICE_CORRECT_TEXT_CHARS_MAX,
    VOICE_FAILED_TEXT,
    VOICE_LANGUAGE_AUTO,
    VOICE_LANGUAGE_AUTO_NAME,
    VOICE_LANGUAGES,
    VOICE_LINE_CACHE_KEY,
    VOICE_LINES,
    VOICE_MAX_SECONDS,
    VOICE_NOT_SPOKEN_TEXT,
    VOICE_OFF_TEXT,
    VOICE_PARTIAL_MAX_S,
    VOICE_PARTIAL_WAV_BYTES_MAX,
    VOICE_SAMPLE_TEXT,
    VOICE_WAV_BYTES_MAX,
    VoiceSettings,
)
from roost.voice.service import VoiceSettingsService
from roost.voice.settings import VoiceIn
from roost.voice.spoken import CacheKey, message_parts
from roost.voice.wav import WavError, read_wav

logger = logging.getLogger(__name__)
voice_router = APIRouter(tags=["voice"])

WAV = "audio/wav"
_NO_STORE = {"Cache-Control": "no-store"}
_MESSAGE_NOT_FOUND = "Message not found"
_BAD_WARM_BODY = "The warm body is {} or {\"bot_id\": \"<bot id>\"}."
T = TypeVar("T")


def no_store() -> dict[str, str]:
    return dict(_NO_STORE)


async def voice_call(work: Awaitable[T]) -> T:
    """Run a voice service call under a route: off is 503, a failure 502."""
    try:
        return await work
    except VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=VOICE_OFF_TEXT) from exc
    except (VoiceFailed, WavError) as exc:
        logger.warning("voice call failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=VOICE_FAILED_TEXT) from exc





def speak_lock_for(locks: dict[str, asyncio.Lock], user_id: str) -> asyncio.Lock:
    """One spoken part at a time per user (shared with the speak-ahead)."""
    return locks.setdefault(user_id, asyncio.Lock())


def _speak_lock(request: Request, user_id: str) -> asyncio.Lock:
    return speak_lock_for(request.app.state.voice_speak_locks, user_id)


async def speak_cached(request: Request, user_id: str, key: CacheKey, words: str, voice: VoiceSettings) -> bytes:
    """The cached audio under ``key``, or ``words`` spoken now in ``voice`` and kept there."""
    cache = request.app.state.voice_cache
    audio = cache.get(key)
    if audio is None:
        async with _speak_lock(request, user_id):
            audio = await request.app.state.voice.speak(words, voice.speaker, voice.tone)
        cache.put(key, audio)
    return audio


class WarmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_id: str | None = Field(default=None, min_length=1, max_length=MAX_RECORD_ID_LENGTH)


async def _warm_body(request: Request) -> WarmIn:
    raw = await request.body()
    if not raw.strip():
        return WarmIn()
    try:
        return WarmIn.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_BAD_WARM_BODY) from exc


async def _make_lines(request: Request, user_id: str, voice: VoiceSettings) -> None:
    """Every fixed call line in ``voice``, into the cache (the ones already there are skipped)."""
    for key, words in VOICE_LINES.items():
        try:
            await speak_cached(request, user_id, (VOICE_LINE_CACHE_KEY, key, voice.speaker, voice.tone), words, voice)
        except (VoiceUnavailable, VoiceFailed, WavError) as exc:
            logger.warning("could not pre-make the call lines: %s", type(exc).__name__)
            return


@voice_router.get("/api/voice")
async def voice_info(request: Request, user: CurrentUser):
    return {
        "available": await request.app.state.voice.available(),
        "speakers": [{"id": s.id, "name": s.name, "best_in": s.best_in} for s in SPEAKERS],
        "tones": [{"id": key, "name": tone.name} for key, tone in TONES.items()],
        "speeds": list(SPEEDS),
        # Voice tuning D2: Auto-detect first, then exactly the languages the hearing model supports.
        "languages": [{"id": VOICE_LANGUAGE_AUTO, "name": VOICE_LANGUAGE_AUTO_NAME},
                      *({"id": lang.id, "name": lang.name} for lang in VOICE_LANGUAGES)],
    }


@voice_router.put("/api/bots/{bot_id}/voice", dependencies=[RequireOrigin])
async def set_voice(bot_id: str, body: VoiceIn, request: Request, user: CurrentUser):
    """The Info tab's save, through the same ``VoiceSettingsService`` as a bot's own ``set_my_voice`` (§4); it
    publishes the ``bot_updated`` frame. The switch (``correct_speech``, or its old name ``correct_english``) and
    ``language`` may be left out: the stored values stay."""
    state = request.app.state
    updated = await VoiceSettingsService(state.bots, state.events).save(
        user.id, bot_id, body.patch(), activity=state.activity_board.get(bot_id))
    if updated is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot_out(updated, state.activity_board.get(updated.id))


@voice_router.get("/api/bots/{bot_id}/voice/sample")
async def voice_sample(bot_id: str, speaker: str, tone: str, request: Request, user: CurrentUser):
    if await request.app.state.bots.get(user.id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if speaker not in SPEAKER_IDS or tone not in TONES:
        raise HTTPException(status_code=422, detail="Pick one of the listed voices and tones.")
    async with _speak_lock(request, user.id):
        audio = await voice_call(request.app.state.voice.speak(VOICE_SAMPLE_TEXT, speaker, tone))
    return Response(content=audio, media_type=WAV, headers=no_store())


async def _bot_for_hint(request: Request, user_id: str, bot_id: str | None) -> str | None:
    """The bot the hint is built for: ``None`` when none was named; 404 for one that is not this user's."""
    if bot_id is None:
        return None
    if len(bot_id) > MAX_RECORD_ID_LENGTH or await request.app.state.bots.get(user_id, bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot_id


async def _hear(request: Request, user_id: str, bot_id: str | None, *, partial: bool, bytes_max: int) -> str:
    """One hearing at a time per user, checked as a WAV before the service hears it with that bot's hint
    (``roost/voice/context.py``). A final recording waits for a live partial still being heard, so stopping the mic
    never loses your words; a partial that comes while anything is heard is refused (429) and the client skips it."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > bytes_max:
        raise HTTPException(status_code=413, detail=VOICE_BAD_AUDIO_TEXT)
    bot = await _bot_for_hint(request, user_id, bot_id)
    hearing = request.app.state.voice_hearing.setdefault(user_id, asyncio.Lock())
    if partial and hearing.locked():
        raise HTTPException(status_code=429, detail=VOICE_BUSY_TEXT)
    body = await request.body()
    try:
        if len(body) > bytes_max or read_wav(body).seconds > (VOICE_PARTIAL_MAX_S if partial else VOICE_MAX_SECONDS):
            raise WavError("too long")
    except WavError as exc:
        raise HTTPException(status_code=422, detail=VOICE_BAD_AUDIO_TEXT) from exc
    hint = await request.app.state.hear_hints.for_bot(user_id, bot, partial=partial)
    if partial and hearing.locked():  # a final came while this one was read: it goes first
        raise HTTPException(status_code=429, detail=VOICE_BUSY_TEXT)
    async with hearing:
        return await voice_call(request.app.state.voice.transcribe(body, hint))


@voice_router.post("/api/voice/transcribe", dependencies=[RequireOrigin])
async def transcribe(request: Request, user: CurrentUser, bot_id: str | None = None):
    text = await _hear(request, user.id, bot_id, partial=False, bytes_max=VOICE_WAV_BYTES_MAX)
    return {"text": text}


@voice_router.post("/api/voice/partial", dependencies=[RequireOrigin])
async def partial(request: Request, user: CurrentUser, bot_id: str | None = None):
    """The live words of a recording still going (voice tuning D4)."""
    text = await _hear(request, user.id, bot_id, partial=True, bytes_max=VOICE_PARTIAL_WAV_BYTES_MAX)
    return {"text": text}


class CorrectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=VOICE_CORRECT_TEXT_CHARS_MAX)
    bot_id: str = Field(min_length=1, max_length=MAX_RECORD_ID_LENGTH)


@voice_router.post("/api/voice/correct", dependencies=[RequireOrigin])
async def correct(body: CorrectIn, request: Request, user: CurrentUser):
    """What you said, cleaned up for the composer (voice tuning D3); the switch off or no change: unchanged."""
    state = request.app.state
    if await state.bots.get(user.id, body.bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    correction = await state.english.correct_now(user.id, body.bot_id, body.text)
    if correction is None:
        return {"corrected": body.text, "fixes": [], "changed": False}
    return {"corrected": correction.corrected,
            "fixes": [{"wrong": wrong, "right": right} for wrong, right in correction.fixes], "changed": True}


@voice_router.post("/api/voice/warm", dependencies=[RequireOrigin])
async def warm(request: Request, user: CurrentUser):
    body = await _warm_body(request)
    await voice_call(request.app.state.voice.warm())
    bot = await request.app.state.bots.get(user.id, body.bot_id) if body.bot_id is not None else None
    if bot is not None:
        request.app.state.voice_tasks.spawn(_make_lines(request, user.id, bot.voice), name=f"voice lines {bot.id}")
    return {"ok": True}


async def _spoken_message(request: Request, user_id: str, thread_id: str, message_id: str):
    talk = request.app.state.talk
    thread = await talk.get_thread(user_id, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=_MESSAGE_NOT_FOUND)
    message = await talk.get_message(user_id, message_id)
    if message is None or message.thread_id != thread_id:
        raise HTTPException(status_code=404, detail=_MESSAGE_NOT_FOUND)
    parts = message_parts(message)
    if not parts:
        raise HTTPException(status_code=404, detail=VOICE_NOT_SPOKEN_TEXT)
    bot = await request.app.state.bots.get(user_id, message.author_bot_id or thread.bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail=_MESSAGE_NOT_FOUND)
    return parts, bot.voice


@voice_router.get("/api/threads/{thread_id}/messages/{message_id}/speech")
async def speech_plan(thread_id: str, message_id: str, request: Request, user: CurrentUser):
    parts, voice = await _spoken_message(request, user.id, thread_id, message_id)
    return {"parts": len(parts), "speed": voice.speed}


@voice_router.get("/api/threads/{thread_id}/messages/{message_id}/speech/{part}")
async def speech_part(thread_id: str, message_id: str, part: int, request: Request, user: CurrentUser):
    parts, voice = await _spoken_message(request, user.id, thread_id, message_id)
    if not 0 <= part < len(parts):
        raise HTTPException(status_code=404, detail=_MESSAGE_NOT_FOUND)
    audio = await voice_call(speak_cached(request, user.id, (message_id, part, voice.speaker, voice.tone), parts[part], voice))
    return Response(content=audio, media_type=WAV, headers=no_store())
