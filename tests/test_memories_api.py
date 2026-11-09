"""The /api/memories routes (memory Task 10): the What I remember panel's door."""

from __future__ import annotations

import pytest
import httpx

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.memory.models import MemoryDraft
from roost.memory.store import MemoryStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
SECRET = "my password is hunter2hunter2"


async def _login(app, cfg, username):
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"},
                              headers=O)).status_code == 200
    return client, (await client.get("/api/auth/me")).json()["id"]


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice, alice_id = await _login(app, cfg, "alice")
    bob, bob_id = await _login(app, cfg, "bob")
    scout = await make_bot(cfg, alice_id, "Scout")
    quill = await make_bot(cfg, alice_id, "Quill")
    yield cfg, app, alice, alice_id, bob, bob_id, scout, quill
    await alice.aclose()
    await bob.aclose()


async def _add(client, text, kind="fact", bot=None, **extra):
    body = {"text": text, "kind": kind, **({"bot_id": bot.id} if bot else {}), **extra}
    return await client.post("/api/memories", json=body, headers=O)


async def test_list_shows_about_you_and_that_bots_own(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    await _add(alice, "Ana likes orchids", "about_you")
    await _add(alice, "Short answers", "preference", scout)
    await _add(alice, "Quill's own", "fact", quill)
    rows = (await alice.get("/api/memories", params={"bot_id": scout.id})).json()
    assert sorted(r["text"] for r in rows) == ["Ana likes orchids", "Short answers"]
    assert set(rows[0]) == {"id", "bot_id", "kind", "text", "source", "importance", "pinned", "tainted",
                            "created_at", "updated_at", "last_recalled_at", "archived_at", "tags"}


async def test_add_edit_pin_restore_and_forget(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    created = await _add(alice, "Likes tea", "fact", scout, importance=4)
    assert created.status_code == 201
    memory = created.json()
    assert (memory["source"], memory["tainted"], memory["importance"], memory["bot_id"]) == ("user", False, 4, scout.id)
    again = await _add(alice, "likes tea", "fact", scout)
    assert again.status_code == 201 and again.json()["id"] == memory["id"]

    edited = await alice.patch(f"/api/memories/{memory['id']}", json={"text": "Likes green tea", "pinned": True},
                               headers=O)
    assert edited.status_code == 200
    assert (edited.json()["text"], edited.json()["pinned"], edited.json()["source"]) == ("Likes green tea", True, "user")

    await MemoryStore(cfg).update(uid, memory["id"], archived_at="2026-01-01T00:00:00+00:00")
    restored = await alice.patch(f"/api/memories/{memory['id']}", json={"restore": True}, headers=O)
    assert restored.json()["archived_at"] is None

    assert (await alice.delete(f"/api/memories/{memory['id']}", headers=O)).status_code == 204
    assert (await alice.delete(f"/api/memories/{memory['id']}", headers=O)).status_code == 404


async def test_an_edit_by_the_user_vouches_for_a_tainted_memory(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    saved, _ = await MemoryStore(cfg).upsert(uid, MemoryDraft(
        kind="fact", text="From a web page", bot_id=scout.id, source="bot", created_by_bot=scout.id, tainted=True))
    edited = (await alice.patch(f"/api/memories/{saved.id}", json={"text": "Checked by me"}, headers=O)).json()
    assert (edited["source"], edited["tainted"]) == ("user", False)


async def test_faded_memories_show_only_when_asked(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    memory = (await _add(alice, "Old minor thing", "fact", scout)).json()
    await MemoryStore(cfg).update(uid, memory["id"], archived_at="2026-01-01T00:00:00+00:00")
    assert (await alice.get("/api/memories", params={"bot_id": scout.id})).json() == []
    shown = (await alice.get("/api/memories", params={"bot_id": scout.id, "faded": "true"})).json()
    assert [m["id"] for m in shown] == [memory["id"]]


async def test_a_secret_is_refused_on_add_and_on_edit(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    refused = await _add(alice, SECRET, "fact", scout)
    assert refused.status_code == 422 and "password" in refused.json()["detail"]
    memory = (await _add(alice, "Fine text", "fact", scout)).json()
    edit = await alice.patch(f"/api/memories/{memory['id']}", json={"text": SECRET}, headers=O)
    assert edit.status_code == 422
    assert len((await alice.get("/api/memories", params={"bot_id": scout.id})).json()) == 1


async def test_a_bot_kind_needs_a_bot_and_about_you_ignores_one(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    missing = await _add(alice, "Needs a bot", "preference")
    assert missing.status_code == 422 and missing.json()["detail"] == "Say which bot this memory is for."
    shared = await _add(alice, "Ana is my sister", "about_you", scout)
    assert shared.status_code == 201 and shared.json()["bot_id"] is None
    assert (await _add(alice, "x", "nonsense")).status_code == 422
    assert (await _add(alice, "x", "fact", scout, extra_field=1)).status_code == 422
    assert (await _add(alice, "", "fact", scout)).status_code == 422


async def test_an_edit_onto_an_existing_memory_is_409(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    await _add(alice, "Likes tea", "fact", scout)
    other = (await _add(alice, "Likes coffee", "fact", scout)).json()
    clash = await alice.patch(f"/api/memories/{other['id']}", json={"text": "likes tea"}, headers=O)
    assert clash.status_code == 409 and clash.json()["detail"] == "You already have that memory."


async def test_the_about_you_line_cannot_be_crossed(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    shared = (await _add(alice, "Ana is my sister", "about_you")).json()
    own = (await _add(alice, "Likes tea", "fact", scout)).json()
    into = await alice.patch(f"/api/memories/{own['id']}", json={"kind": "about_you"}, headers=O)
    out = await alice.patch(f"/api/memories/{shared['id']}", json={"kind": "fact"}, headers=O)
    assert into.status_code == 422 and out.status_code == 422
    assert (await alice.patch(f"/api/memories/{own['id']}", json={"kind": "project"}, headers=O)).status_code == 200


async def test_an_empty_patch_is_refused(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    memory = (await _add(alice, "Likes tea", "fact", scout)).json()
    empty = await alice.patch(f"/api/memories/{memory['id']}", json={}, headers=O)
    assert empty.status_code == 422 and "Say what to change." in str(empty.json())


async def test_every_write_needs_the_origin(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    memory = (await _add(alice, "Likes tea", "fact", scout)).json()
    body = {"text": "x", "kind": "fact", "bot_id": scout.id}
    assert (await alice.post("/api/memories", json=body)).status_code == 403
    assert (await alice.patch(f"/api/memories/{memory['id']}", json={"pinned": True})).status_code == 403
    assert (await alice.delete(f"/api/memories/{memory['id']}")).status_code == 403
    assert (await alice.post(f"/api/bots/{scout.id}/chat")).status_code == 403


async def test_every_route_needs_a_login(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    try:
        assert (await anonymous.get("/api/memories", params={"bot_id": scout.id})).status_code == 401
        assert (await anonymous.post("/api/memories", json={"text": "x", "kind": "about_you"}, headers=O)).status_code == 401
        assert (await anonymous.patch("/api/memories/x", json={"pinned": True}, headers=O)).status_code == 401
        assert (await anonymous.delete("/api/memories/x", headers=O)).status_code == 401
        assert (await anonymous.post(f"/api/bots/{scout.id}/chat", headers=O)).status_code == 401
    finally:
        await anonymous.aclose()


async def test_every_write_publishes_memories_changed(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    memory = (await _add(alice, "Likes tea", "fact", scout)).json()
    await alice.patch(f"/api/memories/{memory['id']}", json={"pinned": True}, headers=O)
    await alice.delete(f"/api/memories/{memory['id']}", headers=O)
    frames = [f for f in await app.state.events.since(uid, 0) if f["type"] == "memories_changed"]
    assert [f["change"] for f in frames] == ["created", "updated", "deleted"]
    assert all(f["memory_id"] == memory["id"] and f["bot_id"] == scout.id for f in frames)


async def test_another_users_memories_and_bots_are_404(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    secret = (await _add(alice, "Alice's private fact", "fact", scout)).json()
    listing = await bob.get("/api/memories", params={"bot_id": scout.id})
    assert listing.status_code == 404 and "private" not in listing.text
    patched = await bob.patch(f"/api/memories/{secret['id']}", json={"text": "hijack"}, headers=O)
    deleted = await bob.delete(f"/api/memories/{secret['id']}", headers=O)
    assert patched.status_code == 404 and deleted.status_code == 404
    assert "private" not in patched.text + deleted.text
    posted = await _add(bob, "Sneaky", "fact", scout)
    assert posted.status_code == 422 and posted.json()["detail"] == "No such bot."
    assert (await alice.get("/api/memories", params={"bot_id": scout.id})).json()[0]["text"] == "Alice's private fact"
    assert (await bob.post(f"/api/bots/{scout.id}/chat", headers=O)).status_code == 404


async def test_a_missing_or_overlong_bot_id_is_refused(rig):
    cfg, app, alice, uid, bob, bob_id, scout, quill = rig
    assert (await alice.get("/api/memories")).status_code == 422
    assert (await alice.get("/api/memories", params={"bot_id": "x" * 500})).status_code == 422
