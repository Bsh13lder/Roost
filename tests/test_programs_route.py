"""Programs: ``GET /api/bots/{id}/workspace/files`` lists a bot's workspace folder, read-only, for its owner only."""

from __future__ import annotations

import json
import shlex

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user

from roost.desk import DeskUnavailable, ExecResult
from roost.gateway.app import create_app

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _login(client: TestClient, name: str) -> None:
    r = client.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=ORIGIN)
    if r.status_code != 201:
        client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=ORIGIN)


def _bot(client: TestClient) -> str:
    r = client.post("/api/bots", json={"name": "Coder", "job": "codes", "instructions": "", "avatar": AVATAR},
                    headers=ORIGIN)
    assert r.status_code == 201
    return r.json()["id"]


def _desk(app, client, bot_id):
    computer = client.get("/api/bots").json()
    kind = next(b for b in computer if b["id"] == bot_id).get("computer", "mac_brave")
    return app.state.desks.for_bot(bot_id, kind)


def test_lists_a_folder_with_the_fixed_script():
    app = create_app()
    c = TestClient(app)
    _login(c, "alice")
    bot_id = _bot(c)
    desk = _desk(app, c, bot_id)
    listing = {"entries": [{"name": "a.py", "kind": "file", "size": 3}], "more": False}
    desk.exec_replies = (ExecResult(0, json.dumps(listing), "", False, False),)
    r = c.get(f"/api/bots/{bot_id}/workspace/files", params={"path": "src"})
    assert r.status_code == 200
    assert r.json() == {"path": "src", "entries": [{"name": "a.py", "kind": "file", "size": 3}], "more": False}
    inner = shlex.split(desk.exec_calls[0][0][2])
    assert inner[4:6] == ["list", "src"]


def test_bad_paths_missing_folders_and_a_down_workspace():
    app = create_app()
    c = TestClient(app)
    _login(c, "alice")
    bot_id = _bot(c)
    assert c.get(f"/api/bots/{bot_id}/workspace/files", params={"path": "../x"}).status_code == 422
    desk = _desk(app, c, bot_id)
    desk.exec_replies = (ExecResult(3, "", json.dumps({"error": "not_found"}), False, False),)
    r = c.get(f"/api/bots/{bot_id}/workspace/files")
    assert r.status_code == 404 and "no such file" in r.json()["detail"].lower()

    async def down(command, timeout_s=60):
        raise DeskUnavailable("keeper down")

    desk.exec = down
    assert c.get(f"/api/bots/{bot_id}/workspace/files").status_code == 503


async def test_another_users_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN)
    r = await alice.post("/api/bots", json={"name": "Coder", "job": "codes", "instructions": "", "avatar": AVATAR},
                         headers=ORIGIN)
    bot_id = r.json()["id"]
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "bob", "pw-123456")
    bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=ORIGIN)).status_code == 200
    assert (await bob.get(f"/api/bots/{bot_id}/workspace/files")).status_code == 404
    assert (await alice.get(f"/api/bots/{bot_id}/workspace/files")).status_code == 200
    await alice.aclose()
    await bob.aclose()
