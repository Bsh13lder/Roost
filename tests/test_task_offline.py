"""Offline tasks (docs/plans/2026-11-08-roost-offline-tasks.md O4, O5): a line the phone kept while it couldn't
reach Roost is read as of the moment it was typed, never handed to a bot, never guessed, and made once."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from tz_helpers import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _offline(c: TestClient, text: str, typed_at: datetime, client_id: str | None = None) -> httpx.Response:
    body = {"client_id": client_id or str(uuid4()), "text": text, "typed_at": typed_at.isoformat()}
    return c.post("/api/tasks/offline", json=body, headers=O)


def _hours_ago(hours: int) -> datetime:
    return datetime.now(MADRID_TZ) - timedelta(hours=hours)


def test_a_line_is_read_as_of_the_moment_it_was_typed():
    c = _client()
    typed = _hours_ago(30)
    made = _offline(c, "Call mom tomorrow at 10 !high", typed)
    assert made.status_code == 201, made.text
    task = made.json()
    expected = datetime.combine(typed.date() + timedelta(days=1), datetime.min.time().replace(hour=10),
                                tzinfo=MADRID_TZ)
    assert (task["title"], task["priority"], task["created"]) == ("Call mom", "high", True)
    assert task["due_date"] == expected.isoformat()


def test_the_same_client_id_makes_one_task():
    c = _client()
    client_id = str(uuid4())
    first = _offline(c, "Buy bread", _hours_ago(1), client_id)
    again = _offline(c, "Buy bread", _hours_ago(1), client_id)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"] and again.json()["created"] is False
    assert [t["title"] for t in c.get("/api/tasks").json()] == ["Buy bread"]


def test_it_is_never_handed_to_a_bot_and_an_unknown_project_stays_in_the_title():
    c = _client()
    c.post("/api/bots", json={"name": "Scout", "job": "helps", "instructions": "", "avatar": AVATAR}, headers=O)
    task = _offline(c, "Fix the sink /Nowhere @Scout", _hours_ago(1)).json()
    assert task["owner"] == "user" and task["project_id"] is None
    assert "/Nowhere" in task["title"] and "@Scout" in task["title"]


def test_a_line_of_only_chips_keeps_the_whole_line_as_its_title():
    c = _client()
    task = _offline(c, "tomorrow", _hours_ago(1)).json()
    assert task["title"] == "tomorrow"


def test_bad_bodies_are_refused():
    c = _client()
    now = datetime.now(MADRID_TZ)
    assert _offline(c, "", now).status_code == 422
    assert _offline(c, "x", now, client_id="not-a-uuid").status_code == 422
    assert _offline(c, "x", now + timedelta(days=2)).status_code == 422          # from the future
    assert _offline(c, "x", now - timedelta(days=400)).status_code == 422        # far too old
    body = {"client_id": str(uuid4()), "text": "x", "typed_at": now.isoformat(), "extra": 1}
    assert c.post("/api/tasks/offline", json=body, headers=O).status_code == 422


async def test_client_ids_are_per_user():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    client_id = str(uuid4())
    body = {"client_id": client_id, "text": "mine", "typed_at": datetime.now(MADRID_TZ).isoformat()}
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        theirs = await alice.post("/api/tasks/offline", json=body, headers=O)
        mine = await bob.post("/api/tasks/offline", json=body, headers=O)
        assert (theirs.status_code, mine.status_code) == (201, 201)
        assert theirs.json()["id"] != mine.json()["id"]
        assert [t["title"] for t in (await bob.get("/api/tasks")).json()] == ["mine"]
