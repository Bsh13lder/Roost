"""Every bot has an approval mode and topic switches; new bots ask every time (approvals plan Task 2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.approvals.models import parse_topics, topics_json
from roost.bots.main_bot import ensure_main_bots
from roost.bots.store import BotStore
from roost.constants import APPROVAL_TOPICS
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
LOCKED = ["posting"]


def _client() -> TestClient:
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    assert r.status_code == 201
    return c


def _make_bot(c: TestClient, name: str = "Scout") -> dict:
    r = c.post("/api/bots", json={"name": name, "job": "j", "instructions": "i", "avatar": AVATAR}, headers=O)
    assert r.status_code == 201
    return r.json()


def test_a_new_bot_starts_in_auto_edit_with_auto_review_on():
    """Owner, 2026-11-03: "the bot just does what you ask"."""
    c = _client()
    assert _make_bot(c)["approval"] == {"mode": "auto_edit", "ask_topics": [], "locked_topics": LOCKED,
                                        "auto_review": True}


async def test_the_main_bot_made_for_a_new_account_starts_in_auto_edit_too():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "bob", "pw-123456")
    store = BotStore(cfg)
    [main] = [m.bot for m in await ensure_main_bots(cfg, store) if m.bot.user_id == user.id]
    assert main.approval.mode == "auto_edit" and main.approval.ask_topics == frozenset() and main.approval.auto_review


def test_set_approval_saves_mode_and_topics():
    c = _client()
    bot = _make_bot(c)
    r = c.put(f"/api/bots/{bot['id']}/approval", json={"mode": "auto_edit", "ask_topics": ["money", "files"]}, headers=O)
    assert r.status_code == 200
    expected = {"mode": "auto_edit", "ask_topics": ["files", "money"], "locked_topics": LOCKED, "auto_review": True}
    assert r.json()["approval"] == expected
    assert c.get(f"/api/bots/{bot['id']}").json()["approval"] == expected


def test_posting_is_locked_and_never_stored():
    c = _client()
    bot = _make_bot(c)
    r = c.put(f"/api/bots/{bot['id']}/approval", json={"mode": "plan", "ask_topics": ["posting"]}, headers=O)
    assert r.status_code == 200
    assert r.json()["approval"] == {"mode": "plan", "ask_topics": [], "locked_topics": LOCKED, "auto_review": True}


def test_bad_mode_or_topic_is_422():
    c = _client()
    bot = _make_bot(c)
    url = f"/api/bots/{bot['id']}/approval"
    assert c.put(url, json={"mode": "yolo"}, headers=O).status_code == 422
    assert c.put(url, json={"mode": "ask", "ask_topics": ["lasers"]}, headers=O).status_code == 422
    assert c.put(url, json={"mode": "ask", "extra": 1}, headers=O).status_code == 422
    assert c.put(url, json={"mode": "ask", "ask_topics": ["files"] * (len(APPROVAL_TOPICS) + 1)}, headers=O).status_code == 422


def test_approval_needs_the_origin():
    c = _client()
    bot = _make_bot(c)
    assert c.put(f"/api/bots/{bot['id']}/approval", json={"mode": "ask"}).status_code == 403


async def test_another_users_bot_is_404_for_approval():
    cfg = load_config()
    await init_db(cfg)
    alice = await register_user(cfg, "alice", "pw-123456")
    bob = await register_user(cfg, "bob", "pw-123456")
    from roost.approvals.models import BotApproval
    from roost.bots.models import Avatar, BotDraft
    store = BotStore(cfg)
    bot = await store.create(alice.id, BotDraft("Scout", "j", "i", Avatar("round", "#22c55e", "none")))
    assert await store.set_approval(bob.id, bot.id, BotApproval("plan", frozenset())) is None
    assert (await store.get(alice.id, bot.id)).approval.mode == "auto_edit"
    done = await store.set_approval(alice.id, bot.id, BotApproval("plan", frozenset({"files"})))
    assert done.approval == BotApproval("plan", frozenset({"files"}), auto_review=True)


def test_the_http_route_gives_another_user_a_404():
    c = _client()
    r = c.put("/api/bots/not-a-bot/approval", json={"mode": "ask"}, headers=O)
    assert r.status_code == 404


def test_parse_and_dump_topics_ignore_unknown_and_posting():
    assert parse_topics('["money", "files", "bogus"]') == frozenset({"money", "files"})
    assert parse_topics("not json") == frozenset()
    assert parse_topics('{"a": 1}') == frozenset()
    assert topics_json(frozenset({"money", "files", "posting"})) == '["files", "money"]'
    assert topics_json(frozenset()) == "[]"


@pytest.mark.parametrize("raw", ["[]", '["files"]'])
def test_parse_topics_reads_what_the_migration_wrote(raw):
    assert isinstance(parse_topics(raw), frozenset)
