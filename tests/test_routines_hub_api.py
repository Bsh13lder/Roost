"""All routines in one place: ``GET /api/routines``, ``GET /api/routines/runs``, the routine templates and
``POST /api/bots/{id}/routines/from-template``."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.schedule import parse_schedule
from roost.routines.templates import ROUTINE_TEMPLATES, template_by_id
from team_helpers import make_bot, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]}


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
                                  headers=ORIGIN)).status_code == 200
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


async def _make(client, bot_id: str, name: str) -> dict:
    created = await client.post(f"/api/bots/{bot_id}/routines", headers=ORIGIN,
                                json={"name": name, "instructions": "Do it.", "schedule": TIMES})
    assert created.status_code == 201, created.text
    return created.json()


# --- templates -------------------------------------------------------------------------------------------------

def test_every_template_is_a_valid_routine():
    ids = [t.id for t in ROUTINE_TEMPLATES]
    assert len(ids) == len(set(ids)) >= 5
    for template in ROUTINE_TEMPLATES:
        parse_schedule(template.schedule, name=template.name)
        assert template.instructions.strip()
    assert template_by_id("morning-brief") is not None and template_by_id("nope") is None


def test_a_template_with_a_placeholder_needs_editing():
    for template in ROUTINE_TEMPLATES:
        assert template.needs_edit == ("<" in template.instructions), template.id
    assert template_by_id("price-watch").needs_edit is True
    assert template_by_id("morning-brief").needs_edit is False


async def test_templates_are_listed_with_words(app, alice):
    async with signed_in(app, "alice") as client:
        listed = (await client.get("/api/routine-templates")).json()["templates"]
    assert [t["id"] for t in listed] == [t.id for t in ROUTINE_TEMPLATES]
    first = listed[0]
    assert set(first) == {"id", "name", "instructions", "schedule", "words", "needs_edit"} and first["words"]
    assert {t["id"]: t["needs_edit"] for t in listed}["price-watch"] is True


async def test_add_a_template_to_a_bot(app, alice):
    bot = await make_bot(app.state.config, alice.id, "Scout")
    async with signed_in(app, "alice") as client:
        made = await client.post(f"/api/bots/{bot.id}/routines/from-template", json={"template_id": "morning-brief"},
                                 headers=ORIGIN)
        assert made.status_code == 201, made.text
        template = template_by_id("morning-brief")
        assert made.json()["name"] == template.name and made.json()["created_by"] == "user"
        assert made.json()["tainted"] is False and made.json()["enabled"] is True
        listed = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert [r["name"] for r in listed] == [template.name]
        unknown = await client.post(f"/api/bots/{bot.id}/routines/from-template", json={"template_id": "nope"},
                                    headers=ORIGIN)
        assert (unknown.status_code, unknown.json()["detail"]) == (422, "There's no such template.")
        extra = await client.post(f"/api/bots/{bot.id}/routines/from-template",
                                  json={"template_id": "morning-brief", "tainted": True}, headers=ORIGIN)
        assert extra.status_code == 422
        for headers in ({}, BAD_O):
            refused = await client.post(f"/api/bots/{bot.id}/routines/from-template",
                                        json={"template_id": "morning-brief"}, headers=headers)
            assert refused.status_code == 403


async def test_a_template_with_a_placeholder_is_added_paused(app, alice):
    bot = await make_bot(app.state.config, alice.id, "Scout")
    async with signed_in(app, "alice") as client:
        made = await client.post(f"/api/bots/{bot.id}/routines/from-template", json={"template_id": "price-watch"},
                                 headers=ORIGIN)
        assert made.status_code == 201, made.text
        assert made.json()["enabled"] is False and made.json()["next_run_at"] is None
        [listed] = (await client.get("/api/routines")).json()["routines"]
    assert listed["enabled"] is False and listed["next_run_madrid"] is None


# --- every routine ---------------------------------------------------------------------------------------------

async def test_all_routines_across_bots_with_bot_names_and_madrid_next(app, alice):
    scout = await make_bot(app.state.config, alice.id, "Scout")
    quill = await make_bot(app.state.config, alice.id, "Quill")
    async with signed_in(app, "alice") as client:
        one = await _make(client, scout.id, "Morning news")
        two = await _make(client, quill.id, "Write diary")
        listed = (await client.get("/api/routines")).json()["routines"]
    assert [(r["id"], r["bot_id"], r["bot_name"]) for r in listed] == [
        (one["id"], scout.id, "Scout"), (two["id"], quill.id, "Quill")]
    first = listed[0]
    assert first["next_run_madrid"][11:16] == "10:07"
    assert first["next_run_madrid"].endswith(("+01:00", "+02:00"))
    assert first["last_state"] is None and first["last_note"] is None and first["last_finished_at"] is None


async def test_the_last_result_is_the_newest_run(app, alice):
    scout = await make_bot(app.state.config, alice.id, "Scout")
    async with signed_in(app, "alice") as client:
        made = await _make(client, scout.id, "Morning news")
        routine = await app.state.routine_store.get(alice.id, made["id"])
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await app.state.routine_runs.record(alice.id, routine, base, "done")
        await app.state.routine_runs.record(alice.id, routine, base + timedelta(days=1), "error", note="It broke.")
        [row] = (await client.get("/api/routines")).json()["routines"]
    assert (row["last_state"], row["last_note"]) == ("error", "It broke.")
    assert row["last_finished_at"]


async def test_a_paused_routine_has_no_next_run(app, alice):
    scout = await make_bot(app.state.config, alice.id, "Scout")
    async with signed_in(app, "alice") as client:
        made = await _make(client, scout.id, "Morning news")
        await client.patch(f"/api/routines/{made['id']}", json={"enabled": False}, headers=ORIGIN)
        [row] = (await client.get("/api/routines")).json()["routines"]
    assert row["enabled"] is False and row["next_run_madrid"] is None


async def test_recent_runs_across_bots_newest_first_with_a_limit(app, alice):
    scout = await make_bot(app.state.config, alice.id, "Scout")
    quill = await make_bot(app.state.config, alice.id, "Quill")
    async with signed_in(app, "alice") as client:
        one = await app.state.routine_store.get(alice.id, (await _make(client, scout.id, "News"))["id"])
        two = await app.state.routine_store.get(alice.id, (await _make(client, quill.id, "Diary"))["id"])
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await app.state.routine_runs.record(alice.id, one, base, "done")
        await app.state.routine_runs.record(alice.id, two, base + timedelta(days=1), "missed")
        await app.state.routine_runs.record(alice.id, one, base + timedelta(days=2), "done")
        runs = (await client.get("/api/routines/runs")).json()["runs"]
        assert [(r["routine_name"], r["bot_name"], r["state"]) for r in runs] == [
            ("News", "Scout", "done"), ("Diary", "Quill", "missed"), ("News", "Scout", "done")]
        assert runs[0]["routine_id"] == one.id and runs[0]["bot_id"] == scout.id
        two_only = (await client.get("/api/routines/runs", params={"limit": 2})).json()["runs"]
        assert len(two_only) == 2
        for bad in (0, -1, 10_000, "x"):
            assert (await client.get("/api/routines/runs", params={"limit": bad})).status_code == 422


async def test_another_users_routines_and_runs_are_never_listed(app, alice, bob):
    scout = await make_bot(app.state.config, alice.id, "Scout")
    await make_bot(app.state.config, bob.id, "Mallory")
    async with signed_in(app, "alice") as client:
        made = await _make(client, scout.id, "Morning news")
        routine = await app.state.routine_store.get(alice.id, made["id"])
        await app.state.routine_runs.record(alice.id, routine, datetime(2026, 1, 1, tzinfo=timezone.utc), "done")
    async with signed_in(app, "bob") as client:
        assert (await client.get("/api/routines")).json()["routines"] == []
        assert (await client.get("/api/routines/runs")).json()["runs"] == []
        stolen = await client.post(f"/api/bots/{scout.id}/routines/from-template",
                                   json={"template_id": "morning-brief"}, headers=ORIGIN)
        assert stolen.status_code == 404


async def test_the_new_routes_need_a_login(app, alice):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anon:
        for method, path in (("GET", "/api/routines"), ("GET", "/api/routines/runs"),
                             ("GET", "/api/routine-templates"), ("POST", "/api/bots/x/routines/from-template")):
            assert (await anon.request(method, path, headers=ORIGIN, json={})).status_code == 401, (method, path)
