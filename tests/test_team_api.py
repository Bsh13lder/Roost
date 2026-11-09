"""Main-bot star — D-B. ``tests/test_main_bot.py`` covers the star's own
rules (it moves, it never vanishes) and the Chief template (S1 D4)."""

from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _bot(c: TestClient, name: str) -> dict:
    r = c.post("/api/bots", json={"name": name, "job": "helps", "instructions": "", "avatar": AVATAR}, headers=O)
    assert r.status_code == 201
    return r.json()


def test_star_routes_404_for_unknown_bots_and_need_an_origin():
    c = _client()
    bot = _bot(c, "Scout")
    assert c.post("/api/bots/not-a-bot/star", headers=O).status_code == 404
    assert c.delete("/api/bots/not-a-bot/star", headers=O).status_code == 404
    assert c.post(f"/api/bots/{bot['id']}/star").status_code == 403


async def test_starring_publishes_bot_updated_for_both_bots():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "alice", "pw-123456")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        a = (await client.post("/api/bots", json={"name": "Boss", "job": "j", "instructions": "", "avatar": AVATAR}, headers=O)).json()
        b = (await client.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "", "avatar": AVATAR}, headers=O)).json()
        await client.post(f"/api/bots/{a['id']}/star", headers=O)
        me = (await client.get("/api/auth/me")).json()
        sub = app.state.events.subscribe(me["id"])
        await client.post(f"/api/bots/{b['id']}/star", headers=O)
        frames = [await asyncio.wait_for(sub.__anext__(), timeout=1) for _ in range(2)]
        sub.close()
    assert [(f["type"], f["bot"]["name"], f["bot"]["is_primary"]) for f in frames] == [
        ("bot_updated", "Scout", True), ("bot_updated", "Boss", False),
    ]
