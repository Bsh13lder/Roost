"""Skills over HTTP (Skills Task 3): add, edit with revision checks, delete, and switch per bot."""

from __future__ import annotations

import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
SKILL = {"name": "Post on X", "use_when": "the user wants a post on X", "body": "1. Open X\n2. Write it"}


def _client(name="alice", app=None) -> tuple[TestClient, str]:
    c = TestClient(app or create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201
    return c, c.get("/api/bots").json()[0]["id"]


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def _add(c, **fields):
    r = c.post("/api/skills", json=SKILL | fields, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


def _second_bot(c) -> str:
    r = c.post("/api/bots", json={"name": "Ledger", "job": "keeps the books", "instructions": "",
                                  "avatar": {"shape": "mochi", "color": "#22c55e"}}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_add_list_get_edit_delete():
    c, _ = _client()
    made = _add(c)
    assert (made["name"], made["origin"], made["tainted"], made["revision"]) == ("Post on X", "user", False, 1)
    assert [s["id"] for s in c.get("/api/skills").json()] == [made["id"]]
    assert c.get(f"/api/skills/{made['id']}").json()["body"] == SKILL["body"]
    saved = c.put(f"/api/skills/{made['id']}", json={"body": "New steps", "base_revision": 1}, headers=O)
    assert saved.status_code == 200 and saved.json()["body"] == "New steps" and saved.json()["revision"] == 2
    assert c.delete(f"/api/skills/{made['id']}", headers=O).status_code == 204
    assert c.get(f"/api/skills/{made['id']}").status_code == 404
    assert c.delete(f"/api/skills/{made['id']}", headers=O).status_code == 404


def test_a_taken_name_is_422():
    c, _ = _client()
    _add(c)
    r = c.post("/api/skills", json=SKILL | {"name": "post on x"}, headers=O)
    assert r.status_code == 422 and r.json()["detail"] == "There is already a skill called “Post on X”."
    r = c.post("/api/skills", json=SKILL | {"name": "two\nlines"}, headers=O)
    assert r.status_code == 422 and "one line" in r.json()["detail"]


def test_a_stale_save_is_409_with_the_current_copy():
    c, _ = _client()
    made = _add(c)
    assert c.put(f"/api/skills/{made['id']}", json={"body": "one", "base_revision": 1}, headers=O).status_code == 200
    stale = c.put(f"/api/skills/{made['id']}", json={"body": "two", "base_revision": 1}, headers=O)
    assert stale.status_code == 409
    assert stale.json()["detail"] == "This skill changed since you opened it."
    assert stale.json()["current"]["body"] == "one" and stale.json()["current"]["revision"] == 2


async def test_the_users_save_clears_the_web_mark():
    app = create_app()
    c, _ = _client(app=app)
    made = _add(c)
    user_id = c.get("/api/auth/me").json()["id"]
    store = app.state.skills.store
    from roost.skills.models import SkillPatch
    await store.update(user_id, made["id"], SkillPatch(), base_revision=1, tainted=True)
    assert c.get(f"/api/skills/{made['id']}").json()["tainted"] is True
    saved = c.put(f"/api/skills/{made['id']}", json={"base_revision": 2}, headers=O).json()
    assert saved["tainted"] is False and saved["origin"] == "user"


def test_a_secret_is_refused_without_echoing_it():
    c, _ = _client()
    secret = "sk-ant-abcdefghijklmnopqrstuv0123"
    r = c.post("/api/skills", json=SKILL | {"body": f"Use the key {secret}"}, headers=O)
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Not saved: an API key or token seems to be in the steps.")
    assert secret not in r.text
    made = _add(c)
    r = c.put(f"/api/skills/{made['id']}", json={"use_when": f"token={secret}", "base_revision": 1}, headers=O)
    assert r.status_code == 422 and secret not in r.text


def test_list_with_bot_id_shows_on():
    c, bot = _client()
    made = _add(c)
    rows = c.get(f"/api/skills?bot_id={bot}").json()
    assert rows[0]["id"] == made["id"] and rows[0]["on"] is True
    assert "on" not in c.get("/api/skills").json()[0]


def test_switch_off_for_one_bot_only():
    c, bot = _client()
    other = _second_bot(c)
    made = _add(c)
    r = c.put(f"/api/bots/{bot}/skills/{made['id']}", json={"on": False}, headers=O)
    assert r.status_code == 200 and r.json() == {"on": False}
    assert c.get(f"/api/skills?bot_id={bot}").json()[0]["on"] is False
    assert c.get(f"/api/skills?bot_id={other}").json()[0]["on"] is True
    assert c.put(f"/api/bots/{bot}/skills/{made['id']}", json={"on": True}, headers=O).json() == {"on": True}
    assert c.get(f"/api/skills?bot_id={bot}").json()[0]["on"] is True


async def test_another_users_skill_and_bot_are_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    bob_id = (await register_user(cfg, "bob", "pw-123456")).id
    alice_bot, bob_bot = (await make_bot(cfg, alice_id, "Scout")).id, (await make_bot(cfg, bob_id, "Ledger")).id
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as a, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as b:
        for client, name in ((a, "alice"), (b, "bob")):
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
            assert login.status_code == 200
        sid = (await a.post("/api/skills", json=SKILL, headers=O)).json()["id"]
        assert (await b.get(f"/api/skills/{sid}")).status_code == 404
        assert (await b.put(f"/api/skills/{sid}", json={"body": "x", "base_revision": 1}, headers=O)).status_code == 404
        assert (await b.delete(f"/api/skills/{sid}", headers=O)).status_code == 404
        assert (await b.put(f"/api/bots/{bob_bot}/skills/{sid}", json={"on": False}, headers=O)).status_code == 404
        assert (await b.put(f"/api/bots/{alice_bot}/skills/{sid}", json={"on": False}, headers=O)).status_code == 404
        assert (await b.get(f"/api/skills?bot_id={alice_bot}")).status_code == 404
        assert (await b.get("/api/skills")).json() == []
        assert (await a.get(f"/api/skills/{sid}")).json()["body"] == SKILL["body"]


def test_writes_need_origin():
    c, bot = _client()
    made = _add(c)
    assert c.post("/api/skills", json=SKILL | {"name": "Other"}).status_code == 403
    assert c.put(f"/api/skills/{made['id']}", json={"body": "x", "base_revision": 1}).status_code == 403
    assert c.delete(f"/api/skills/{made['id']}").status_code == 403
    assert c.put(f"/api/bots/{bot}/skills/{made['id']}", json={"on": False}).status_code == 403


def test_bodies_refuse_unknown_fields():
    c, _ = _client()
    assert c.post("/api/skills", json=SKILL | {"tainted": False}, headers=O).status_code == 422
    made = _add(c)
    r = c.put(f"/api/skills/{made['id']}", json={"origin": "bot", "base_revision": 1}, headers=O)
    assert r.status_code == 422


def test_skills_changed_is_published():
    c, bot = _client()
    made = _add(c)
    c.put(f"/api/bots/{bot}/skills/{made['id']}", json={"on": False}, headers=O)
    assert _frames().count("skills_changed") == 2
