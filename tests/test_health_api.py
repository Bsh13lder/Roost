"""``GET /api/health`` — the unauthenticated liveness probe the gateway
container's compose healthcheck polls (``docker-compose.yml``)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.gateway.routes import static as static_module


def test_health_is_ok_without_a_session():
    c = TestClient(create_app())
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_needs_no_origin_header():
    # A healthcheck is a plain GET from inside the container -- no browser,
    # no Origin header, no cookie.
    c = TestClient(create_app())
    r = c.get("/api/health", headers={})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_is_not_shadowed_by_the_spa_mount(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>roost-shell</html>")
    monkeypatch.setattr(static_module, "_web_dist_dir", lambda: Path(dist))
    c = TestClient(create_app())
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_only_answers_get():
    c = TestClient(create_app())
    assert c.post("/api/health").status_code == 405
