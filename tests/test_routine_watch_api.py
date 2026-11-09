"""The watch on the routine routes: set, shown, refused, stopped, and another user's routine is a 404."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]}
WATCH = {"url": "https://web.whatsapp.com/", "part": "the physio chat", "every_min": 5}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def app(cfg):
    return create_app(cfg)


@asynccontextmanager
async def signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@pytest.fixture
async def bob(cfg):
    return await register_user(cfg, "bob", PASSWORD)


def body(**kw) -> dict:
    return {"name": "Watch physio chat", "instructions": "Tell me what Ana wrote.", "schedule": TIMES, **kw}


async def test_a_routine_with_a_watch_shows_it(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        made = await client.post(f"/api/bots/{bot.id}/routines", json=body(watch=WATCH), headers=O)
        assert made.status_code == 201, made.text
        out = made.json()
        assert out["watch"] == {**WATCH, "host": "web.whatsapp.com", "last_checked_at": None,
                                "last_changed_at": None}
        assert out["words"] == "Watching web.whatsapp.com · every 5 min"
        listed = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert listed[0]["watch"]["part"] == "the physio chat"
        hub = (await client.get("/api/routines")).json()["routines"]
        assert hub[0]["watch"]["host"] == "web.whatsapp.com"


async def test_the_watch_is_switched_off_and_changed_by_patch(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        made = (await client.post(f"/api/bots/{bot.id}/routines", json=body(), headers=O)).json()
        assert made["watch"] is None
        watched = await client.patch(f"/api/routines/{made['id']}", json={"watch": {**WATCH, "every_min": 30}},
                                     headers=O)
        assert watched.status_code == 200 and watched.json()["watch"]["every_min"] == 30
        renamed = await client.patch(f"/api/routines/{made['id']}", json={"name": "Physio"}, headers=O)
        assert renamed.json()["watch"]["every_min"] == 30          # a patch without watch keeps it
        off = await client.patch(f"/api/routines/{made['id']}", json={"watch": None}, headers=O)
        assert off.status_code == 200 and off.json()["watch"] is None


@pytest.mark.parametrize("watch", [
    {"url": "http://localhost:8080/", "every_min": 5}, {"url": "https://x.com/", "every_min": 1},
    {"url": "javascript:alert(1)"}, {"url": "https://x.com/", "part": "p" * 500},
])
async def test_a_bad_watch_is_refused_in_plain_words(app, cfg, alice, watch):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        refused = await client.post(f"/api/bots/{bot.id}/routines", json=body(watch=watch), headers=O)
        assert refused.status_code == 422
        assert isinstance(refused.json()["detail"], (str, list))


async def test_an_unknown_watch_key_is_refused(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        refused = await client.post(f"/api/bots/{bot.id}/routines",
                                    json=body(watch={**WATCH, "script": "x"}), headers=O)
        assert refused.status_code == 422


async def test_another_users_routine_is_a_404(app, cfg, alice, bob):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        made = (await client.post(f"/api/bots/{bot.id}/routines", json=body(watch=WATCH), headers=O)).json()
    async with signed_in(app, "bob") as other:
        patched = await other.patch(f"/api/routines/{made['id']}", json={"watch": None}, headers=O)
        assert patched.status_code == 404


async def test_a_new_address_starts_a_new_baseline(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        made = (await client.post(f"/api/bots/{bot.id}/routines", json=body(watch=WATCH), headers=O)).json()
        store = app.state.watch_store
        await store.save(alice.id, made["id"], snapshot="old page", fingerprint="f", changed=False)
        same = await client.patch(f"/api/routines/{made['id']}", json={"watch": {**WATCH, "every_min": 10}},
                                  headers=O)
        assert same.json()["watch"]["last_checked_at"] is not None
        assert await store.get(alice.id, made["id"]) is not None
        await client.patch(f"/api/routines/{made['id']}",
                           json={"watch": {**WATCH, "url": "https://shop.example/"}}, headers=O)
        assert await store.get(alice.id, made["id"]) is None
