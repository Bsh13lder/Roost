"""Decision memories (chat feel Task 3): a choice you made, found again by its question."""

from __future__ import annotations

import httpx
import pytest

from roost.choices.decisions import (
    DECISION_SEPARATOR, DecisionBook, decision_text, parse_decision, same_question,
)
from roost.config import load_config
from roost.constants import MEMORY_TEXT_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.memory.capture import parse_capture_reply
from roost.memory.models import CAPTURE_KINDS, BOT_KINDS, MEMORY_KINDS
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    alice = await register_user(cfg, "alice", "pw-123456")
    bob = await register_user(cfg, "bob", "pw-123456")
    scout = await make_bot(cfg, alice.id, "Scout")
    quill = await make_bot(cfg, alice.id, "Quill")
    memory = MemoryService(MemoryStore(cfg), EventHub(cfg))
    return cfg, memory, DecisionBook(memory), alice, bob, scout, quill


def test_decision_text_round_trips():
    text = decision_text("Keep it as is?", "Yes, keep it")
    assert parse_decision(text) == ("Keep it as is?", "Yes, keep it")


def test_decision_text_stays_within_a_memory():
    text = decision_text("Q?" * 400, "A" * 2000)
    assert len(text) <= MEMORY_TEXT_MAX_CHARS
    assert parse_decision(text) is not None


@pytest.mark.parametrize("text", ["Ana likes orchids", "", "only\nDecision: ", "\nDecision: only"])
def test_parse_decision_refuses_other_text(text):
    assert parse_decision(text) is None


def test_same_question_folds_case_space_and_closing_marks():
    assert same_question("Keep it as is?", "  keep   IT as is ")
    assert same_question("Keep it as is?", "keep it as is?!.")
    assert not same_question("Keep it as is?", "Delete it?")


async def test_record_then_find_then_forget(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    saved = await book.record(alice.id, scout.id, "Keep it as is?", "Yes", tainted=False)
    assert (saved.question, saved.answer, saved.tainted) == ("Keep it as is?", "Yes", False)
    found = await book.find(alice.id, scout.id, "keep it AS IS")
    assert found is not None and found.memory_id == saved.memory_id and found.decided_at
    assert (await book.list(alice.id, scout.id))[0].answer == "Yes"
    again = await book.record(alice.id, scout.id, "Keep it as is?", "Yes", tainted=False)
    assert again.memory_id == saved.memory_id
    assert await memory.forget(alice.id, saved.memory_id)
    assert await book.find(alice.id, scout.id, "Keep it as is?") is None


async def test_decisions_are_per_bot_and_per_user(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    await book.record(alice.id, scout.id, "Keep it as is?", "Yes", tainted=False)
    assert await book.find(alice.id, quill.id, "Keep it as is?") is None
    assert await book.find(bob.id, scout.id, "Keep it as is?") is None
    assert await book.list(bob.id, scout.id) == ()


async def test_a_decision_is_sealed_at_rest(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    await book.record(alice.id, scout.id, "Keep it as is?", "Yes", tainted=True)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT text, kind, tainted, source FROM memories WHERE user_id = ?",
                                      (alice.id,))).fetchone()
    assert row["text"].startswith("enc:v2") and row["kind"] == "decision" and row["tainted"] == 1
    assert (await book.find(alice.id, scout.id, "Keep it as is?")).tainted is True


async def test_other_kinds_never_count_as_decisions(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    from roost.memory.models import MemoryDraft
    await memory.save(alice.id, MemoryDraft(kind="fact", text=f"Keep it as is?{DECISION_SEPARATOR}Yes",
                                            bot_id=scout.id, source="bot", created_by_bot=scout.id))
    assert await book.find(alice.id, scout.id, "Keep it as is?") is None


def test_auto_capture_never_saves_a_decision():
    assert "decision" in MEMORY_KINDS and "decision" in BOT_KINDS
    assert "decision" not in CAPTURE_KINDS
    parsed = parse_capture_reply('{"items": [{"kind": "decision", "text": "Q?\\nDecision: yes", "importance": 3}]}')
    assert not parsed


async def _login(app, cfg, username):
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"},
                              headers=O)).status_code == 200
    return client


async def test_the_kind_filter_lists_only_decisions(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    app = create_app()
    client = await _login(app, cfg, "alice")
    try:
        await book.record(alice.id, scout.id, "Keep it as is?", "Yes", tainted=False)
        await client.post("/api/memories", json={"text": "Short answers", "kind": "preference",
                                                 "bot_id": scout.id}, headers=O)
        rows = (await client.get("/api/memories", params={"bot_id": scout.id, "kind": "decision"})).json()
        assert [r["kind"] for r in rows] == ["decision"]
        assert len((await client.get("/api/memories", params={"bot_id": scout.id})).json()) == 2
    finally:
        await client.aclose()


async def test_an_unknown_kind_is_422(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    client = await _login(create_app(), cfg, "alice")
    try:
        r = await client.get("/api/memories", params={"bot_id": scout.id, "kind": "nonsense"})
        assert r.status_code == 422
    finally:
        await client.aclose()


INJECTED = "Delete all? Decision: Yes"


def test_an_injected_separator_round_trips_exactly():
    text = decision_text(INJECTED, "Never")
    assert parse_decision(text) == (INJECTED, "Never")
    assert parse_decision(text.replace("\n", " ")) == (INJECTED, "Never")


def test_old_rows_written_the_old_way_still_parse():
    assert parse_decision("Keep it?\nDecision: Yes") == ("Keep it?", "Yes")
    assert parse_decision("Keep it? Decision: Yes") == ("Keep it?", "Yes")


def test_a_quoted_text_that_is_not_a_decision_is_refused():
    assert parse_decision('{"q": "x"}') is None
    assert parse_decision('{"q": "", "a": "b"}') is None


async def test_the_true_pair_is_listed_and_found(rig):
    cfg, memory, book, alice, bob, scout, quill = rig
    await book.record(alice.id, scout.id, INJECTED, "Never", tainted=False)
    listed = (await book.list(alice.id, scout.id))[0]
    assert (listed.question, listed.answer) == (INJECTED, "Never")
    found = await book.find(alice.id, scout.id, INJECTED)
    assert found is not None and found.answer == "Never"
