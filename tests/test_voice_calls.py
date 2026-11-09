"""The call registry (docs/plans/2026-10-30-roost-voice.md §3, contract A): an in-memory record of which threads
are in a voice call, kept alive by beats and gone after ``VOICE_CALL_EXPIRES_S`` without one. Pure."""

from __future__ import annotations

import dataclasses

import pytest

from roost.voice.calls import CallRegistry, CallSession
from roost.voice.constants import VOICE_CALL_EXPIRES_S, VOICE_CALL_HEARTBEAT_S


def _registry(now: list[float]) -> CallRegistry:
    return CallRegistry(clock=lambda: now[0])


def test_a_thread_is_in_a_call_only_after_a_beat():
    now = [100.0]
    calls = _registry(now)
    assert not calls.active("t1")
    session = calls.beat("u1", "t1", "b1")
    assert calls.active("t1") and not calls.active("t2")
    assert session == CallSession(thread_id="t1", bot_id="b1", user_id="u1", started_at=100.0, beat_at=100.0,
                                  interrupted=None)


def test_a_beat_keeps_the_start_and_moves_the_clock():
    now = [100.0]
    calls = _registry(now)
    calls.beat("u1", "t1", "b1")
    now[0] = 130.0
    again = calls.beat("u1", "t1", "b1")
    assert (again.started_at, again.beat_at) == (100.0, 130.0)


def test_a_call_expires_without_a_beat_and_a_beat_in_time_keeps_it():
    now = [0.0]
    calls = _registry(now)
    calls.beat("u1", "t1", "b1")
    now[0] = VOICE_CALL_EXPIRES_S - 0.1
    assert calls.active("t1")
    now[0] = VOICE_CALL_EXPIRES_S + 0.1
    assert not calls.active("t1") and calls.get("t1") is None
    assert VOICE_CALL_HEARTBEAT_S < VOICE_CALL_EXPIRES_S   # a client that beats on time never drops


def test_end_is_idempotent_and_interrupt_remembers_the_cut_reply():
    now = [0.0]
    calls = _registry(now)
    calls.end("t1")   # nothing to end: fine
    calls.beat("u1", "t1", "b1")
    calls.interrupt("t1", "m9")
    assert calls.get("t1").interrupted == "m9"
    calls.interrupt("t2", "m9")   # no call there: nothing happens
    calls.end("t1")
    calls.end("t1")
    assert not calls.active("t1")


def test_a_fresh_beat_after_an_end_starts_over_clean():
    now = [0.0]
    calls = _registry(now)
    calls.beat("u1", "t1", "b1")
    calls.interrupt("t1", "m1")
    calls.end("t1")
    now[0] = 5.0
    session = calls.beat("u1", "t1", "b1")
    assert (session.started_at, session.interrupted) == (5.0, None)


def test_sessions_are_frozen():
    session = CallRegistry().beat("u1", "t1", "b1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        session.thread_id = "t2"   # type: ignore[misc]
