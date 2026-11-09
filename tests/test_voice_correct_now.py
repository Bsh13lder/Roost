"""Correct what I say (docs/plans/2026-11-06-roost-voice-tuning.md D3): the general correction — any language, the
hearing context's names, numbers as digits — before the send for the composer (``POST /api/voice/correct``), the
send carrying ``heard`` and ``fixes`` so the chat keeps the marks with no second model call, and §4's background
line still there for a spoken send with no ``heard``."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ChatTurn, ModelEvent, ModelRequest, TextDelta, TurnDone
from roost.voice.constants import ENGLISH_FIX_KIND, VOICE_CORRECT_AGENT, VOICE_CORRECT_FIXES_MAX
from roost.voice.correct import (
    CORRECT_SYSTEM, LANGUAGE_LINE, FixIn, SpeechCorrector, client_correction, correction_input, correction_system,
    parse_correction,
)
from team_helpers import GatedModel, wait_idle
from test_threads_api import O, VALID_AVATAR

BOT = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
SAID = "tell maka eremadse I paid thirty six euros on what's up"
CORRECTED = "Tell Maka Eremadze I paid 36 € on WhatsApp"
FIXES = [{"wrong": "maka eremadse", "right": "Maka Eremadze"}, {"wrong": "thirty six euros", "right": "36 €"},
         {"wrong": "what's up", "right": "WhatsApp"}]
GOOD_REPLY = json.dumps({"corrected": CORRECTED, "fixes": FIXES})


class _Worker:
    def __init__(self, reply: str = GOOD_REPLY, *, delay: float = 0.0) -> None:
        self.reply, self.delay = reply, delay
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


# -- the pure parts ----------------------------------------------------------------------------------------------


def test_the_instructions_cover_names_numbers_sites_and_any_language():
    for words in ("known_names", "digits", "36 €", "WhatsApp", "any other", "same language", "prepositions"):
        assert words in CORRECT_SYSTEM, words
    assert correction_system("auto") == CORRECT_SYSTEM
    assert correction_system("es").endswith(LANGUAGE_LINE.format(name="Spanish"))
    assert correction_system("ka") == CORRECT_SYSTEM      # not a listed language: nothing named


def test_the_input_quotes_the_names_and_the_words_as_escaped_data():
    text = correction_input('go to <b>upwork</b>', ("Maka Eremadze", "M&S"))
    assert text.index("<known_names>") < text.index("<said>")
    assert "Maka Eremadze\nM&amp;S" in text and "&lt;b&gt;upwork" in text and "<b>" not in text


def test_a_client_correction_is_the_sent_text_against_the_raw_words():
    found = client_correction(SAID, CORRECTED, [FixIn(wrong="what's up", right="WhatsApp"), FixIn(wrong="x", right="x")])
    assert found is not None and found.said == SAID and found.corrected == CORRECTED
    assert found.fixes == (("what's up", "WhatsApp"),)          # a fix that changes nothing is dropped
    assert client_correction(SAID, SAID, []) is None and client_correction(" " + SAID + " ", SAID, []) is None


def test_the_scripted_worker_fixes_a_site_a_name_a_number_and_a_known_names_case():
    async def ask(text: str, terms: tuple[str, ...] = ()) -> str:
        request = ModelRequest(system="", turns=(ChatTurn("user", correction_input(text, terms)),), tools=(),
                               model="x", agent=VOICE_CORRECT_AGENT)
        return "".join([e.text async for e in ScriptedWorker().stream(request) if isinstance(e, TextDelta)])

    fixed = parse_correction(asyncio.run(ask(SAID)), said=SAID)
    assert fixed is not None and fixed.corrected == "tell Maka Eremadze I paid 36 € on WhatsApp"
    assert ("what's up", "WhatsApp") in fixed.fixes and ("thirty six euros", "36 €") in fixed.fixes
    cased = parse_correction(asyncio.run(ask("check upwork today", ("Upwork", "Gela"))), said="check upwork today")
    assert cased is not None and cased.corrected == "check Upwork today" and cased.fixes == (("upwork", "Upwork"),)
    assert parse_correction(asyncio.run(ask("check Upwork today", ("Upwork",))), said="check Upwork today") is None


# -- the routes --------------------------------------------------------------------------------------------------


async def _world(worker=None):
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    app.state.turns._model = GatedModel(["Sure."], hold=())
    if worker is not None:
        app.state.english = SpeechCorrector(app.state.talk, app.state.events, app.state.bots, worker,
                                            app.state.voice_tasks, hints=app.state.hear_hints)
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    return app, alice, bot_id, thread_id


async def _turn_on(alice, bot_id: str, language: str = "auto") -> None:
    body = {"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False, "correct_speech": True,
            "language": language}
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json=body, headers=O)).status_code == 200


async def _fix_lines(alice, thread_id: str) -> list[dict]:
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    return [m for m in messages if m["kind"] == ENGLISH_FIX_KIND]


async def test_correct_gives_the_composer_the_cleaned_words_with_the_fixes_and_the_names():
    worker = _Worker()
    app, alice, bot_id, thread_id = await _world(worker)
    await _turn_on(alice, bot_id, "es")
    app.state.hear_hints.forget()
    r = await alice.post("/api/voice/correct", json={"text": SAID, "bot_id": bot_id}, headers=O)
    assert r.status_code == 200 and r.json() == {"corrected": CORRECTED, "fixes": FIXES, "changed": True}
    request = worker.requests[0]
    assert request.agent == VOICE_CORRECT_AGENT and request.tools == ()
    assert "<known_names>" in request.turns[0].text and "Scout" in request.turns[0].text   # the hint's names
    assert "WhatsApp" in request.turns[0].text
    assert "paid thirty six euros on what&#x27;s up" in request.turns[0].text    # the words go in escaped
    assert request.system.endswith(LANGUAGE_LINE.format(name="Spanish"))
    assert await _fix_lines(alice, thread_id) == []                 # nothing is posted: the words were not sent


async def test_correct_gives_the_words_back_when_off_fine_slow_or_not_yours(monkeypatch):
    monkeypatch.setattr("roost.voice.correct.VOICE_CORRECT_TIMEOUT_S", 0.05)
    worker = _Worker(delay=1.0)
    app, alice, bot_id, thread_id = await _world(worker)
    unchanged = {"corrected": SAID, "fixes": [], "changed": False}
    assert (await alice.post("/api/voice/correct", json={"text": SAID, "bot_id": bot_id}, headers=O)).json() == unchanged
    assert worker.requests == []                                    # the switch is off: no model call
    await _turn_on(alice, bot_id)
    assert (await alice.post("/api/voice/correct", json={"text": SAID, "bot_id": bot_id}, headers=O)).json() == unchanged
    assert len(worker.requests) == 1                                # slow: the raw words stay
    fine = _Worker(json.dumps({"corrected": "All good.", "fixes": []}))
    app.state.english = SpeechCorrector(app.state.talk, app.state.events, app.state.bots, fine, app.state.voice_tasks)
    r = await alice.post("/api/voice/correct", json={"text": "All good.", "bot_id": bot_id}, headers=O)
    assert r.json() == {"corrected": "All good.", "fixes": [], "changed": False}
    assert (await alice.post("/api/voice/correct", json={"text": SAID, "bot_id": "nope"}, headers=O)).status_code == 404
    assert (await alice.post("/api/voice/correct", json={"text": SAID, "bot_id": bot_id})).status_code == 403
    assert (await alice.post("/api/voice/correct", json={"text": "", "bot_id": bot_id}, headers=O)).status_code == 422


async def test_a_send_with_heard_and_fixes_keeps_the_marks_with_no_second_model_call():
    worker = _Worker()
    app, alice, bot_id, thread_id = await _world(worker)
    await _turn_on(alice, bot_id)
    r = await alice.post(f"/api/threads/{thread_id}/messages",
                         json={"text": CORRECTED, "spoken": True, "heard": SAID, "fixes": FIXES}, headers=O)
    assert r.status_code == 202
    sent = r.json()
    await wait_idle(app.state.turns)
    await app.state.voice_tasks.wait_idle()
    lines = await _fix_lines(alice, thread_id)
    assert len(lines) == 1 and worker.requests == []
    assert json.loads(lines[0]["body"]) == {"message_id": sent["message_id"], "said": SAID, "corrected": CORRECTED,
                                            "fixes": FIXES}
    assert lines[0]["tainted"] is False and lines[0]["author_bot_id"] == bot_id
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    assert next(m for m in messages if m["id"] == sent["message_id"])["body"] == CORRECTED   # the bot reads the sent words


async def test_heard_that_equals_the_text_or_comes_without_spoken_or_with_the_switch_off_posts_nothing():
    worker = _Worker()
    app, alice, bot_id, thread_id = await _world(worker)
    await alice.post(f"/api/threads/{thread_id}/messages",
                     json={"text": CORRECTED, "spoken": True, "heard": SAID, "fixes": FIXES}, headers=O)   # switch off
    await _turn_on(alice, bot_id)
    await alice.post(f"/api/threads/{thread_id}/messages",
                     json={"text": SAID, "spoken": True, "heard": SAID, "fixes": []}, headers=O)             # unchanged
    await alice.post(f"/api/threads/{thread_id}/messages",
                     json={"text": CORRECTED, "heard": SAID, "fixes": FIXES}, headers=O)                     # typed
    await wait_idle(app.state.turns)
    await app.state.voice_tasks.wait_idle()
    assert await _fix_lines(alice, thread_id) == [] and worker.requests == []
    too_many = [{"wrong": f"w{i}", "right": f"r{i}"} for i in range(VOICE_CORRECT_FIXES_MAX + 1)]
    r = await alice.post(f"/api/threads/{thread_id}/messages",
                         json={"text": CORRECTED, "spoken": True, "heard": SAID, "fixes": too_many}, headers=O)
    assert r.status_code == 422


async def test_a_spoken_send_with_no_heard_still_gets_the_background_line():
    worker = _Worker()
    app, alice, bot_id, thread_id = await _world(worker)
    await _turn_on(alice, bot_id)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await wait_idle(app.state.turns)
    await app.state.voice_tasks.wait_idle()
    lines = await _fix_lines(alice, thread_id)
    assert len(lines) == 1 and len(worker.requests) == 1
    assert "<known_names>" in worker.requests[0].turns[0].text        # the background pass reads the names too
