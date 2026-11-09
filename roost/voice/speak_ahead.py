"""Speak-ahead (docs/plans/2026-10-30-roost-voice.md §3, contract B): while a thread is in a call, a reply is spoken
as it streams. ``SpeakAhead.listen`` is an ``EventHub`` listener (quick, publishes nothing itself): a bot's
placeholder ``message`` frame in a call thread opens a ``ReplyTrack``; each ``text_delta`` adds to its text and
wakes one worker task per reply, which cuts the text with ``call_parts``, speaks every new part under the user's
speak lock into the speech cache (the same key the ``/speech`` route uses) and publishes a live-only
``speech_ready`` frame; ``message_done`` lets the open tail be spoken and ends with ``done: true``. An interrupt
stops the rest. Tracks are frozen and replaced; they are dropped on call end or after ``VOICE_TRACK_KEEP_S``."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from roost.voice.calls import CallRegistry
from roost.voice.client import Voice, VoiceFailed, VoiceUnavailable
from roost.voice.constants import VOICE_LIVE_TYPE, VOICE_TRACK_KEEP_S, VoiceSettings
from roost.voice.sentences import call_parts
from roost.voice.settings import voice_from_dict
from roost.voice.spoken import SpeechCache
from roost.voice.tasks import TrackedTasks
from roost.voice.wav import WavError

logger = logging.getLogger(__name__)

_BOT_ROLE = "bot"
_TEXT_KIND = "text"
_PLACEHOLDER_SEQ = 0
_NO_PART = -1   # the done frame's part when no part was made


class _Publisher(Protocol):
    async def publish(self, user_id: str, event: dict[str, Any]) -> int: ...


class _BotLookup(Protocol):
    async def get(self, user_id: str, bot_id: str) -> Any: ...


@dataclass(frozen=True)
class ReplyTrack:
    message_id: str
    thread_id: str
    bot_id: str
    user_id: str
    opened_at: float
    text: str = ""
    parts_ready: int = 0
    streamed: bool = False       # message_done seen: the text is complete
    done: bool = False           # nothing more will be spoken (every part made, interrupted, or failed)
    interrupted: bool = False
    voice: VoiceSettings | None = None   # the bot's voice, read by the worker; a bot_updated frame replaces it (§4)
    part_voices: tuple[tuple[str, str], ...] = ()   # the (speaker, tone) each ready part was spoken in: its cache key

    def part_voice(self, part: int) -> tuple[str, str] | None:
        """The speaker and tone part ``part`` was made in (the voice may have changed since)."""
        if 0 <= part < len(self.part_voices):
            return self.part_voices[part]
        return None if self.voice is None else (self.voice.speaker, self.voice.tone)


class SpeakAhead:
    def __init__(self, events: _Publisher, bots: _BotLookup, voice: Voice, cache: SpeechCache, calls: CallRegistry,
                 speak_lock_for: Callable[[str], asyncio.Lock], clock: Callable[[], float] = time.monotonic) -> None:
        self._events = events
        self._bots = bots
        self._voice = voice
        self._cache = cache
        self._calls = calls
        self._lock_for = speak_lock_for
        self._clock = clock
        self._tracks: Mapping[str, ReplyTrack] = MappingProxyType({})
        self._workers: Mapping[str, asyncio.Task[None]] = MappingProxyType({})
        self._tasks = TrackedTasks()

    # --- the listener -------------------------------------------------------------------------------------------

    def listen(self, user_id: str, frame: dict[str, Any]) -> None:
        kind = frame.get("type")
        if kind == "message":
            self._on_message(user_id, frame)
        elif kind == "text_delta":
            self._on_delta(frame)
        elif kind == "message_done":
            self._on_done(frame)
        elif kind == "bot_updated":
            self._on_bot_updated(frame)

    def _on_bot_updated(self, frame: dict[str, Any]) -> None:
        """§4: the bot's voice changed (the Info tab, or its own set_my_voice): a reply still being spoken uses the
        new voice from its next part. A frame whose voice doesn't fit changes nothing."""
        bot = frame.get("bot") or {}
        bot_id = str(bot.get("id") or "")
        voice = voice_from_dict(bot.get("voice") or {})
        if not bot_id or voice is None:
            return
        for track in tuple(self._tracks.values()):
            if track.bot_id == bot_id and not track.done and track.voice is not None:
                self._put(replace(track, voice=voice))

    def _on_message(self, user_id: str, frame: dict[str, Any]) -> None:
        message = frame.get("message") or {}
        thread_id = str(frame.get("thread_id") or "")
        message_id = str(message.get("id") or "")
        if (not message_id or message.get("role") != _BOT_ROLE or message.get("seq") != _PLACEHOLDER_SEQ
                or message.get("kind") != _TEXT_KIND or not self._calls.active(thread_id)):
            return
        session = self._calls.get(thread_id)
        bot_id = str(message.get("author_bot_id") or (session.bot_id if session is not None else ""))
        self._sweep()
        self._put(ReplyTrack(message_id=message_id, thread_id=thread_id, bot_id=bot_id, user_id=user_id,
                             opened_at=self._clock()))

    def _on_delta(self, frame: dict[str, Any]) -> None:
        track = self._tracks.get(str(frame.get("message_id")))
        if track is None or track.done:
            return
        self._put(replace(track, text=track.text + str(frame.get("delta") or "")))
        self._wake(track.message_id)

    def _on_done(self, frame: dict[str, Any]) -> None:
        track = self._tracks.get(str(frame.get("message_id")))
        if track is None or track.done:
            return
        self._put(replace(track, streamed=True))
        self._wake(track.message_id)

    # --- the tracks ---------------------------------------------------------------------------------------------

    def track(self, message_id: str) -> ReplyTrack | None:
        return self._tracks.get(message_id)

    def interrupt(self, thread_id: str, message_id: str) -> None:
        """The user cut the bot off: nothing more of that reply is spoken."""
        track = self._tracks.get(message_id)
        if track is not None and track.thread_id == thread_id:
            self._put(replace(track, interrupted=True, done=True))

    def end_call(self, thread_id: str) -> None:
        """The call ended: its replies' tracks go, and their workers stop at the next part."""
        for track in tuple(self._tracks.values()):
            if track.thread_id == thread_id:
                self._put(replace(track, interrupted=True, done=True))
        self._tracks = MappingProxyType({mid: t for mid, t in self._tracks.items() if t.thread_id != thread_id})

    def _put(self, track: ReplyTrack) -> None:
        self._tracks = MappingProxyType({**self._tracks, track.message_id: track})

    def _sweep(self) -> None:
        cutoff = self._clock() - VOICE_TRACK_KEEP_S
        self._tracks = MappingProxyType({mid: t for mid, t in self._tracks.items() if t.opened_at > cutoff})

    # --- the worker ---------------------------------------------------------------------------------------------

    def _wake(self, message_id: str) -> None:
        running = self._workers.get(message_id)
        if running is not None and not running.done():
            return
        task = self._tasks.spawn(self._work(message_id), name=f"speak-ahead {message_id}")
        self._workers = MappingProxyType({**self._workers, message_id: task})

    def _forget_worker(self, message_id: str) -> None:
        self._workers = MappingProxyType({mid: t for mid, t in self._workers.items() if mid != message_id})

    async def _work(self, message_id: str) -> None:
        try:
            while True:
                track = self._tracks.get(message_id)
                if track is None or track.done:
                    return
                if track.voice is None:
                    track = await self._with_voice(track)
                    if track is None:
                        return
                parts = call_parts(track.text, track.streamed)
                if len(parts) > track.parts_ready:
                    if not await self._speak_part(track, parts[track.parts_ready]):
                        return
                    continue
                if track.streamed:
                    await self._finish(track)
                    return
                self._forget_worker(message_id)   # nothing new, and no await since the read: a later frame wakes us
                return
        finally:
            if self._workers.get(message_id) is asyncio.current_task():
                self._forget_worker(message_id)

    async def _with_voice(self, track: ReplyTrack) -> ReplyTrack | None:
        bot = await self._bots.get(track.user_id, track.bot_id)
        current = self._tracks.get(track.message_id)
        if bot is None or current is None:
            return None
        self._put(replace(current, voice=bot.voice))
        return self._tracks.get(track.message_id)

    async def _speak_part(self, track: ReplyTrack, words: str) -> bool:
        """Speak one part into the cache and say it is ready; False when the voice failed (the track ends)."""
        voice = track.voice
        assert voice is not None
        try:
            async with self._lock_for(track.user_id):
                audio = await self._voice.speak(words, voice.speaker, voice.tone)
        except (VoiceUnavailable, VoiceFailed, WavError) as exc:
            logger.warning("speak-ahead stopped for a reply: %s", type(exc).__name__)
            await self._finish(track)
            return False
        current = self._tracks.get(track.message_id)
        if current is None or current.done:
            return False   # interrupted, or the call ended, while this part was being made
        self._cache.put((track.message_id, track.parts_ready, voice.speaker, voice.tone), audio)
        self._put(replace(current, parts_ready=track.parts_ready + 1,
                          part_voices=(*current.part_voices, (voice.speaker, voice.tone))))
        await self._publish(track, track.parts_ready, done=False)
        return True

    async def _finish(self, track: ReplyTrack) -> None:
        current = self._tracks.get(track.message_id)
        if current is None:
            return
        self._put(replace(current, done=True))
        await self._publish(current, current.parts_ready - 1 if current.parts_ready else _NO_PART, done=True)

    async def _publish(self, track: ReplyTrack, part: int, *, done: bool) -> None:
        await self._events.publish(track.user_id, {
            "type": VOICE_LIVE_TYPE, "thread_id": track.thread_id, "message_id": track.message_id,
            "part": part, "done": done,
        })

    # --- lifecycle ----------------------------------------------------------------------------------------------

    async def wait_idle(self) -> None:
        await self._tasks.wait_idle()

    async def close(self) -> None:
        await self._tasks.close()
