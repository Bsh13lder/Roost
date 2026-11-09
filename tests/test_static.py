"""Tests for the SPA static mount — ``roost/gateway/routes/static.py``.

Review finding (Task 12 fix round 1): this module ships with zero
dedicated tests, verified only by an uncommitted ad hoc script. Covers:
dist present -> ``GET /`` and an unknown SPA route both serve
``index.html``; dist absent -> ``mount_static_if_built`` returns
``False`` and ``GET /`` is a plain 404; ``/api/*`` is never shadowed in
either case.

Every test monkeypatches ``_web_dist_dir`` to a ``tmp_path``-based
directory rather than touching the repo's real (gitignored) ``web/dist``
— that directory may or may not exist on a given checkout, and this
suite must not depend on, or disturb, whatever is actually built there.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.gateway.routes import static as static_module


def _built_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>roost-shell</body></html>")
    return dist


def _app_with_dist(monkeypatch, dist_dir: Path) -> FastAPI:
    monkeypatch.setattr(static_module, "_web_dist_dir", lambda: dist_dir)
    return create_app()


# ---------------------------------------------------------------------------
# dist present
# ---------------------------------------------------------------------------


def test_root_serves_index_when_dist_is_built(tmp_path, monkeypatch):
    dist = _built_dist(tmp_path)
    client = TestClient(_app_with_dist(monkeypatch, dist))

    r = client.get("/")

    assert r.status_code == 200
    assert "roost-shell" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_unknown_spa_route_falls_back_to_index(tmp_path, monkeypatch):
    dist = _built_dist(tmp_path)
    client = TestClient(_app_with_dist(monkeypatch, dist))

    r = client.get("/bots/some-fake-id")

    assert r.status_code == 200
    assert "roost-shell" in r.text


def test_api_route_not_shadowed_when_dist_is_built(tmp_path, monkeypatch):
    dist = _built_dist(tmp_path)
    client = TestClient(_app_with_dist(monkeypatch, dist))

    r = client.get("/api/auth/me")

    assert r.status_code == 401
    assert "roost-shell" not in r.text


def test_an_unmatched_api_path_is_still_404_when_dist_is_built(tmp_path, monkeypatch):
    """S1 Task 1 fix round 1, finding 1: a registered route 404s past the
    static mount regardless (the case above), but nothing registered this
    router-less path. ``_SpaStaticFiles.get_response`` used to catch every
    404 and serve ``index.html``, so a deleted route (``/api/roles``) would
    silently come back 200 in production, where ``dist`` is always built."""
    dist = _built_dist(tmp_path)
    client = TestClient(_app_with_dist(monkeypatch, dist))

    r = client.get("/api/nope")

    assert r.status_code == 404
    assert "roost-shell" not in r.text


# ---------------------------------------------------------------------------
# dist absent
# ---------------------------------------------------------------------------


def test_mount_static_if_built_returns_false_when_dist_missing(tmp_path, monkeypatch):
    missing = tmp_path / "dist"  # never created
    monkeypatch.setattr(static_module, "_web_dist_dir", lambda: missing)

    mounted = static_module.mount_static_if_built(FastAPI())

    assert mounted is False


def test_root_is_plain_404_when_dist_missing(tmp_path, monkeypatch):
    missing = tmp_path / "dist"  # never created
    client = TestClient(_app_with_dist(monkeypatch, missing))

    r = client.get("/")

    assert r.status_code == 404


def test_api_route_unaffected_when_dist_missing(tmp_path, monkeypatch):
    missing = tmp_path / "dist"  # never created
    client = TestClient(_app_with_dist(monkeypatch, missing))

    r = client.get("/api/auth/me")

    assert r.status_code == 401


def test_the_spa_never_loads_remote_images(tmp_path, monkeypatch):
    """M2 Task 5: a note's markdown must never make the browser fetch a remote
    image (an exfiltration path for a tainted run's note). The preview draws no
    <img>; this header is the second line of defense."""
    client = TestClient(_app_with_dist(monkeypatch, _built_dist(tmp_path)))
    for path in ("/", "/bots/some-fake-id/board"):
        assert client.get(path).headers["content-security-policy"] == "img-src 'self' data: blob:"
