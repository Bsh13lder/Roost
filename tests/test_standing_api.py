"""The standing permission routes (Step 2): ``GET``/``POST /api/routines/{id}/permissions`` and
``DELETE /api/routines/{id}/permissions/{permission_id}``. Only the owner's own click makes one (Origin on every
write); plain 422 sentences for a bad site, action, count or date; another user's routine is 404."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.standing.constants import STANDING_PER_ROUTINE_MAX, STANDING_UNTIL_MAX_DAYS
from roost.work.runs import madrid_today
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1], "times": ["10:07"]}


def _today() -> date:
    return date.fromisoformat(madrid_today(datetime.now(timezone.utc)))


def perm(**kw) -> dict:
    return {"host": "x.com", "action": "post", "max_per_day": 1,
            "until": (_today() + timedelta(days=7)).isoformat(), **kw}


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


async def _routine(client, bot) -> str:
    made = await client.post(f"/api/bots/{bot.id}/routines", headers=O, json={
        "name": "Weekly post", "instructions": "Post the weekly update on x.com.", "schedule": TIMES})
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def test_add_list_and_revoke(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        path = f"/api/routines/{routine_id}/permissions"
        assert (await client.get(path)).json() == {"permissions": []}
        made = await client.post(path, json=perm(host="WWW.X.com"), headers=O)
        assert made.status_code == 201, made.text
        out = made.json()
        assert {k: out[k] for k in ("host", "action", "max_per_day", "used_today", "routine_id")} == {
            "host": "x.com", "action": "post", "max_per_day": 1, "used_today": 0, "routine_id": routine_id}
        assert [p["id"] for p in (await client.get(path)).json()["permissions"]] == [out["id"]]
        assert (await client.delete(f"{path}/{out['id']}", headers=O)).status_code == 204
        assert (await client.get(path)).json() == {"permissions": []}
        assert (await client.delete(f"{path}/{out['id']}", headers=O)).status_code == 404


async def test_writes_need_the_origin(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        path = f"/api/routines/{routine_id}/permissions"
        assert (await client.post(path, json=perm(), headers=BAD_O)).status_code == 403
        made = (await client.post(path, json=perm(), headers=O)).json()
        assert (await client.delete(f"{path}/{made['id']}", headers=BAD_O)).status_code == 403


@pytest.mark.parametrize(("change", "text"), [
    ({"host": "https://x.com/home"}, "Name the site as a plain address, such as x.com."),
    ({"action": "spend"}, "Pick post, send or submit."),
    ({"action": "delete"}, "Pick post, send or submit."),
    ({"max_per_day": 0}, "Pick 1 to 20 a day."),
    ({"max_per_day": 21}, "Pick 1 to 20 a day."),
    ({"until": "soon"}, "Pick an end date."),
    ({"until": "2020-01-01"}, "Pick an end date from today on."),
])
async def test_bad_permissions_are_422_with_plain_text(app, cfg, alice, change, text):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        response = await client.post(f"/api/routines/{routine_id}/permissions", json=perm(**change), headers=O)
        assert (response.status_code, response.json()["detail"]) == (422, text)


async def test_the_end_date_is_at_most_thirty_days_out(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        path = f"/api/routines/{routine_id}/permissions"
        last = (_today() + timedelta(days=STANDING_UNTIL_MAX_DAYS)).isoformat()
        assert (await client.post(path, json=perm(until=last), headers=O)).status_code == 201
        late = (_today() + timedelta(days=STANDING_UNTIL_MAX_DAYS + 1)).isoformat()
        response = await client.post(path, json=perm(until=late, action="send"), headers=O)
        assert (response.status_code, response.json()["detail"]) == (
            422, f"Pick an end date at most {STANDING_UNTIL_MAX_DAYS} days ahead.")


async def test_a_routine_holds_a_few_and_the_same_site_and_action_replaces(app, cfg, alice):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        path = f"/api/routines/{routine_id}/permissions"
        hosts = [f"site{i}.com" for i in range(STANDING_PER_ROUTINE_MAX)]
        for host in hosts:
            assert (await client.post(path, json=perm(host=host), headers=O)).status_code == 201
        assert (await client.post(path, json=perm(host=hosts[0], max_per_day=3), headers=O)).status_code == 201
        full = await client.post(path, json=perm(host="more.com"), headers=O)
        assert full.status_code == 422 and "already" in full.json()["detail"]
        listed = (await client.get(path)).json()["permissions"]
        assert len(listed) == STANDING_PER_ROUTINE_MAX


async def test_another_users_routine_is_404(app, cfg, alice, bob):
    bot = await make_bot(cfg, alice.id, "Poster")
    async with signed_in(app, "alice") as client:
        routine_id = await _routine(client, bot)
        made = (await client.post(f"/api/routines/{routine_id}/permissions", json=perm(), headers=O)).json()
    async with signed_in(app, "bob") as client:
        path = f"/api/routines/{routine_id}/permissions"
        assert (await client.get(path)).status_code == 404
        assert (await client.post(path, json=perm(), headers=O)).status_code == 404
        assert (await client.delete(f"{path}/{made['id']}", headers=O)).status_code == 404
