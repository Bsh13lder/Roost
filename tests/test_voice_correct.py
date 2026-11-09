"""Correct my English (docs/plans/2026-10-30-roost-voice.md §4): a spoken message (``"spoken": true``) in a chat
whose bot has ``voice.correct_english`` on gets, in the background, one ``english_fix`` activity line from the worker
model — the corrected sentence and each fix — or nothing at all when the sentence is fine, the reply is bad or the
worker is slow. The bot always reads the user's ORIGINAL words. The line is never replayed to the model, never a
chat-list preview, never read aloud and never tainted."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ChatTurn, ModelEvent, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.talk.chats import chat_preview
from roost.talk.store import TalkStore
from roost.talk.turn import _MODEL_KINDS
from roost.voice.constants import (
    ENGLISH_FIX_KIND, VOICE_CORRECT_AGENT, VOICE_CORRECT_FIX_CHARS_MAX, VOICE_CORRECT_FIXES_MAX,
    VOICE_CORRECT_TIMEOUT_S,
)
from roost.voice.correct import (
    Correction, EnglishCorrector, correction_input, english_fix_body, parse_correction,
)
from roost.voice.spoken import message_parts
from team_helpers import GatedModel, wait_idle
from test_threads_api import O, VALID_AVATAR

BOT = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
SAID = "Yesterday I has goed to the shop."
CORRECTED = "Yesterday I went to the shop."
GOOD_REPLY = json.dumps({"corrected": CORRECTED, "fixes": [{"wrong": "has goed", "right": "went"}]})


class _Worker:
    """A worker model that answers ``reply`` after ``delay`` seconds (or raises), and records the requests."""

    def __init__(self, reply: str = GOOD_REPLY, *, delay: float = 0.0, tool: bool = False) -> None:
        self.reply, self.delay, self.tool = reply, delay, tool
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.tool:
            yield ToolCallRequested("c1", "add_task", {})
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


# -- the pure parts ----------------------------------------------------------------------------------------------


def test_parse_correction_reads_strict_json_and_refuses_anything_else():
    found = parse_correction(GOOD_REPLY, said=SAID)
    assert found == Correction(said=SAID, corrected=CORRECTED, fixes=(("has goed", "went"),))
    assert parse_correction("not json", said=SAID) is None
    assert parse_correction(json.dumps({"corrected": CORRECTED}), said=SAID) is None          # fixes missing
    assert parse_correction(json.dumps({"corrected": "", "fixes": []}), said=SAID) is None    # nothing to show
    assert parse_correction(json.dumps({"corrected": CORRECTED, "fixes": [{"wrong": "x"}]}), said=SAID) is None


def test_parse_correction_treats_no_change_as_nothing_to_post():
    same = json.dumps({"corrected": SAID, "fixes": []})
    assert parse_correction(same, said=SAID) is None
    spaced = json.dumps({"corrected": "  " + SAID + " ", "fixes": []})
    assert parse_correction(spaced, said=SAID) is None


def test_parse_correction_caps_the_fixes_and_their_length():
    too_many = [{"wrong": f"w{i}", "right": f"r{i}"} for i in range(VOICE_CORRECT_FIXES_MAX + 1)]
    assert parse_correction(json.dumps({"corrected": CORRECTED, "fixes": too_many}), said=SAID) is None
    long = [{"wrong": "x" * (VOICE_CORRECT_FIX_CHARS_MAX + 1), "right": "y"}]
    assert parse_correction(json.dumps({"corrected": CORRECTED, "fixes": long}), said=SAID) is None
    fine = [{"wrong": "x" * VOICE_CORRECT_FIX_CHARS_MAX, "right": "y"}]
    assert parse_correction(json.dumps({"corrected": CORRECTED, "fixes": fine}), said=SAID) is not None


def test_parse_correction_drops_a_fix_that_changes_nothing_but_keeps_the_sentence():
    reply = json.dumps({"corrected": CORRECTED, "fixes": [{"wrong": "shop", "right": "shop"},
                                                         {"wrong": "has goed", "right": "went"}]})
    assert parse_correction(reply, said=SAID).fixes == (("has goed", "went"),)


def test_a_worker_that_echoes_the_escaped_words_is_read_back_plain():
    said = "I dont know if he come's today"
    reply = json.dumps({"corrected": "I don&#x27;t know if he&#x27;s coming today",
                        "fixes": [{"wrong": "dont", "right": "don&#x27;t"}, {"wrong": "come&#x27;s", "right": "is coming"}]})
    found = parse_correction(reply, said=said)
    assert found.corrected == "I don't know if he's coming today"
    assert found.fixes == (("dont", "don't"), ("come's", "is coming"))
    unchanged = json.dumps({"corrected": "I dont know if he come&#x27;s today", "fixes": []})
    assert parse_correction(unchanged, said=said) is None     # the same words, escaped: nothing to show


def test_the_input_quotes_the_words_as_escaped_data():
    text = correction_input('I <b>said</b> "hi" & left')
    assert "<said>" in text and "</said>" in text
    assert "&lt;b&gt;" in text and "&quot;hi&quot;" in text and "<b>" not in text


def test_the_body_is_the_contract_json():
    body = json.loads(english_fix_body("m1", Correction(said=SAID, corrected=CORRECTED, fixes=(("has goed", "went"),))))
    assert body == {"message_id": "m1", "said": SAID, "corrected": CORRECTED,
                    "fixes": [{"wrong": "has goed", "right": "went"}]}


def test_the_scripted_worker_corrects_a_known_mistake_and_leaves_a_fine_sentence_alone():
    async def ask(text: str) -> str:
        request = ModelRequest(system="", turns=(ChatTurn("user", correction_input(text)),), tools=(), model="x",
                               agent=VOICE_CORRECT_AGENT)
        parts = [e.text async for e in ScriptedWorker().stream(request) if isinstance(e, TextDelta)]
        return "".join(parts)

    fixed = parse_correction(asyncio.run(ask(SAID)), said=SAID)
    assert fixed is not None and fixed.corrected != SAID and fixed.fixes
    assert parse_correction(asyncio.run(ask("All is well here.")), said="All is well here.") is None


# -- the corrector -----------------------------------------------------------------------------------------------


async def _world():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    app.state.turns._model = GatedModel(["Sure."], hold=())
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    return app, alice, bot_id, thread_id


async def _turn_on(alice, bot_id: str) -> None:
    body = {"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False, "correct_english": True}
    assert (await alice.put(f"/api/bots/{bot_id}/voice", json=body, headers=O)).status_code == 200


async def _fix_lines(alice, thread_id: str) -> list[dict]:
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    return [m for m in messages if m["kind"] == ENGLISH_FIX_KIND]


async def _settle(app) -> None:
    await wait_idle(app.state.turns)
    await app.state.voice_tasks.wait_idle()


async def test_a_spoken_message_gets_one_english_fix_line_under_it_and_the_bot_reads_the_original():
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    worker = _Worker()
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, worker, app.state.voice_tasks)
    sent = (await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)).json()
    await _settle(app)
    lines = await _fix_lines(alice, thread_id)
    assert len(lines) == 1
    line = lines[0]
    assert line["role"] == "activity" and line["tainted"] is False and line["author_bot_id"] == bot_id
    assert json.loads(line["body"]) == {"message_id": sent["message_id"], "said": SAID, "corrected": CORRECTED,
                                        "fixes": [{"wrong": "has goed", "right": "went"}]}
    # the worker saw the words as quoted data on the correction agent, with no tools
    assert len(worker.requests) == 1 and worker.requests[0].agent == VOICE_CORRECT_AGENT
    assert SAID in worker.requests[0].turns[0].text and worker.requests[0].tools == ()
    # the bot's own message, the one its run reads, is the user's original words
    messages = (await alice.get(f"/api/threads/{thread_id}/messages")).json()
    assert next(m for m in messages if m["id"] == sent["message_id"])["body"] == SAID


async def test_the_line_is_published_as_a_message_frame():
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, _Worker(), app.state.voice_tasks)
    seen: list[dict] = []

    def listener(user_id: str, frame: dict) -> None:
        if frame.get("type") == "message" and (frame.get("message") or {}).get("kind") == ENGLISH_FIX_KIND:
            seen.append(frame)

    app.state.events.add_listener(listener)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await _settle(app)
    assert len(seen) == 1 and seen[0]["thread_id"] == thread_id


async def test_a_typed_message_or_a_bot_with_the_switch_off_gets_no_line():
    app, alice, bot_id, thread_id = await _world()
    worker = _Worker()
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, worker, app.state.voice_tasks)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)   # switch off
    await _settle(app)
    await _turn_on(alice, bot_id)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID}, headers=O)                   # typed
    await _settle(app)
    assert await _fix_lines(alice, thread_id) == [] and worker.requests == []


@pytest.mark.parametrize("worker", [
    _Worker("not json"),
    _Worker(json.dumps({"corrected": SAID, "fixes": []})),       # the sentence was fine
    _Worker(tool=True),                                           # the worker asked for a tool
])
async def test_a_bad_reply_or_no_change_posts_nothing(worker):
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, worker, app.state.voice_tasks)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await _settle(app)
    assert await _fix_lines(alice, thread_id) == []


def test_the_instructions_ask_for_every_mistake_in_the_spoken_language():
    # Owner, 2026-11-03: "inside of the London" went uncorrected; Haiku missed it one time in three.
    from roost.voice.correct import CORRECT_SYSTEM
    for words in ("learning", "prepositions", "articles", "verb forms", "the same language"):
        assert words in CORRECT_SYSTEM, words


async def test_a_slow_worker_is_given_up_on(monkeypatch):
    monkeypatch.setattr("roost.voice.correct.VOICE_CORRECT_TIMEOUT_S", 0.05)
    assert VOICE_CORRECT_TIMEOUT_S == 30.0          # owner, 2026-11-03: a 9.9 s answer was dropped at 8 s
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, _Worker(delay=1.0),
                                         app.state.voice_tasks)
    r = await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    assert r.status_code == 202                                   # the response never waits for the worker
    await _settle(app)
    assert await _fix_lines(alice, thread_id) == []


async def test_the_scripted_gateway_makes_a_fix_line_by_itself():
    """``make e2e``: the scripted worker is the default in scripted mode, so the E2E sees a line."""
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await _settle(app)
    lines = await _fix_lines(alice, thread_id)
    assert len(lines) == 1 and json.loads(lines[0]["body"])["fixes"]


async def test_the_line_is_never_a_model_kind_a_preview_or_spoken_and_never_tainted():
    cfg = load_config()
    await init_db(cfg)
    assert ENGLISH_FIX_KIND not in _MODEL_KINDS
    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    app.state.english = EnglishCorrector(app.state.talk, app.state.events, app.state.bots, _Worker(), app.state.voice_tasks)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await _settle(app)
    talk: TalkStore = app.state.talk
    me = (await alice.get("/api/auth/me")).json()["id"]
    latest = await talk.latest_for_bot(me, bot_id)
    assert latest is not None and latest.kind != ENGLISH_FIX_KIND          # the fix never leads the chat list
    assert (await talk.latest_in_thread(me, thread_id)).kind != ENGLISH_FIX_KIND
    line = next(m for m in await talk.list_latest_messages(me, thread_id) if m.kind == ENGLISH_FIX_KIND)
    assert message_parts(line) == [] and line.tainted is False
    text, kind = chat_preview(line)
    assert "{" not in text and kind == "notice"


def test_events_hub_is_the_publisher_the_corrector_uses():
    assert hasattr(EventHub, "publish")


async def test_the_english_fix_counts_its_tokens_as_the_bots_background_work():
    from roost.usage.store import TokenUsageStore

    app, alice, bot_id, thread_id = await _world()
    await _turn_on(alice, bot_id)
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": SAID, "spoken": True}, headers=O)
    await _settle(app)
    me = (await alice.get("/api/auth/me")).json()["id"]
    rows = await TokenUsageStore(load_config()).rows(me, since_day="2000-01-01", bot_id=bot_id)
    assert any(r.kind == "background" and r.totals.calls >= 1 for r in rows)
