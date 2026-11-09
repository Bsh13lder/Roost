"""``GET /api/routines/occurrences``: routine run times for the calendars (user-scoped, capped, Madrid days)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest

from roost.config import load_config
from roost.constants import ROUTINE_OCCURRENCE_SPAN_DAYS_MAX
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.hub import RoutinesHub
from team_helpers import make_bot, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
MADRID = ZoneInfo("Europe/Madrid")
DAILY = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]}
ROUTE = "/api/routines/occurrences"


@pytest.fixture
async def app():
    config = load_config()
    await init_db(config)
    return create_app(config)


@pytest.fixture
async def alice(app):
    return await register_user(app.state.config, "alice", PASSWORD)


@pytest.fixture
async def bob(app):
    return await register_user(app.state.config, "bob", PASSWORD)


@asynccontextmanager
async def signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


def today() -> date:
    return datetime.now(timezone.utc).astimezone(MADRID).date()


async def _make(client, bot_id: str, name: str, *, enabled: bool = True) -> dict:
    made = await client.post(f"/api/bots/{bot_id}/routines", headers=ORIGIN,
                             json={"name": name, "instructions": "Do it.", "schedule": DAILY, "enabled": enabled})
    assert made.status_code == 201, made.text
    return made.json()


def _span(first: date, last: date, **extra: str) -> dict:
    return {"from": first.isoformat(), "to": last.isoformat(), **extra}


async def test_occurrences_list_each_run_with_its_bot(app, alice):
    gela = await make_bot(app.state.config, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        made = await _make(client, gela.id, "Morning news")
        await _make(client, gela.id, "Paused one", enabled=False)
        first = today() + timedelta(days=1)
        answer = await client.get(ROUTE, params=_span(first, first + timedelta(days=2)))
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["truncated"] is False
    assert [(o["day"], o["time"]) for o in body["occurrences"]] == [
        ((first + timedelta(days=n)).isoformat(), "10:07") for n in range(3)]
    one = body["occurrences"][0]
    assert set(one) == {"routine_id", "routine_name", "bot_id", "bot_name", "at", "day", "time", "log_thread_id"}
    assert (one["routine_id"], one["routine_name"], one["bot_id"], one["bot_name"], one["log_thread_id"]) == (
        made["id"], "Morning news", gela.id, "Gela", made["thread_id"])
    assert one["at"].endswith("Z") or one["at"].endswith("+00:00")


async def test_runs_already_past_are_left_out(app, alice):
    gela = await make_bot(app.state.config, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        await _make(client, gela.id, "Morning news")
        past = today() - timedelta(days=3)
        body = (await client.get(ROUTE, params=_span(past, today() - timedelta(days=1)))).json()
    assert body["occurrences"] == []


async def test_bot_id_narrows_to_one_bot_and_another_users_bot_is_404(app, alice, bob):
    gela = await make_bot(app.state.config, alice.id, "Gela")
    max_bot = await make_bot(app.state.config, alice.id, "Max")
    bobs = await make_bot(app.state.config, bob.id, "Bobby")
    first = today() + timedelta(days=1)
    async with signed_in(app, "bob") as client:
        await _make(client, bobs.id, "Bob's routine")
    async with signed_in(app, "alice") as client:
        await _make(client, gela.id, "News")
        await _make(client, max_bot.id, "Gym")
        everyone = (await client.get(ROUTE, params=_span(first, first))).json()["occurrences"]
        just_max = (await client.get(ROUTE, params=_span(first, first, bot_id=max_bot.id))).json()["occurrences"]
        other = await client.get(ROUTE, params=_span(first, first, bot_id=bobs.id))
        unknown = await client.get(ROUTE, params=_span(first, first, bot_id="nope"))
    assert sorted(o["routine_name"] for o in everyone) == ["Gym", "News"]
    assert [o["bot_name"] for o in just_max] == ["Max"]
    assert other.status_code == 404 and unknown.status_code == 404


async def test_a_bad_window_is_422(app, alice):
    first = today()
    async with signed_in(app, "alice") as client:
        backwards = await client.get(ROUTE, params=_span(first, first - timedelta(days=1)))
        too_long = await client.get(ROUTE, params=_span(first, first + timedelta(days=ROUTINE_OCCURRENCE_SPAN_DAYS_MAX)))
        not_a_day = await client.get(ROUTE, params={"from": "tomorrow", "to": first.isoformat()})
        missing = await client.get(ROUTE)
    assert [r.status_code for r in (backwards, too_long, not_a_day, missing)] == [422, 422, 422, 422]
    assert backwards.json()["detail"] == "The last day comes before the first."


async def test_signed_out_is_401(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        refused = await client.get(ROUTE, params=_span(today(), today()))
    assert refused.status_code == 401


async def test_the_hub_caps_and_starts_at_now(app, alice):
    gela = await make_bot(app.state.config, alice.id, "Gela")
    async with signed_in(app, "alice") as client:
        await client.post(f"/api/bots/{gela.id}/routines", headers=ORIGIN, json={
            "name": "Often", "instructions": "Do it.", "schedule": {"kind": "cron", "expr": "*/15 * * * *"}})
    fixed = datetime(2026, 10, 27, 12, 0, tzinfo=MADRID).astimezone(timezone.utc)
    state = app.state
    hub = RoutinesHub(state.routines, state.routine_store, state.routine_runs, state.bots, clock=lambda: fixed)
    page = await hub.occurrences(alice.id, date(2026, 10, 27), date(2026, 10, 27), cap=5)
    assert [o.time for o in page.occurrences] == ["12:00", "12:15", "12:30", "12:45", "13:00"]  # a slot due right now still shows
    assert page.truncated is True
