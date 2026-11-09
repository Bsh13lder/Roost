"""The Bot Journal over HTTP: recent days, one day, search; another user's bot is a 404."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

ORIGIN = {"Origin": "http://127.0.0.1:18800"}


@dataclass(frozen=True)
class Rig:
    app: FastAPI
    alice_id: str
    alice: httpx.AsyncClient
    bob: httpx.AsyncClient
    anon: httpx.AsyncClient


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as anon:
        for client, name in ((alice, "alice"), (bob, "bob")):
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=ORIGIN)
            assert login.status_code == 200
        yield Rig(app, alice_id, alice, bob, anon)


async def _written(rig: Rig, text: str = "Paid the café bill"):
    bot = await make_bot(rig.app.state.config, rig.alice_id, "Ana")
    day = await rig.app.state.journal.append(rig.alice_id, bot.id, bot.name, text)
    return bot, day.day.isoformat()


async def test_list_and_read_a_day(rig):
    bot, day = await _written(rig)
    listed = (await rig.alice.get(f"/api/bots/{bot.id}/journal")).json()
    assert listed == {"days": [{"day": day, "entries": 1, "tainted": False, "updated_at": listed["days"][0]["updated_at"]}]}
    got = (await rig.alice.get(f"/api/bots/{bot.id}/journal/{day}")).json()
    assert got["content"].endswith("Paid the café bill\n") and got["bot_id"] == bot.id and got["entries"] == 1


async def test_a_missing_day_is_404_and_a_bad_day_422(rig):
    bot, _ = await _written(rig)
    assert (await rig.alice.get(f"/api/bots/{bot.id}/journal/2020-01-01")).status_code == 404
    assert (await rig.alice.get(f"/api/bots/{bot.id}/journal/2020-1-1")).status_code == 422
    assert (await rig.alice.get(f"/api/bots/{bot.id}/journal/someday")).status_code == 422


async def test_another_users_bot_is_404_and_search_finds_only_your_days(rig):
    bot, day = await _written(rig)
    assert (await rig.bob.get(f"/api/bots/{bot.id}/journal")).status_code == 404
    assert (await rig.bob.get(f"/api/bots/{bot.id}/journal/{day}")).status_code == 404
    assert (await rig.bob.get("/api/journal/search", params={"q": "bill"})).json() == []
    hits = (await rig.alice.get("/api/journal/search", params={"q": "cafe bill"})).json()
    assert hits == [{"bot_id": bot.id, "bot_name": "Ana", "day": day, "lines": [hits[0]["lines"][0]],
                     "tainted": False}]


async def test_the_journal_needs_a_login(rig):
    bot, day = await _written(rig)
    assert (await rig.anon.get(f"/api/bots/{bot.id}/journal")).status_code == 401
    assert (await rig.anon.get("/api/journal/search", params={"q": "x"})).status_code == 401
