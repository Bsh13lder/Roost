"""Skill proposals over HTTP (Skills Task 6): Save skill and Not now, 409 on a second press, 404 for others."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.skills.proposals import ProposalRequest
from roost.skills.models import SkillProposalPayload
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PAYLOAD = SkillProposalPayload(name="Post on X", use_when="posting on X", body="1. Open X")


def _client(app) -> tuple[TestClient, str, str]:
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c, c.get("/api/auth/me").json()["id"], c.get("/api/bots").json()[0]["id"]


async def _propose(app, user_id, bot_id, payload=PAYLOAD, action="create", skill=None, tainted=False):
    thread, _ = await app.state.talk.ensure_main_thread(user_id, bot_id)
    return await app.state.skill_proposals.propose(ProposalRequest(
        user_id=user_id, bot_id=bot_id, action=action, payload=payload, thread_id=thread.id, tainted=tainted,
        from_routine=False, skill=skill))


async def test_list_get_save_and_the_skill_exists():
    app = create_app()
    c, user_id, bot = _client(app)
    proposal = await _propose(app, user_id, bot, tainted=True)
    [row] = c.get("/api/skill-proposals?state=open").json()
    assert row["id"] == proposal.id and row["action"] == "create" and row["tainted"] is True
    assert row["payload"] == {"name": "Post on X", "use_when": "posting on X", "body": "1. Open X"}
    assert row["skill_name"] == "Post on X" and row["diff"] == []
    assert c.get(f"/api/skill-proposals/{proposal.id}").json()["state"] == "open"
    saved = c.post(f"/api/skill-proposals/{proposal.id}/save", headers=O)
    assert saved.status_code == 200 and saved.json()["state"] == "saved"
    [skill] = c.get("/api/skills").json()
    assert skill["name"] == "Post on X" and skill["origin"] == "bot" and skill["tainted"] is True
    assert c.get("/api/skill-proposals").json() == []


async def test_saving_twice_is_409_and_decline():
    app = create_app()
    c, user_id, bot = _client(app)
    first = await _propose(app, user_id, bot)
    assert c.post(f"/api/skill-proposals/{first.id}/save", headers=O).status_code == 200
    again = c.post(f"/api/skill-proposals/{first.id}/save", headers=O)
    assert again.status_code == 409 and again.json()["detail"] == "Try again: that proposal was already decided."
    second = await _propose(app, user_id, bot, SkillProposalPayload(name="Other", use_when="w", body="b"))
    declined = c.post(f"/api/skill-proposals/{second.id}/decline", headers=O)
    assert declined.status_code == 200 and declined.json()["state"] == "declined"
    assert c.post(f"/api/skill-proposals/{second.id}/decline", headers=O).status_code == 409


async def test_a_stale_change_is_422_and_stays_open():
    app = create_app()
    c, user_id, bot = _client(app)
    made = c.post("/api/skills", json={"name": "Post on X", "use_when": "posting", "body": "old"}, headers=O).json()
    skill = await app.state.skills.get(user_id, made["id"])
    proposal = await _propose(app, user_id, bot, SkillProposalPayload(body="bot's"), action="change", skill=skill)
    view = c.get(f"/api/skill-proposals/{proposal.id}").json()
    assert view["diff"] == [{"field": "body", "before": "old", "after": "bot's"}]
    c.put(f"/api/skills/{made['id']}", json={"body": "mine", "base_revision": 1}, headers=O)
    stale = c.post(f"/api/skill-proposals/{proposal.id}/save", headers=O)
    assert stale.status_code == 422 and stale.json()["detail"].startswith("That skill changed or is gone")
    assert c.get(f"/api/skill-proposals/{proposal.id}").json()["state"] == "open"
    assert c.get(f"/api/skills/{made['id']}").json()["body"] == "mine"


async def test_a_deleted_skill_takes_its_change_proposals_with_it():
    app = create_app()
    c, user_id, bot = _client(app)
    made = c.post("/api/skills", json={"name": "Post on X", "use_when": "posting", "body": "old"}, headers=O).json()
    skill = await app.state.skills.get(user_id, made["id"])
    proposal = await _propose(app, user_id, bot, SkillProposalPayload(body="new"), action="change", skill=skill)
    c.delete(f"/api/skills/{made['id']}", headers=O)
    assert c.get(f"/api/skill-proposals/{proposal.id}").status_code == 404


async def test_another_users_proposal_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    bot = await make_bot(cfg, alice, "Scout")
    proposal = await _propose(app, alice, bot.id)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as b:
        assert (await b.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"},
                             headers=O)).status_code == 200
        assert (await b.get(f"/api/skill-proposals/{proposal.id}")).status_code == 404
        assert (await b.post(f"/api/skill-proposals/{proposal.id}/save", headers=O)).status_code == 404
        assert (await b.post(f"/api/skill-proposals/{proposal.id}/decline", headers=O)).status_code == 404
        assert (await b.get("/api/skill-proposals")).json() == []


async def test_writes_need_origin():
    app = create_app()
    c, user_id, bot = _client(app)
    proposal = await _propose(app, user_id, bot)
    assert c.post(f"/api/skill-proposals/{proposal.id}/save").status_code == 403
    assert c.post(f"/api/skill-proposals/{proposal.id}/decline").status_code == 403
