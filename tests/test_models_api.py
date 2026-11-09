"""``PUT /api/bots/{id}/model``, ``GET /api/models`` and the notice dismissal."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.registry import BOT_MODELS, DEFAULT_BOT_MODEL, EFFORTS, HAIKU, OPUS, SONNET

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client_with_bot():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    r = c.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "", "avatar": AVATAR}, headers=O)
    return c, r.json()["id"]


def test_put_model_saves_and_publishes_bot_updated():
    c, bot_id = _client_with_bot()
    r = c.put(f"/api/bots/{bot_id}/model", json={"model": OPUS.id, "effort": "max"}, headers=O)
    assert r.status_code == 200
    body = r.json()
    assert (body["model"], body["model_label"], body["effort"]) == (OPUS.id, OPUS.label, "max")
    assert c.get(f"/api/bots/{bot_id}").json()["model"] == OPUS.id
    cleared = c.put(f"/api/bots/{bot_id}/model", json={"model": None, "effort": None}, headers=O).json()
    assert (cleared["model"], cleared["effort"]) == (DEFAULT_BOT_MODEL, None)
    assert cleared["model_override"] is None


def test_put_model_publishes_a_bot_updated_event():
    app = create_app()
    c = TestClient(app)
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = c.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "", "avatar": AVATAR},
                    headers=O).json()["id"]
    published = []

    async def fake_publish(user_id, frame):
        published.append(frame)

    app.state.events.publish = fake_publish
    c.put(f"/api/bots/{bot_id}/model", json={"model": SONNET.id, "effort": "low"}, headers=O)
    assert [f["type"] for f in published] == ["bot_updated"]
    assert published[0]["bot"]["effort"] == "low"


def test_a_bad_model_or_effort_is_422():
    c, bot_id = _client_with_bot()
    for body in (
        {"model": "claude-nope-1", "effort": None},
        {"model": "claude-nope-1", "effort": None},
        {"model": OPUS.id, "effort": "xhigh"},
        {"model": OPUS.id, "effort": None, "extra": 1},
    ):
        assert c.put(f"/api/bots/{bot_id}/model", json=body, headers=O).status_code == 422
    assert c.get(f"/api/bots/{bot_id}").json()["model_override"] is None


async def test_another_users_bot_is_404_and_a_bad_model_is_422():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "alice", "pw-123456")
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        bot_id = (await alice.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "",
                                                       "avatar": AVATAR}, headers=O)).json()["id"]
        assert (await bob.put(f"/api/bots/{bot_id}/model", json={"model": OPUS.id, "effort": None},
                              headers=O)).status_code == 404
        assert (await alice.put(f"/api/bots/{bot_id}/model", json={"model": "claude-nope-1", "effort": None},
                                headers=O)).status_code == 422
        assert (await alice.get(f"/api/bots/{bot_id}")).json()["model_override"] is None


def test_put_model_needs_the_origin_and_a_login():
    c, bot_id = _client_with_bot()
    assert c.put(f"/api/bots/{bot_id}/model", json={"model": OPUS.id, "effort": None}, headers=BAD_O).status_code == 403
    assert TestClient(create_app()).put(f"/api/bots/{bot_id}/model", json={"model": None, "effort": None},
                                        headers=O).status_code == 401
    assert TestClient(create_app()).get("/api/models").status_code == 401


def test_models_lists_bot_choices_then_seen_ones_marked_new():
    app = create_app()
    c = TestClient(app)
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    first = c.get("/api/models").json()
    assert [x["id"] for x in first["choices"]] == [m.id for m in BOT_MODELS]
    assert not any(x["new"] for x in first["choices"])
    assert first["efforts"] == list(EFFORTS) and first["default_model"] == DEFAULT_BOT_MODEL
    assert first["notice"] is None and first["default_effort"][SONNET.id] == "high"

    import asyncio
    asyncio.run(app.state.seen_models.add_new({"claude-new-9": "New 9"}))
    second = c.get("/api/models").json()
    assert second["choices"][-1] == {"id": "claude-new-9", "label": "New 9", "line": "new", "new": True}
    assert second["notice"] == {"id": "claude-new-9", "label": "New 9"}
    assert c.post("/api/models/notice/claude-new-9/dismiss", headers=BAD_O).status_code == 403
    assert c.post("/api/models/notice/claude-new-9/dismiss", headers=O).status_code == 204
    third = c.get("/api/models").json()
    assert third["notice"] is None and third["choices"][-1]["id"] == "claude-new-9"

    # A seen model can be picked.
    bot_id = c.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "", "avatar": AVATAR},
                    headers=O).json()["id"]
    assert c.put(f"/api/bots/{bot_id}/model", json={"model": "claude-new-9", "effort": None},
                 headers=O).json()["model_label"] == "New 9"


async def test_haiku_is_a_bot_model_you_can_pick():
    from roost.models_check.store import SeenModelStore
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "alice", "pw-123456")
    await SeenModelStore(cfg).add_new({HAIKU.id: HAIKU.label})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as alice:
        await alice.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
        bot_id = (await alice.post("/api/bots", json={"name": "Scout", "job": "j", "instructions": "",
                                                       "avatar": AVATAR}, headers=O)).json()["id"]
        r = await alice.put(f"/api/bots/{bot_id}/model", json={"model": HAIKU.id, "effort": None}, headers=O)
        assert r.status_code == 200 and r.json()["model"] == HAIKU.id
        listed = (await alice.get("/api/models")).json()["choices"]
        assert [c["id"] for c in listed].count(HAIKU.id) == 1
