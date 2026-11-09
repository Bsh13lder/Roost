"""Voice routes (docs/plans/2026-10-30-roost-voice.md) on the fake voice: settings, a recording heard, a reply spoken
in its bot's voice, and nothing of another user's or a non-reply."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.voice.client import FakeVoice
from roost.voice.constants import (
    TONES, VOICE_OFF_TEXT, VOICE_PARTIAL_MAX_S, VOICE_PARTIAL_WAV_BYTES_MAX, VOICE_SAMPLE_TEXT,
)
from roost.voice.wav import encode_wav, read_wav
from team_helpers import GatedModel, wait_idle
from test_threads_api import O, VALID_AVATAR, _async_client_as

BOT = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
REPLY = "Done! I added **milk** to [your list](https://x.example/l). Anything else?"
VOICE = {"speaker": "serena", "tone": "cheerful", "speed": 1.25, "read_aloud": True, "correct_english": False}
# What the server sends back for VOICE: the switch under both names and the language (voice tuning D2, D3).
STORED = {**VOICE, "correct_speech": False, "language": "auto"}


async def _rig():
    await init_db(load_config())
    app = create_app()
    app.state.turns._model = GatedModel([REPLY], hold=())
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    sent = (await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)).json()
    await wait_idle(app.state.turns)
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    reply = next(m for m in messages if m["role"] == "bot" and m["kind"] == "text")
    return app, alice, bot_id, thread_id, sent["message_id"], reply["id"]


def _speech(thread_id: str, message_id: str, part: int | None = None) -> str:
    base = f"/api/threads/{thread_id}/messages/{message_id}/speech"
    return base if part is None else f"{base}/{part}"


async def test_voice_info_lists_the_choices():
    app, alice, *_ = await _rig()
    info = (await alice.get("/api/voice")).json()
    assert info["available"] is True
    assert {s["id"] for s in info["speakers"]} >= {"aiden", "ryan", "serena"}
    assert [t["id"] for t in info["tones"]] == list(TONES)
    assert 1.0 in info["speeds"]
    # Voice tuning D2: Auto-detect first, then the hearing model's languages; never Georgian.
    assert info["languages"][0] == {"id": "auto", "name": "Auto-detect"}
    assert {"id": "es", "name": "Spanish"} in info["languages"] and len(info["languages"]) == 31
    assert "ka" not in {lang["id"] for lang in info["languages"]}
    app.state.voice = FakeVoice(on=False)
    assert (await alice.get("/api/voice")).json()["available"] is False


async def test_a_bot_starts_with_the_default_voice_and_saves_a_new_one():
    app, alice, bot_id, *_ = await _rig()
    bot = (await alice.get(f"/api/bots/{bot_id}")).json()
    assert bot["voice"] == {"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False,
                            "correct_speech": False, "correct_english": False, "language": "auto"}
    r = await alice.put(f"/api/bots/{bot_id}/voice", json=VOICE, headers=O)
    assert r.status_code == 200 and r.json()["voice"] == STORED
    assert (await alice.get(f"/api/bots/{bot_id}")).json()["voice"] == STORED


async def test_the_language_is_saved_from_the_list_and_kept_when_absent():
    app, alice, bot_id, *_ = await _rig()
    saved = (await alice.put(f"/api/bots/{bot_id}/voice", json={**VOICE, "language": "es"}, headers=O)).json()
    assert saved["voice"]["language"] == "es"
    kept = (await alice.put(f"/api/bots/{bot_id}/voice", json=VOICE, headers=O)).json()   # no language given
    assert kept["voice"]["language"] == "es"
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json={**VOICE, "language": "ka"},
                            headers=O)).status_code == 422
    back = (await alice.put(f"/api/bots/{bot_id}/voice", json={**VOICE, "language": "auto"}, headers=O)).json()
    assert back["voice"]["language"] == "auto"


async def test_the_switch_is_taken_under_either_name_and_sent_under_both():
    app, alice, bot_id, *_ = await _rig()
    base = {k: v for k, v in VOICE.items() if k != "correct_english"}
    new = (await alice.put(f"/api/bots/{bot_id}/voice", json={**base, "correct_speech": True}, headers=O)).json()
    assert new["voice"]["correct_speech"] is True and new["voice"]["correct_english"] is True
    old = (await alice.put(f"/api/bots/{bot_id}/voice", json={**base, "correct_english": False}, headers=O)).json()
    assert old["voice"]["correct_speech"] is False and old["voice"]["correct_english"] is False


async def test_correct_my_english_is_optional_on_the_save_and_kept_when_absent():
    app, alice, bot_id, *_ = await _rig()
    on = {**VOICE, "correct_english": True}
    stored_on = {**STORED, "correct_english": True, "correct_speech": True}
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json=on, headers=O)).json()["voice"] == stored_on
    without = {k: v for k, v in VOICE.items() if k != "correct_english"}
    saved = (await alice.put(f"/api/bots/{bot_id}/voice", json={**without, "speed": 2.0}, headers=O)).json()["voice"]
    assert saved == {**stored_on, "speed": 2.0}               # the stored switch stays on
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json={**without, "correct_english": "yes"},
                            headers=O)).status_code == 422
    off = (await alice.put(f"/api/bots/{bot_id}/voice", json={**without, "correct_english": False}, headers=O)).json()
    assert off["voice"]["correct_english"] is False


@pytest.mark.parametrize("bad", [{"speaker": "nobody"}, {"tone": "angry"}, {"speed": 3.0}, {"read_aloud": "yes"},
                                 {"extra": 1}])
async def test_voice_settings_off_the_lists_are_refused(bad):
    app, alice, bot_id, *_ = await _rig()
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json={**VOICE, **bad}, headers=O)).status_code == 422


async def test_voice_settings_need_the_origin_and_the_owner():
    app, alice, bot_id, *_ = await _rig()
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json=VOICE)).status_code == 403
    bob = await _async_client_as(app, "bob")
    assert (await bob.put(f"/api/bots/{bot_id}/voice", json=VOICE, headers=O)).status_code == 404


async def test_a_recording_becomes_text_and_nothing_is_sent():
    app, alice, bot_id, thread_id, *_ = await _rig()
    before = len((await alice.get(f"/api/threads/{thread_id}/messages")).json())
    wav = encode_wav(b"\x00\x00" * 16000, 16000)
    r = await alice.post("/api/voice/transcribe", content=wav, headers={**O, "Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json() == {"text": "Add milk to my list"}
    assert len((await alice.get(f"/api/threads/{thread_id}/messages")).json()) == before


async def test_a_recording_for_a_bot_is_heard_with_that_bots_hint():
    """Voice tuning D1/D2: the bots' names, the owner's own words and the bot's language reach the hearing model."""
    app, alice, bot_id, thread_id, *_ = await _rig()
    await alice.put(f"/api/bots/{bot_id}/voice", json={**VOICE, "language": "es"}, headers=O)
    app.state.hear_hints.forget()
    wav = encode_wav(b"\x00\x00" * 16000, 16000)
    r = await alice.post(f"/api/voice/transcribe?bot_id={bot_id}", content=wav, headers={**O, "Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json() == {"text": "Add milk to my list"}
    hint = app.state.voice.engine.hints[-1]
    assert {"Chief", "Scout"} <= set(hint.terms[:2])        # the bots first (the main bot exists from the start)
    assert "WhatsApp" in hint.terms and hint.language == "Spanish" and not hint.partial
    assert "hi" not in hint.terms                           # the owner's plain words are not names
    # no bot named: the fixed names and auto-detect; another user's bot: 404
    await alice.post("/api/voice/transcribe", content=wav, headers={**O, "Content-Type": "audio/wav"})
    assert app.state.voice.engine.hints[-1].language is None
    bob = await _async_client_as(app, "bob")
    assert (await bob.post(f"/api/voice/transcribe?bot_id={bot_id}", content=wav, headers=O)).status_code == 404


async def test_a_partial_is_the_live_words_of_a_recording_still_going():
    """Voice tuning D4: the same hint, marked partial; a buffer past the cap is refused; the guard is shared."""
    app, alice, bot_id, *_ = await _rig()
    wav = encode_wav(b"\x00\x00" * 16000 * 3, 16000)
    r = await alice.post(f"/api/voice/partial?bot_id={bot_id}", content=wav, headers={**O, "Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json() == {"text": "Add milk to my list"}
    hint = app.state.voice.engine.hints[-1]
    assert hint.partial is True and "Scout" in hint.terms[:2]
    too_long = encode_wav(b"\x00\x00" * 16000 * (VOICE_PARTIAL_MAX_S + 1), 16000)
    assert (await alice.post("/api/voice/partial", content=too_long, headers=O)).status_code == 422
    huge = {**O, "Content-Length": str(VOICE_PARTIAL_WAV_BYTES_MAX + 1)}
    assert (await alice.post("/api/voice/partial", content=b"", headers=huge)).status_code == 413
    assert (await alice.post("/api/voice/partial", content=wav)).status_code == 403


async def test_the_final_recording_waits_for_a_live_partial_instead_of_being_refused():
    """Stop while a live partial is still being heard: the final recording waits for it and comes back with its
    words (it used to get 429 "Still working on your last recording." and the words were lost). A partial that
    comes while anything is being heard is refused at once: the client just skips that tick."""
    app, alice, bot_id, *_ = await _rig()
    wav = encode_wav(b"\x00\x00" * 16000 * 3, 16000)
    heard = app.state.voice.transcribe
    gate = asyncio.Event()
    started = asyncio.Event()

    async def slow_partial_then_final(body, hint):
        if hint.partial:
            started.set()
            await gate.wait()
        return await heard(body, hint)

    app.state.voice.transcribe = slow_partial_then_final
    partial = asyncio.create_task(
        alice.post(f"/api/voice/partial?bot_id={bot_id}", content=wav, headers={**O, "Content-Type": "audio/wav"}))
    await started.wait()
    second = await alice.post(f"/api/voice/partial?bot_id={bot_id}", content=wav, headers=O)
    assert second.status_code == 429
    final = asyncio.create_task(alice.post(f"/api/voice/transcribe?bot_id={bot_id}", content=wav, headers=O))
    await asyncio.sleep(0.05)
    assert not final.done(), "the final waits for the partial in flight"
    gate.set()
    assert (await partial).status_code == 200
    done = await final
    assert done.status_code == 200 and done.json() == {"text": "Add milk to my list"}


async def test_a_bad_or_huge_recording_is_refused():
    app, alice, *_ = await _rig()
    assert (await alice.post("/api/voice/transcribe", content=b"OggS", headers=O)).status_code == 422
    huge = {**O, "Content-Length": str(50_000_000)}
    assert (await alice.post("/api/voice/transcribe", content=b"", headers=huge)).status_code == 413
    assert (await alice.post("/api/voice/transcribe", content=b"x")).status_code == 403


async def test_voice_off_says_so():
    app, alice, *_ = await _rig()
    app.state.voice = FakeVoice(on=False)
    r = await alice.post("/api/voice/transcribe", content=encode_wav(b"\x00\x00" * 160, 16000), headers=O)
    assert r.status_code == 503 and r.json()["detail"] == VOICE_OFF_TEXT


async def test_a_reply_is_spoken_in_its_bots_voice_and_cached():
    app, alice, bot_id, thread_id, _, reply_id = await _rig()
    await alice.put(f"/api/bots/{bot_id}/voice", json=VOICE, headers=O)
    plan = (await alice.get(_speech(thread_id, reply_id))).json()
    assert plan == {"parts": 1, "speed": 1.25}
    r = await alice.get(_speech(thread_id, reply_id, 0))
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert read_wav(r.content).seconds > 0
    spoken = app.state.voice.engine.spoken
    assert spoken == [("Done! I added milk to your list. Anything else?", "serena", "cheerful")]
    await alice.get(_speech(thread_id, reply_id, 0))
    assert len(spoken) == 1
    assert (await alice.get(_speech(thread_id, reply_id, 1))).status_code == 404


async def test_only_a_bots_reply_in_your_own_thread_is_spoken():
    app, alice, bot_id, thread_id, mine_id, reply_id = await _rig()
    assert (await alice.get(_speech(thread_id, mine_id))).status_code == 404
    assert (await alice.get(_speech("other-thread", reply_id))).status_code == 404
    bob = await _async_client_as(app, "bob")
    assert (await bob.get(_speech(thread_id, reply_id))).status_code == 404
    assert (await bob.get(_speech(thread_id, reply_id, 0))).status_code == 404


async def test_try_it_speaks_the_sample_line():
    app, alice, bot_id, *_ = await _rig()
    r = await alice.get(f"/api/bots/{bot_id}/voice/sample", params={"speaker": "ryan", "tone": "calm"})
    assert r.status_code == 200
    assert app.state.voice.engine.spoken == [(VOICE_SAMPLE_TEXT, "ryan", "calm")]
    bad = await alice.get(f"/api/bots/{bot_id}/voice/sample", params={"speaker": "x", "tone": "calm"})
    assert bad.status_code == 422


async def test_warm_up_before_a_call():
    app, alice, *_ = await _rig()
    r = await alice.post("/api/voice/warm", headers=O)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert app.state.voice.engine.warmed == 1
    assert (await alice.post("/api/voice/warm")).status_code == 403
    app.state.voice = FakeVoice(on=False)
    r = await alice.post("/api/voice/warm", headers=O)
    assert r.status_code == 503 and r.json()["detail"] == VOICE_OFF_TEXT


# --- Call mode (§3) -----------------------------------------------------------------------------------------------

from roost.voice.constants import VOICE_CALL_EXPIRES_S, VOICE_LINES   # noqa: E402

REPLY_2 = "On it: checking the trains.\n\nThe next train leaves at 9:40. Shall I book a seat?"


async def _call_rig():
    app, alice, bot_id, thread_id, mine_id, reply_id = await _rig()
    app.state.turns._model = GatedModel([REPLY_2, REPLY_2], hold=())   # a fresh model: its first call is a call turn
    return app, alice, bot_id, thread_id, mine_id, reply_id


async def _call_reply(app, alice, thread_id: str) -> str:
    """A call turn: the message sent with ``call: true``; the reply's id once the run and the speak-ahead are done."""
    r = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "trains to Toledo?", "call": True},
                         headers=O)
    assert r.status_code == 202 and set(r.json()) == {"message_id", "status", "queued", "mentioned"}
    await wait_idle(app.state.turns)
    await app.state.speak_ahead.wait_idle()
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    return [m for m in messages if m["role"] == "bot" and m["kind"] == "text"][-1]["id"]


async def test_a_call_starts_beats_and_ends():
    app, alice, bot_id, thread_id, *_ = await _call_rig()
    r = await alice.post(f"/api/threads/{thread_id}/call", json={}, headers=O)
    assert r.status_code == 200 and r.json() == {"ok": True, "expires_in": int(VOICE_CALL_EXPIRES_S)}
    assert app.state.calls.active(thread_id)
    assert (await alice.post(f"/api/threads/{thread_id}/call", content=b"", headers=O)).status_code == 200
    r = await alice.post(f"/api/threads/{thread_id}/call", json={"interrupted": "m-9"}, headers=O)
    assert r.status_code == 200 and app.state.calls.get(thread_id).interrupted == "m-9"
    assert (await alice.post(f"/api/threads/{thread_id}/call", json={"interrupted": 5}, headers=O)).status_code == 422
    assert (await alice.post(f"/api/threads/{thread_id}/call", json={})).status_code == 403
    r = await alice.delete(f"/api/threads/{thread_id}/call", headers=O)
    assert r.status_code == 200 and r.json() == {"ok": True} and not app.state.calls.active(thread_id)
    assert (await alice.delete(f"/api/threads/{thread_id}/call", headers=O)).status_code == 200


async def test_a_call_is_only_yours_and_never_a_room():
    app, alice, bot_id, thread_id, *_ = await _call_rig()
    bob = await _async_client_as(app, "bob")
    assert (await bob.post(f"/api/threads/{thread_id}/call", json={}, headers=O)).status_code == 404
    assert (await alice.post("/api/threads/nope/call", json={}, headers=O)).status_code == 404
    other = (await alice.post("/api/bots", json={**BOT, "name": "Quill"}, headers=O)).json()["id"]
    room = (await alice.post("/api/rooms", json={"name": "Desk", "member_ids": [bot_id, other]}, headers=O)).json()
    assert (await alice.post(f"/api/threads/{room['thread_id']}/call", json={}, headers=O)).status_code == 409


async def test_a_call_keeps_the_models_warm_at_most_once_in_a_while():
    app, alice, bot_id, thread_id, *_ = await _call_rig()
    await alice.post(f"/api/threads/{thread_id}/call", json={}, headers=O)
    await alice.post(f"/api/threads/{thread_id}/call", json={}, headers=O)
    await app.state.voice_tasks.wait_idle()
    assert app.state.voice.engine.warmed == 1


async def test_a_call_turn_is_spoken_ahead_and_served_live():
    app, alice, bot_id, thread_id, *_ = await _call_rig()
    await alice.post(f"/api/threads/{thread_id}/call", json={}, headers=O)
    reply_id = await _call_reply(app, alice, thread_id)
    assert app.state.calls.active(thread_id)
    plan = (await alice.get(f"/api/threads/{thread_id}/live-speech/{reply_id}")).json()
    assert plan == {"parts": 2, "done": True, "speed": 1.0}
    spoken = [s[0] for s in app.state.voice.engine.spoken]
    assert spoken == ["The next train leaves at 9:40.", "Shall I book a seat?"]   # no "On it" lead
    r = await alice.get(f"/api/threads/{thread_id}/live-speech/{reply_id}/0")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and read_wav(r.content).seconds > 0
    assert r.headers["cache-control"] == "no-store"
    assert (await alice.get(f"/api/threads/{thread_id}/live-speech/{reply_id}/2")).status_code == 404
    assert len(app.state.voice.engine.spoken) == 2   # the parts were served from the cache


async def test_a_call_turn_needs_no_call_route_first():
    """``call: true`` on the message alone beats the registry (the client's heartbeat may be a moment late)."""
    app, alice, bot_id, thread_id, *_ = await _call_rig()
    reply_id = await _call_reply(app, alice, thread_id)
    assert app.state.calls.active(thread_id)
    assert (await alice.get(f"/api/threads/{thread_id}/live-speech/{reply_id}")).json()["parts"] == 2


async def test_live_speech_is_only_for_a_reply_made_in_your_own_call():
    app, alice, bot_id, thread_id, mine_id, typed_reply_id = await _call_rig()
    await alice.post(f"/api/threads/{thread_id}/call", json={}, headers=O)
    reply_id = await _call_reply(app, alice, thread_id)
    assert (await alice.get(f"/api/threads/{thread_id}/live-speech/{typed_reply_id}")).status_code == 404
    assert (await alice.get(f"/api/threads/{thread_id}/live-speech/{mine_id}")).status_code == 404
    assert (await alice.get(f"/api/threads/other/live-speech/{reply_id}")).status_code == 404
    assert (await alice.get(f"/api/threads/{thread_id}/live-speech/nope/0")).status_code == 404
    bob = await _async_client_as(app, "bob")
    assert (await bob.get(f"/api/threads/{thread_id}/live-speech/{reply_id}")).status_code == 404
    assert (await bob.get(f"/api/threads/{thread_id}/live-speech/{reply_id}/0")).status_code == 404


async def test_a_fixed_line_is_spoken_in_the_bots_voice_and_cached():
    app, alice, bot_id, *_ = await _call_rig()
    await alice.put(f"/api/bots/{bot_id}/voice", json=VOICE, headers=O)
    r = await alice.get(f"/api/bots/{bot_id}/voice/line/greeting")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert app.state.voice.engine.spoken == [(VOICE_LINES["greeting"], "serena", "cheerful")]
    await alice.get(f"/api/bots/{bot_id}/voice/line/greeting")
    assert len(app.state.voice.engine.spoken) == 1
    assert (await alice.get(f"/api/bots/{bot_id}/voice/line/shout")).status_code == 404
    bob = await _async_client_as(app, "bob")
    assert (await bob.get(f"/api/bots/{bot_id}/voice/line/greeting")).status_code == 404


async def test_warm_with_a_bot_makes_its_six_lines_in_the_background():
    app, alice, bot_id, *_ = await _call_rig()
    r = await alice.post("/api/voice/warm", json={"bot_id": bot_id}, headers=O)
    assert r.status_code == 200 and r.json() == {"ok": True}
    await app.state.voice_tasks.wait_idle()
    assert sorted(s[0] for s in app.state.voice.engine.spoken) == sorted(VOICE_LINES.values())
    await alice.get(f"/api/bots/{bot_id}/voice/line/bye")
    assert len(app.state.voice.engine.spoken) == len(VOICE_LINES)   # already made
    assert (await alice.post("/api/voice/warm", json={}, headers=O)).status_code == 200
    assert (await alice.post("/api/voice/warm", json={"bot_id": "nope"}, headers=O)).status_code == 200
    assert (await alice.post("/api/voice/warm", json={"bot_id": 7}, headers=O)).status_code == 422
