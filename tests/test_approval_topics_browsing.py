"""C3 Task 10: the Browsing actions topic.

Amendment 2026-10-21 (user): browsing is an ordinary opt-in topic, off by default; there is no "-browsing"
opt-out word, and old rows need no change."""

from __future__ import annotations

from typing import get_args

import pytest
from fastapi.testclient import TestClient

from roost.approvals.models import Topic, parse_topics, topics_json
from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import DEFAULT_ASK_TOPICS
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

_O = {"Origin": "http://127.0.0.1:18800"}
_AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def test_old_rows_do_not_ask_for_browsing():
    assert parse_topics('["files"]') == frozenset({"files"})
    assert DEFAULT_ASK_TOPICS == frozenset()


def test_browsing_round_trips_and_a_minus_word_means_nothing():
    stored = topics_json(frozenset({"browsing", "files"}))
    assert stored == '["browsing", "files"]'
    assert parse_topics(stored) == frozenset({"browsing", "files"})
    assert parse_topics('["-browsing"]') == frozenset()
    assert topics_json(frozenset()) == "[]"


def test_browsing_is_a_topic():
    assert "browsing" in get_args(Topic)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_an_old_row_reads_without_browsing(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await BotStore(cfg).create(user.id, BotDraft("Scout", "j", "", Avatar("round", "#22c55e", "none")))
    async with db_session(cfg) as db:
        await db.execute("UPDATE bots SET approval_ask_topics = ? WHERE id = ?", ('["files"]', bot.id))
        await db.commit()
    again = await BotStore(cfg).get(user.id, bot.id)
    assert again is not None and "browsing" not in again.approval.ask_topics


def test_the_bot_approval_route_takes_and_returns_browsing():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "bob", "password": "pw-123456"}, headers=_O).status_code == 201
    bot = c.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "i", "avatar": _AVATAR},
                 headers=_O).json()
    assert bot["approval"]["ask_topics"] == []                       # new bots: browsing does not ask
    url = f"/api/bots/{bot['id']}/approval"
    r = c.put(url, json={"mode": "auto_edit", "ask_topics": ["browsing", "files"]}, headers=_O)
    assert r.status_code == 200 and r.json()["approval"]["ask_topics"] == ["browsing", "files"]
    assert c.get(f"/api/bots/{bot['id']}").json()["approval"]["ask_topics"] == ["browsing", "files"]
    assert c.put(url, json={"mode": "ask", "ask_topics": ["-browsing"]}, headers=_O).status_code == 422
