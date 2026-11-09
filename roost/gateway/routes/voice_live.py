"""Call mode (docs/plans/2026-10-30-roost-voice.md §3): the call registry's routes, a call reply's live speech and
the fixed spoken lines.

- ``POST /api/threads/{thread_id}/call`` — start or beat the thread's call (``{"interrupted": "<message_id>"}``
  when you cut the bot off); it also keeps the voice models warm. ``DELETE`` ends it (idempotent).
- ``GET /api/threads/{thread_id}/live-speech/{message_id}`` → ``{"parts", "done", "speed"}`` and ``…/{part}`` →
  ``audio/wav``: a reply spoken ahead during a call on your own thread; 404 for anything else, and for a part not
  ready yet (``speech_ready`` frames say when).
- ``GET /api/bots/{bot_id}/voice/line/{key}`` → ``audio/wav``: one of ``VOICE_LINES`` in the bot's voice.

Owner checks go through the thread or the bot; another user's ids are 404."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import MESSAGE_ID_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.voice import WAV, no_store, speak_cached, voice_call
from roost.voice.constants import VOICE_CALL_EXPIRES_S, VOICE_LINE_CACHE_KEY, VOICE_LINES, VOICE_WARM_KEEP_S

logger = logging.getLogger(__name__)
voice_live_router = APIRouter(tags=["voice"])

_THREAD_NOT_FOUND = "Thread not found"
_ROOM_TEXT = "A call is with one bot. Open its chat instead."
_BAD_CALL_BODY = "The call body is {} or {\"interrupted\": \"<message id>\"}."
_NOT_READY = "That part isn't ready yet"
_NOT_LIVE = "No live speech for that message"
_LINE_NOT_FOUND = "No such line"


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interrupted: str | None = Field(default=None, min_length=1, max_length=MESSAGE_ID_MAX)


async def call_body(request: Request) -> CallIn:
    """``CallIn`` from the body; an empty body (or none) is ``{}``."""
    raw = await request.body()
    if not raw.strip():
        return CallIn()
    try:
        return CallIn.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_BAD_CALL_BODY) from exc


async def _own_thread(request: Request, user_id: str, thread_id: str):
    thread = await request.app.state.talk.get_thread(user_id, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=_THREAD_NOT_FOUND)
    return thread


def _keep_warm(request: Request) -> None:
    """Load (or keep) the voice models, at most once per ``VOICE_WARM_KEEP_S``, without holding the request."""
    state = request.app.state
    now = time.monotonic()
    if now - state.voice_warmed_at < VOICE_WARM_KEEP_S:
        return
    state.voice_warmed_at = now
    state.voice_tasks.spawn(_warm_quietly(request), name="voice warm")


async def _warm_quietly(request: Request) -> None:
    try:
        await request.app.state.voice.warm()
    except Exception as exc:   # the service may be off: the call goes on without speech until it answers
        logger.warning("voice warm failed: %s", type(exc).__name__)


@voice_live_router.post("/api/threads/{thread_id}/call", dependencies=[RequireOrigin])
async def start_or_beat_call(thread_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    thread = await _own_thread(request, user.id, thread_id)
    if thread.kind == "room":
        raise HTTPException(status_code=409, detail=_ROOM_TEXT)
    body = await call_body(request)
    state = request.app.state
    state.calls.beat(user.id, thread_id, thread.bot_id)
    if body.interrupted is not None:
        state.calls.interrupt(thread_id, body.interrupted)
        state.speak_ahead.interrupt(thread_id, body.interrupted)
    _keep_warm(request)
    return {"ok": True, "expires_in": int(VOICE_CALL_EXPIRES_S)}


@voice_live_router.delete("/api/threads/{thread_id}/call", dependencies=[RequireOrigin])
async def end_call(thread_id: str, request: Request, user: CurrentUser) -> dict[str, bool]:
    await _own_thread(request, user.id, thread_id)
    request.app.state.calls.end(thread_id)
    request.app.state.speak_ahead.end_call(thread_id)
    return {"ok": True}


async def _live_track(request: Request, user_id: str, thread_id: str, message_id: str):
    await _own_thread(request, user_id, thread_id)
    track = request.app.state.speak_ahead.track(message_id)
    if track is None or track.thread_id != thread_id or track.user_id != user_id or track.voice is None:
        raise HTTPException(status_code=404, detail=_NOT_LIVE)
    return track


@voice_live_router.get("/api/threads/{thread_id}/live-speech/{message_id}")
async def live_speech_plan(thread_id: str, message_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    track = await _live_track(request, user.id, thread_id, message_id)
    return {"parts": track.parts_ready, "done": track.done, "speed": track.voice.speed}


@voice_live_router.get("/api/threads/{thread_id}/live-speech/{message_id}/{part}")
async def live_speech_part(thread_id: str, message_id: str, part: int, request: Request, user: CurrentUser) -> Response:
    track = await _live_track(request, user.id, thread_id, message_id)
    made_in = track.part_voice(part)    # the voice this part was spoken in, even if the bot's voice changed since (§4)
    audio = None if made_in is None else request.app.state.voice_cache.get((message_id, part, *made_in))
    if audio is None or not 0 <= part < track.parts_ready:
        raise HTTPException(status_code=404, detail=_NOT_READY)
    return Response(content=audio, media_type=WAV, headers=no_store())


@voice_live_router.get("/api/bots/{bot_id}/voice/line/{key}")
async def voice_line(bot_id: str, key: str, request: Request, user: CurrentUser) -> Response:
    bot = await request.app.state.bots.get(user.id, bot_id)
    if bot is None or key not in VOICE_LINES:
        raise HTTPException(status_code=404, detail=_LINE_NOT_FOUND)
    cache_key = (VOICE_LINE_CACHE_KEY, key, bot.voice.speaker, bot.voice.tone)
    audio = await voice_call(speak_cached(request, user.id, cache_key, VOICE_LINES[key], bot.voice))
    return Response(content=audio, media_type=WAV, headers=no_store())
