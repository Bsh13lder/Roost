"""Day notes over HTTP (Batch F, G7): auth, origin, ownership, ranges, retired bots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
import pytest
from fastapi import FastAPI

from roost.config import RoostConfig, load_config
from roost.day_notes.models import DayNoteDraft
from roost.day_notes.store import DayNoteStore
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
EVIL = {"Origin": "http://evil.example"}
KEYS = {"id", "day", "author_kind", "bot_id", "bot_name", "text", "created_at", "tainted"}
RANGE = {"from": "2026-10-01", "to": "2026-10-31"}


def _today() -> str:
    from roost.day_notes.service import madrid_today
    return madrid_today().isoformat()


@dataclass(frozen=True)
class Rig:
    app: FastAPI
    cfg: RoostConfig
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
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
            assert login.status_code == 200
        yield Rig(app, cfg, alice_id, alice, bob, anon)


async def test_post_get_delete_round_trip(rig):
    day = _today()
    made = await rig.alice.post("/api/day-notes", json={"day": day, "text": "  Call Ana  "}, headers=O)
    assert made.status_code == 201
    body = made.json()
    assert set(body) == KEYS and (body["author_kind"], body["bot_id"], body["text"], body["tainted"]) == (
        "user", None, "Call Ana", False)
    got = await rig.alice.get("/api/day-notes", params={"from": day, "to": day})
    assert [n["id"] for n in got.json()] == [body["id"]]
    assert (await rig.alice.delete(f"/api/day-notes/{body['id']}", headers=O)).status_code == 204
    assert (await rig.alice.get("/api/day-notes", params={"from": day, "to": day})).json() == []
    assert (await rig.alice.delete(f"/api/day-notes/{body['id']}", headers=O)).status_code == 404
    frames = [e["change"] for e in await rig.app.state.events.since(rig.alice_id, 0) if e["type"] == "day_notes_changed"]
    assert frames == ["created", "deleted"]


async def test_another_users_note_is_404_for_delete_and_absent_from_get(rig):
    day = _today()
    note = (await rig.alice.post("/api/day-notes", json={"day": day, "text": "mine"}, headers=O)).json()
    assert (await rig.bob.delete(f"/api/day-notes/{note['id']}", headers=O)).status_code == 404
    assert (await rig.bob.get("/api/day-notes", params={"from": day, "to": day})).json() == []
    assert len((await rig.alice.get("/api/day-notes", params={"from": day, "to": day})).json()) == 1


async def test_every_route_needs_a_login_and_every_write_the_origin(rig):
    day = _today()
    assert (await rig.anon.get("/api/day-notes", params={"from": day, "to": day})).status_code == 401
    assert (await rig.anon.post("/api/day-notes", json={"day": day, "text": "x"}, headers=O)).status_code == 401
    assert (await rig.anon.delete("/api/day-notes/x", headers=O)).status_code == 401
    note = (await rig.alice.post("/api/day-notes", json={"day": day, "text": "x"}, headers=O)).json()
    for headers in ({}, EVIL):
        assert (await rig.alice.post("/api/day-notes", json={"day": day, "text": "y"}, headers=headers)).status_code == 403
        assert (await rig.alice.delete(f"/api/day-notes/{note['id']}", headers=headers)).status_code == 403
    assert len((await rig.alice.get("/api/day-notes", params={"from": day, "to": day})).json()) == 1


async def test_range_is_required_ordered_and_bounded(rig):
    get = rig.alice.get
    assert (await get("/api/day-notes")).status_code == 422
    assert (await get("/api/day-notes", params={"from": "2026-10-01"})).status_code == 422
    assert (await get("/api/day-notes", params={"from": "2026-10-05", "to": "2026-10-01"})).status_code == 422
    assert (await get("/api/day-notes", params={"from": "2026-01-01", "to": "2026-12-31"})).status_code == 422
    assert (await get("/api/day-notes", params={"from": "2026-13-01", "to": "2026-13-02"})).status_code == 422
    assert (await get("/api/day-notes", params={"from": "20261001", "to": "20261002"})).status_code == 422
    assert (await get("/api/day-notes", params={"from": "2026-10-01", "to": "2026-12-01"})).status_code == 200   # 62 days


async def test_post_checks_day_text_and_extra_fields(rig):
    post = rig.alice.post
    day = _today()
    assert (await post("/api/day-notes", json={"day": day, "text": "x", "author_kind": "bot"}, headers=O)).status_code == 422
    assert (await post("/api/day-notes", json={"day": day, "text": "x", "bot_id": "b"}, headers=O)).status_code == 422
    assert (await post("/api/day-notes", json={"day": day, "text": "x", "tainted": True}, headers=O)).status_code == 422
    for bad in ("2026-02-30", "tomorrow", "20261001", "2026-1-5", ""):
        assert (await post("/api/day-notes", json={"day": bad, "text": "x"}, headers=O)).status_code == 422
    for text in ("", "  ", "x" * 501):
        r = await post("/api/day-notes", json={"day": day, "text": text}, headers=O)
        assert r.status_code == 422
    assert (await post("/api/day-notes", json={"day": "2099-01-01", "text": "x"}, headers=O)).status_code == 422
    r = await post("/api/day-notes", json={"day": day, "text": "x" * 501}, headers=O)
    assert "500 characters" in str(r.json())


async def test_a_retired_bots_note_says_a_retired_bot(rig):
    bot = await make_bot(rig.cfg, rig.alice_id, "Planner")
    day = date(2026, 10, 21)
    await DayNoteStore(rig.cfg).add(rig.alice_id, DayNoteDraft(day=day, text="from bot"), bot_id=bot.id, tainted=True)
    rows = (await rig.alice.get("/api/day-notes", params={"from": "2026-10-21", "to": "2026-10-21"})).json()
    assert (rows[0]["author_kind"], rows[0]["bot_id"], rows[0]["bot_name"], rows[0]["tainted"]) == (
        "bot", bot.id, "Planner", True)
    async with db_session(rig.cfg) as db:
        await db.execute("DELETE FROM bots WHERE id = ?", (bot.id,))
        await db.commit()
    rows = (await rig.alice.get("/api/day-notes", params={"from": "2026-10-21", "to": "2026-10-21"})).json()
    assert (rows[0]["bot_id"], rows[0]["bot_name"]) == (None, "A retired bot")
