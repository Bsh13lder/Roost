"""Contract tests for the threads/messages HTTP API —
``roost/gateway/routes/threads.py``.

Per the brief: a thread of another user → 404 on GET/POST messages;
creating a thread on a foreign bot → 404; text over 8000 chars → 422.
``POST /api/threads/{id}/messages`` only stores the message and returns
202 ``{message_id}`` — starting a turn is Task 11's job (here
``app.state.turns`` is the no-op ``NoOpTurnStarter``, see
``roost/gateway/app.py``); this file only asserts the response/storage
side, not that any turn actually started.

Same cross-user pattern as ``tests/test_bots_api.py``: registration
closes after the first account, so a "second user" is created directly
via ``register_user`` then logged in over HTTP with an async client
sharing the app's event loop.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}

VALID_AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _register(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/register", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code in (201, 403)
    if r.status_code == 403:
        client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)


def _create_bot(client: TestClient, name: str = "Scout") -> str:
    body = {"name": name, "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
    r = client.post("/api/bots", json=body, headers=O)
    assert r.status_code == 201
    return r.json()["id"]


async def _async_client_as(app, username: str) -> httpx.AsyncClient:
    """Register ``username`` directly (bypassing the closed-registration
    HTTP gate), then log them in over HTTP on a fresh async client."""
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    r = await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code == 200
    return client


# ---------------------------------------------------------------------------
# POST/GET /api/bots/{bot_id}/threads
# ---------------------------------------------------------------------------

def test_create_thread_201_with_expected_shape():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)

    r = c.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)
    assert r.status_code == 201
    body = r.json()
    assert body["bot_id"] == bot_id
    assert body["kind"] == "chat"
    assert body["title"] is None
    assert set(body) == {"id", "bot_id", "title", "kind", "created_at", "updated_at"}


def test_create_thread_with_title():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)

    r = c.post(f"/api/bots/{bot_id}/threads", json={"title": "Morning check-in"}, headers=O)
    assert r.status_code == 201
    assert r.json()["title"] == "Morning check-in"


def test_create_thread_on_unknown_bot_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots/does-not-exist/threads", json={}, headers=O)
    assert r.status_code == 404


async def test_create_thread_on_foreign_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post(
        "/api/bots", json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}, headers=O,
    )).json()["id"]

    bob = await _async_client_as(app, "bob")
    r = await bob.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)
    assert r.status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_create_thread_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/threads", json={}, headers=BAD_O)
    assert r.status_code == 403


def test_list_threads_shows_only_that_bots_threads_in_order():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    c.post(f"/api/bots/{bot_id}/threads", json={"title": "T1"}, headers=O)
    c.post(f"/api/bots/{bot_id}/threads", json={"title": "T2"}, headers=O)

    r = c.get(f"/api/bots/{bot_id}/threads")
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T1", "T2"]


async def test_list_threads_on_foreign_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post(
        "/api/bots", json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}, headers=O,
    )).json()["id"]

    bob = await _async_client_as(app, "bob")
    r = await bob.get(f"/api/bots/{bot_id}/threads")
    assert r.status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_threads_routes_require_auth():
    c = TestClient(create_app())
    assert c.get("/api/bots/some-id/threads").status_code == 401
    assert c.post("/api/bots/some-id/threads", json={}, headers=O).status_code == 401


# ---------------------------------------------------------------------------
# GET/POST /api/threads/{thread_id}/messages
# ---------------------------------------------------------------------------

def _create_thread(client: TestClient, bot_id: str) -> str:
    return client.post(f"/api/bots/{bot_id}/threads", json={}, headers=O).json()["id"]


def test_post_message_202_and_message_is_stored():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))

    r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "hello"}, headers=O)
    assert r.status_code == 202
    assert set(r.json()) == {"message_id", "status", "queued", "mentioned"}

    messages = c.get(f"/api/threads/{thread_id}/messages").json()
    assert len(messages) == 1
    assert messages[0]["id"] == r.json()["message_id"]
    assert messages[0]["body"] == "hello"
    assert messages[0]["role"] == "user"
    assert messages[0]["seq"] == 1
    assert messages[0]["tainted"] is False
    assert messages[0]["thread_id"] == thread_id


def test_get_messages_after_seq_pages():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    for i in range(3):
        c.post(f"/api/threads/{thread_id}/messages", json={"text": f"msg {i}"}, headers=O)

    all_messages = c.get(f"/api/threads/{thread_id}/messages").json()
    assert [m["seq"] for m in all_messages] == [1, 2, 3]

    after_1 = c.get(f"/api/threads/{thread_id}/messages?after=1").json()
    assert [m["seq"] for m in after_1] == [2, 3]


def test_get_messages_with_no_after_returns_the_latest_page_once_over_the_limit(monkeypatch):
    """Final review, finding 8: ``after=0`` (the default/omitted case)
    must mean "the latest page", not "the oldest page" -- a reload of
    Talk otherwise never shows anything posted after the thread's first
    ``DEFAULT_MESSAGE_PAGE_LIMIT`` messages."""
    import roost.talk.store as store_module

    monkeypatch.setattr(store_module, "DEFAULT_MESSAGE_PAGE_LIMIT", 2)

    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    for i in range(3):
        c.post(f"/api/threads/{thread_id}/messages", json={"text": f"msg {i}"}, headers=O)

    messages = c.get(f"/api/threads/{thread_id}/messages").json()
    assert [m["seq"] for m in messages] == [2, 3]


def test_post_message_text_too_long_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "x" * 8001}, headers=O)
    assert r.status_code == 422


def test_post_message_empty_text_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    r = c.post(f"/api/threads/{thread_id}/messages", json={"text": ""}, headers=O)
    assert r.status_code == 422


def test_post_message_exactly_8000_chars_is_202():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "x" * 8000}, headers=O)
    assert r.status_code == 202


def test_post_message_on_unknown_thread_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/threads/does-not-exist/messages", json={"text": "hi"}, headers=O)
    assert r.status_code == 404


def test_get_messages_on_unknown_thread_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    assert c.get("/api/threads/does-not-exist/messages").status_code == 404


async def test_foreign_thread_is_404_on_get_and_post_messages():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post(
        "/api/bots", json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}, headers=O,
    )).json()["id"]
    thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "alice's secret"}, headers=O)

    bob = await _async_client_as(app, "bob")

    assert (await bob.get(f"/api/threads/{thread_id}/messages")).status_code == 404
    assert (await bob.post(f"/api/threads/{thread_id}/messages", json={"text": "hijack"}, headers=O)).status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_post_message_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    thread_id = _create_thread(c, _create_bot(c))
    r = c.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=BAD_O)
    assert r.status_code == 403


def test_messages_routes_require_auth():
    c = TestClient(create_app())
    assert c.get("/api/threads/some-id/messages").status_code == 401
    assert c.post("/api/threads/some-id/messages", json={"text": "hi"}, headers=O).status_code == 401


async def test_posting_a_message_queues_a_work_item_for_the_threads_bot():
    app = create_app()
    client = await _async_client_as(app, "alice")
    body = {"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR}
    bot_id = (await client.post("/api/bots", json=body, headers=O)).json()["id"]
    thread_id = (await client.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]

    r = await client.post(f"/api/threads/{thread_id}/messages", json={"text": "hello"}, headers=O)

    assert r.status_code == 202
    async with db_session(load_config()) as db:
        rows = await (await db.execute(
            "SELECT bot_id, kind, message_id FROM work_items WHERE thread_id = ?", (thread_id,),
        )).fetchall()
    assert [(row["bot_id"], row["kind"], row["message_id"]) for row in rows] == [
        (bot_id, "message", r.json()["message_id"]),
    ]
    await wait_idle(app.state.turns)
    await client.aclose()
