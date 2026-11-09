"""Speak-ahead (docs/plans/2026-10-30-roost-voice.md §3, contract B): while a thread is in a call, the reply's
streamed text is spoken sentence by sentence as it arrives, into the speech cache under the usual key, with a
``speech_ready`` frame per part; nothing is spoken for a thread with no call; an interrupt stops the rest."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from roost.voice.calls import CallRegistry
from roost.voice.client import FakeVoice
from roost.voice.constants import VOICE_LIVE_TYPE, VOICE_TRACK_KEEP_S, VoiceSettings
from roost.voice.speak_ahead import SpeakAhead
from roost.voice.spoken import SpeechCache

VOICE = VoiceSettings(speaker="serena", tone="calm", speed=1.25, read_aloud=False)


class FakeEvents:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, user_id: str, event: dict) -> int:
        self.published.append((user_id, event))
        return 0


class FakeBots:
    def __init__(self, known: frozenset[str] = frozenset({"b1"})) -> None:
        self.known = known

    async def get(self, user_id: str, bot_id: str):
        return SimpleNamespace(id=bot_id, voice=VOICE) if bot_id in self.known else None


def _world(now: list[float] | None = None):
    now = now if now is not None else [0.0]
    calls = CallRegistry(clock=lambda: now[0])
    events, voice, cache = FakeEvents(), FakeVoice(), SpeechCache()
    locks: dict[str, asyncio.Lock] = {}
    ahead = SpeakAhead(events, FakeBots(), voice, cache, calls, speak_lock_for=lambda uid: locks.setdefault(uid, asyncio.Lock()),
                       clock=lambda: now[0])
    return ahead, calls, events, voice, cache


def _placeholder(message_id: str, thread_id: str) -> dict:
    return {"type": "message", "thread_id": thread_id, "seq": 0,
            "message": {"id": message_id, "thread_id": thread_id, "role": "bot", "body": "", "seq": 0, "kind": "text",
                        "author_bot_id": "b1"}}


def _delta(message_id: str, thread_id: str, text: str) -> dict:
    return {"type": "text_delta", "thread_id": thread_id, "message_id": message_id, "delta": text, "seq": 0}


def _done(message_id: str, thread_id: str) -> dict:
    return {"type": "message_done", "thread_id": thread_id, "message_id": message_id, "seq": 1}


def _ready(events: FakeEvents) -> list[tuple[int, bool]]:
    return [(e["part"], e["done"]) for _, e in events.published if e["type"] == VOICE_LIVE_TYPE]


async def test_parts_are_spoken_as_the_sentences_close_and_the_tail_at_the_end():
    ahead, calls, events, voice, cache = _world()
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _delta("m1", "t1", "I found three "))
    ahead.listen("u1", _delta("m1", "t1", "flights. The cheapest "))
    await ahead.wait_idle()
    assert [s[0] for s in voice.engine.spoken] == ["I found three flights."]
    assert _ready(events) == [(0, False)]
    ahead.listen("u1", _delta("m1", "t1", "is at 7:30! Book it?"))
    await ahead.wait_idle()
    assert [s[0] for s in voice.engine.spoken] == ["I found three flights.", "The cheapest is at 7:30!"]
    ahead.listen("u1", _done("m1", "t1"))
    await ahead.wait_idle()
    assert voice.engine.spoken == [("I found three flights.", "serena", "calm"), ("The cheapest is at 7:30!", "serena", "calm"),
                                   ("Book it?", "serena", "calm")]
    assert _ready(events) == [(0, False), (1, False), (2, False), (2, True)]
    assert all(e["thread_id"] == "t1" and e["message_id"] == "m1" for _, e in events.published)
    assert all(cache.get(("m1", i, "serena", "calm")) is not None for i in range(3))
    track = ahead.track("m1")
    assert (track.parts_ready, track.done, track.voice) == (3, True, VOICE)


async def test_nothing_is_spoken_for_a_thread_with_no_call_or_a_user_message():
    ahead, calls, events, voice, cache = _world()
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _delta("m1", "t1", "Hello there. "))
    ahead.listen("u1", _done("m1", "t1"))
    calls.beat("u1", "t2", "b1")
    mine = _placeholder("m2", "t2")
    mine["message"]["role"] = "user"
    ahead.listen("u1", mine)
    ahead.listen("u1", _delta("m2", "t2", "Hi bot. "))
    await ahead.wait_idle()
    assert voice.engine.spoken == [] and events.published == [] and ahead.track("m1") is None


async def test_an_interrupt_stops_the_rest_of_the_reply():
    ahead, calls, events, voice, cache = _world()
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _delta("m1", "t1", "First one. "))
    await ahead.wait_idle()
    ahead.interrupt("t1", "m1")
    ahead.listen("u1", _delta("m1", "t1", "Second one. Third one. "))
    ahead.listen("u1", _done("m1", "t1"))
    await ahead.wait_idle()
    assert [s[0] for s in voice.engine.spoken] == ["First one."]
    assert ahead.track("m1").done and ahead.track("m1").interrupted
    ahead.interrupt("t1", "m-unknown")   # nothing happens


async def test_a_done_reply_with_no_words_ends_with_a_done_frame_alone():
    ahead, calls, events, voice, cache = _world()
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _done("m1", "t1"))
    await ahead.wait_idle()
    assert voice.engine.spoken == [] and _ready(events) == [(-1, True)]


async def test_tracks_are_dropped_when_the_call_ends_or_after_a_while():
    now = [0.0]
    ahead, calls, events, voice, cache = _world(now)
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _done("m1", "t1"))
    await ahead.wait_idle()
    ahead.end_call("t1")
    assert ahead.track("m1") is None
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m2", "t1"))
    now[0] = VOICE_TRACK_KEEP_S + 1
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m3", "t1"))
    assert ahead.track("m2") is None and ahead.track("m3") is not None


async def test_a_voice_failure_ends_the_track_instead_of_raising():
    ahead, calls, events, voice, cache = _world()
    voice.on = False
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", _placeholder("m1", "t1"))
    ahead.listen("u1", _delta("m1", "t1", "Hello there. "))
    await ahead.wait_idle()
    assert ahead.track("m1").done and ahead.track("m1").parts_ready == 0
    assert _ready(events) == [(-1, True)]
