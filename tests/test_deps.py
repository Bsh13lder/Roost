"""Tests for ``roost/gateway/deps.py`` — the shared dependency aliases.

Night-1's only router (auth) doesn't need these (its routes predate and
bootstrap the session/origin machinery deps.py wraps), but every later
router (bots, threads, desk, events) is expected to import ``CurrentUser``
/ ``RequireOrigin`` from here instead of reaching into
``roost.gateway.auth`` / ``roost.gateway.origin`` directly. Mount them on
a throwaway route to prove the aliases actually wire up, rather than
leaving deps.py untested until a later task happens to use it.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from roost.gateway.auth import create_session, register_user
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.db.connection import init_db


def _probe_app(config):
    app = FastAPI()
    app.state.config = config

    @app.get("/whoami")
    async def whoami(user: CurrentUser):
        return {"id": user.id, "username": user.username}

    @app.post("/echo", dependencies=[RequireOrigin])
    async def echo():
        return {"ok": True}

    return app


async def test_current_user_dependency_resolves_from_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    from roost.config import load_config

    config = load_config()
    await init_db(config)
    user = await register_user(config, "alice", "pw-123456")
    session_id = await create_session(config, user.id)

    app = _probe_app(config)
    client = TestClient(app)
    client.cookies.set("roost_session", session_id)

    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json() == {"id": user.id, "username": "alice"}


async def test_current_user_dependency_401s_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    from roost.config import load_config

    config = load_config()
    await init_db(config)
    app = _probe_app(config)
    client = TestClient(app)

    assert client.get("/whoami").status_code == 401


def test_require_origin_dependency_allows_configured_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    from roost.config import load_config

    config = load_config()
    app = _probe_app(config)
    client = TestClient(app)

    r = client.post("/echo", headers={"Origin": "http://127.0.0.1:18800"})
    assert r.status_code == 200


def test_require_origin_dependency_blocks_other_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    from roost.config import load_config

    config = load_config()
    app = _probe_app(config)
    client = TestClient(app)

    r = client.post("/echo", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
