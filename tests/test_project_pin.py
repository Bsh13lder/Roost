"""Pinned projects: PUT /api/projects/{id}/pin (Batch F, G7)."""

from __future__ import annotations

import httpx
import pytest

from roost.config import load_config
from roost.constants import GENERAL_PROJECT_NAME
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore

O = {"Origin": "http://127.0.0.1:18800"}
EVIL = {"Origin": "http://evil.example"}


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            assert (await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"},
                                      headers=O)).status_code == 200
        project = await ProjectStore(cfg).create(alice_id, ProjectDraft(name="Trip"), created_by_bot=None, tainted=False)
        yield app, cfg, alice_id, project, alice, bob


async def test_pin_and_unpin_set_pinned_at(rig):
    app, _, alice_id, project, alice, _ = rig
    pinned = await alice.put(f"/api/projects/{project.id}/pin", json={"pinned": True}, headers=O)
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True and pinned.json()["pinned_at"]
    unpinned = await alice.put(f"/api/projects/{project.id}/pin", json={"pinned": False}, headers=O)
    assert (unpinned.json()["pinned"], unpinned.json()["pinned_at"]) == (False, None)
    changes = [e["change"] for e in await app.state.events.since(alice_id, 0) if e["type"] == "money_changed"]
    assert changes.count("project_updated") == 2


async def test_another_users_project_is_404_and_stays_unpinned(rig):
    _, cfg, alice_id, project, alice, bob = rig
    assert (await bob.put(f"/api/projects/{project.id}/pin", json={"pinned": True}, headers=O)).status_code == 404
    assert (await bob.put("/api/projects/nope/pin", json={"pinned": True}, headers=O)).status_code == 404
    assert (await ProjectStore(cfg).get(alice_id, project.id)).pinned is False


async def test_general_cannot_be_pinned(rig):
    _, cfg, alice_id, _, alice, _ = rig
    general = await ProjectStore(cfg).create(alice_id, ProjectDraft(name=GENERAL_PROJECT_NAME),
                                             created_by_bot=None, tainted=False)
    r = await alice.put(f"/api/projects/{general.id}/pin", json={"pinned": True}, headers=O)
    assert (r.status_code, r.json()["detail"]) == (422, "General can't be pinned.")


async def test_project_out_carries_pinned(rig):
    _, _, _, project, alice, _ = rig
    for url in ("/api/projects", f"/api/projects/{project.id}"):
        body = (await alice.get(url)).json()
        row = body[0] if isinstance(body, list) else body
        assert (row["pinned"], row["pinned_at"]) == (False, None)


async def test_pin_needs_the_origin_header_and_a_strict_bool(rig):
    _, _, _, project, alice, _ = rig
    url = f"/api/projects/{project.id}/pin"
    for headers in ({}, EVIL):
        assert (await alice.put(url, json={"pinned": True}, headers=headers)).status_code == 403
    for body in ({"pinned": "yes"}, {"pinned": 1}, {}, {"pinned": True, "x": 1}):
        assert (await alice.put(url, json=body, headers=O)).status_code == 422
    anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://roost.test")
    async with anon:
        assert (await anon.put(url, json={"pinned": True}, headers=O)).status_code == 401


async def test_pinning_twice_keeps_pinned_at_and_publishes_once(rig):
    app, _, alice_id, project, alice, _ = rig
    first = await alice.put(f"/api/projects/{project.id}/pin", json={"pinned": True}, headers=O)
    again = await alice.put(f"/api/projects/{project.id}/pin", json={"pinned": True}, headers=O)
    assert again.status_code == 200 and again.json()["pinned_at"] == first.json()["pinned_at"]
    changes = [e["change"] for e in await app.state.events.since(alice_id, 0) if e["type"] == "money_changed"]
    assert changes.count("project_updated") == 1
