"""The instructions card over HTTP: Accept (with or without your edit) and Decline, 409 on a second press, 422 when
stale, 404 for another user's card."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.instruction_proposals.models import ProposalRequest

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
NEW = "## What you do\n\nPlan the week every Monday."


def _client(app) -> tuple[TestClient, str, str]:
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                  headers=ORIGIN).status_code == 201
    return c, c.get("/api/auth/me").json()["id"], c.get("/api/bots").json()[0]["id"]


async def _propose(app, user_id, bot_id, text=NEW, tainted=False):
    thread, _ = await app.state.talk.ensure_main_thread(user_id, bot_id)
    return await app.state.instruction_proposals.propose(ProposalRequest(
        user_id=user_id, bot_id=bot_id, new_text=text, why="You plan on Mondays.", thread_id=thread.id,
        tainted=tainted, from_routine=False))


async def test_list_get_and_accept_writes_the_instructions():
    app = create_app()
    c, user_id, bot_id = _client(app)
    before = c.get(f"/api/bots/{bot_id}").json()["instructions"]
    proposal = await _propose(app, user_id, bot_id, tainted=True)
    [row] = c.get("/api/instruction-proposals?state=open").json()
    assert row["id"] == proposal.id and row["bot_id"] == bot_id and row["tainted"] is True
    assert row["before"] == before and "Plan the week every Monday." in row["after"]
    assert row["why"] == "You plan on Mondays." and row["stale"] is False and row["state"] == "open"
    assert {"op": "add", "text": "Plan the week every Monday."} in row["diff"]
    assert c.get(f"/api/instruction-proposals/{proposal.id}").json()["id"] == proposal.id
    r = c.post(f"/api/instruction-proposals/{proposal.id}/accept", json={}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "accepted"
    assert c.get(f"/api/bots/{bot_id}").json()["instructions"] == row["after"]
    assert c.get("/api/instruction-proposals").json() == []
    again = c.post(f"/api/instruction-proposals/{proposal.id}/accept", json={}, headers=ORIGIN)
    assert again.status_code == 409


async def test_accept_with_an_edit_and_decline():
    app = create_app()
    c, user_id, bot_id = _client(app)
    first = await _propose(app, user_id, bot_id)
    r = c.post(f"/api/instruction-proposals/{first.id}/accept", json={"text": "My words."}, headers=ORIGIN)
    assert r.status_code == 200 and c.get(f"/api/bots/{bot_id}").json()["instructions"] == "My words."
    second = await _propose(app, user_id, bot_id)
    d = c.post(f"/api/instruction-proposals/{second.id}/decline", headers=ORIGIN)
    assert d.status_code == 200 and d.json()["state"] == "declined"
    assert c.get(f"/api/bots/{bot_id}").json()["instructions"] == "My words."


async def test_stale_is_422_and_bad_edits_are_422():
    app = create_app()
    c, user_id, bot_id = _client(app)
    proposal = await _propose(app, user_id, bot_id)
    for bad in ({"text": ""}, {"text": "x" * 4001}, {"other": 1}):
        r = c.post(f"/api/instruction-proposals/{proposal.id}/accept", json=bad, headers=ORIGIN)
        assert r.status_code == 422
    c.patch(f"/api/bots/{bot_id}", json={"instructions": "Changed by me."}, headers=ORIGIN)
    r = c.post(f"/api/instruction-proposals/{proposal.id}/accept", json={}, headers=ORIGIN)
    assert r.status_code == 422 and r.json()["detail"].startswith("Your bot's instructions changed")
    assert c.get(f"/api/instruction-proposals/{proposal.id}").json()["state"] == "open"


async def test_writes_need_the_origin():
    app = create_app()
    c, user_id, bot_id = _client(app)
    proposal = await _propose(app, user_id, bot_id)
    r = c.post(f"/api/instruction-proposals/{proposal.id}/decline", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


async def test_another_users_card_is_404():
    app = create_app()
    _, user_id, bot_id = _client(app)
    proposal = await _propose(app, user_id, bot_id)
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "bob", "pw-123456")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as bob:
        assert (await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"},
                               headers=ORIGIN)).status_code == 200
        assert (await bob.get(f"/api/instruction-proposals/{proposal.id}")).status_code == 404
        for action in ("accept", "decline"):
            r = await bob.post(f"/api/instruction-proposals/{proposal.id}/{action}", json={}, headers=ORIGIN)
            assert r.status_code == 404
        assert (await bob.get("/api/instruction-proposals")).json() == []
