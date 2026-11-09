"""Contract tests for the desk HTTP API —
``roost/gateway/routes/desk.py``.

Per the brief: a second user's bot -> 404 on every desk route; keeper
down -> 503 ``{"detail": "desk unavailable"}``; ``exec`` with
``{"command": "echo hi"}`` passes ``["/bin/sh", "-c", "echo hi"]`` with
``timeout_s=120`` to the keeper (``FakeDesk`` records it); missing
Origin -> 403.

``app.state.desks`` is already a ``DeskFactory`` in ``desk_mode="fake"``
(forced session-wide by ``tests/conftest.py``), so every test below goes
through the real ``DeskFactory.for_bot`` -> real ``FakeDesk`` path except
where a test swaps in its own stub factory to force ``DeskUnavailable``.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.desk.fake import FakeDesk
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
# Fix round 1, finding 2: every BAD_O case above sends a *wrong* Origin.
# A request with no Origin header at all is a distinct case the brief
# itself lists ("missing Origin -> 403") -- require_origin treats it the
# same as a disallowed one (roost/gateway/origin.py), but nothing here
# exercised that path until now.
NO_ORIGIN: dict[str, str] = {}

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
    bot_id = r.json()["id"]
    # these tests cover the Mac Brave desk; new bots default to the Linux computer
    assert client.patch(f"/api/bots/{bot_id}", json={"computer": "mac_brave"}, headers=O).status_code == 200
    return bot_id


async def _async_client_as(app, username: str) -> httpx.AsyncClient:
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    r = await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code == 200
    return client


class _StubDeskFactory:
    """Hands out one fixed ``Desk`` (real or unavailable) for every bot
    id — used to exercise the routes' own error handling in isolation
    from ``DeskFactory``'s per-bot caching."""

    def __init__(self, desk) -> None:
        self._desk = desk

    def for_bot(self, bot_id: str, computer: str = "mac_brave"):
        return self._desk


# ---------------------------------------------------------------------------
# GET /api/bots/{bot_id}/desk
# ---------------------------------------------------------------------------


def test_get_desk_status_default_shape():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)

    r = c.get(f"/api/bots/{bot_id}/desk")
    assert r.status_code == 200
    assert r.json() == {"browser": "stopped", "workspace": "absent", "computer": "mac_brave", "state": None}


def test_get_desk_on_unknown_bot_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    assert c.get("/api/bots/does-not-exist/desk").status_code == 404


async def test_get_desk_on_foreign_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (
        await alice.post(
            "/api/bots",
            json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR},
            headers=O,
        )
    ).json()["id"]

    bob = await _async_client_as(app, "bob")
    assert (await bob.get(f"/api/bots/{bot_id}/desk")).status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_desk_routes_require_auth():
    c = TestClient(create_app())
    assert c.get("/api/bots/some-id/desk").status_code == 401
    assert c.post("/api/bots/some-id/desk/browser/start", headers=O).status_code == 401
    assert c.post("/api/bots/some-id/desk/browser/stop", headers=O).status_code == 401
    assert c.post("/api/bots/some-id/desk/workspace/exec", json={"command": "echo hi"}, headers=O).status_code == 401


# ---------------------------------------------------------------------------
# POST /api/bots/{bot_id}/desk/browser/start · /stop
# ---------------------------------------------------------------------------


def test_start_browser_returns_running_status():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)

    r = c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    assert r.status_code == 200
    assert r.json() == {"browser": "running", "workspace": "absent", "computer": "mac_brave", "state": None}


def test_stop_browser_returns_stopped_status():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)

    r = c.post(f"/api/bots/{bot_id}/desk/browser/stop", headers=O)
    assert r.status_code == 200
    assert r.json()["browser"] == "stopped"


def test_start_browser_on_unknown_bot_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    assert c.post("/api/bots/does-not-exist/desk/browser/start", headers=O).status_code == 404


async def test_browser_start_and_stop_on_foreign_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (
        await alice.post(
            "/api/bots",
            json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR},
            headers=O,
        )
    ).json()["id"]

    bob = await _async_client_as(app, "bob")
    assert (await bob.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)).status_code == 404
    assert (await bob.post(f"/api/bots/{bot_id}/desk/browser/stop", headers=O)).status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_start_browser_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=BAD_O)
    assert r.status_code == 403


def test_stop_browser_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/browser/stop", headers=BAD_O)
    assert r.status_code == 403


def test_start_browser_with_no_origin_header_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=NO_ORIGIN)
    assert r.status_code == 403


def test_stop_browser_with_no_origin_header_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/browser/stop", headers=NO_ORIGIN)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/bots/{bot_id}/desk/workspace/exec
# ---------------------------------------------------------------------------


def test_exec_passes_the_exact_shell_argv_and_fixed_timeout_to_the_keeper():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = _create_bot(c)

    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"}, headers=O)
    assert r.status_code == 200
    assert set(r.json()) == {"exit_code", "stdout", "stderr", "timed_out", "truncated"}

    desk = app.state.desks.for_bot(bot_id)
    assert isinstance(desk, FakeDesk)
    assert desk.exec_calls == [(["/bin/sh", "-c", "echo hi"], 120)]


def test_exec_on_unknown_bot_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots/does-not-exist/desk/workspace/exec", json={"command": "echo hi"}, headers=O)
    assert r.status_code == 404


async def test_exec_on_foreign_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (
        await alice.post(
            "/api/bots",
            json={"name": "Scout", "job": "read news", "instructions": "", "avatar": VALID_AVATAR},
            headers=O,
        )
    ).json()["id"]

    bob = await _async_client_as(app, "bob")
    r = await bob.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"}, headers=O)
    assert r.status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_exec_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"}, headers=BAD_O)
    assert r.status_code == 403


def test_exec_with_no_origin_header_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"}, headers=NO_ORIGIN)
    assert r.status_code == 403


def test_exec_empty_command_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": ""}, headers=O)
    assert r.status_code == 422


def test_exec_command_over_2000_chars_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = _create_bot(c)
    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "x" * 2001}, headers=O)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Keeper down -> 503 on every route
# ---------------------------------------------------------------------------


def test_status_when_keeper_unavailable_is_503():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = _create_bot(c)
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    r = c.get(f"/api/bots/{bot_id}/desk")
    assert r.status_code == 503
    assert r.json() == {"detail": "desk unavailable"}


def test_start_browser_when_keeper_unavailable_is_503():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = _create_bot(c)
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    r = c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    assert r.status_code == 503
    assert r.json()["detail"] == "desk unavailable"


def test_stop_browser_when_keeper_unavailable_is_503():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = _create_bot(c)
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    r = c.post(f"/api/bots/{bot_id}/desk/browser/stop", headers=O)
    assert r.status_code == 503
    assert r.json()["detail"] == "desk unavailable"


def test_exec_when_keeper_unavailable_is_503():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = _create_bot(c)
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    r = c.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"}, headers=O)
    assert r.status_code == 503
    assert r.json()["detail"] == "desk unavailable"


# ---------------------------------------------------------------------------
# app.state.desks wiring
# ---------------------------------------------------------------------------


def test_app_state_desks_is_a_desk_factory():
    app = create_app()
    assert isinstance(app.state.desks, DeskFactory)


def test_forget_drops_the_cached_desk_so_for_bot_builds_a_fresh_one():
    """Final review, finding 5: ``delete_bot`` calls this right after
    retiring a bot's desk, so nothing in this process can go on reusing
    a ``Desk`` instance for a bot id that's already gone."""
    factory = DeskFactory(load_config())
    first = factory.for_bot("bot-x")

    factory.forget("bot-x")

    second = factory.for_bot("bot-x")
    assert first is not second


def test_forget_an_unknown_bot_id_is_a_safe_no_op():
    factory = DeskFactory(load_config())
    factory.forget("never-existed")  # must not raise
