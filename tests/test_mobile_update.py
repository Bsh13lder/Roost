"""In-app update (app restructure slice 2): the gateway serves the newest phone app.

``GET /api/mobile/latest`` returns ``latest.json`` from the mobile dir (written by ``scripts/publish_mobile.sh``),
and ``GET /api/mobile/apk/{file}`` streams one APK whose name matches the versioned pattern. Both need a
session; anything else is a plain 404 (no path traversal, no listing)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.mobile_update.release import apk_path, read_latest

O = {"Origin": "http://127.0.0.1:18800"}
APK = b"PK\x03\x04 fake apk bytes"
NAME = "roost-1.0.1+2.apk"


def _publish(folder: Path, name: str = NAME, data: bytes = APK, **over) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    latest = {"version": "1.0.1", "build": 2, "file": name,
              "sha256": hashlib.sha256(data).hexdigest(), "notes": "Update check inside the app"}
    latest.update(over)
    (folder / "latest.json").write_text(json.dumps(latest))
    return latest


@pytest.fixture
def mobile_dir(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "mobile"
    monkeypatch.setenv("ROOST_MOBILE_DIR", str(folder))
    return folder


@pytest.fixture
async def client(mobile_dir):
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    await register_user(cfg, "alice", "pw-123456")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await http.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
    yield http
    await http.aclose()


# --- the release reader ---------------------------------------------------------------------------------------

def test_read_latest_returns_none_when_nothing_is_published(tmp_path):
    assert read_latest(tmp_path / "missing") is None
    assert read_latest(tmp_path) is None


def test_read_latest_reads_a_valid_file(tmp_path):
    latest = _publish(tmp_path)
    release = read_latest(tmp_path)
    assert release is not None and release.model_dump() == latest


@pytest.mark.parametrize("over", [
    {"version": "1.0"}, {"version": "../1.0.1"}, {"build": 0}, {"build": "2"},
    {"file": "../etc/passwd"}, {"file": "roost-1.0.2+3.apk"}, {"sha256": "abc"}, {"notes": "x" * 500},
    {"extra": 1},
])
def test_read_latest_refuses_a_bad_file(tmp_path, over):
    _publish(tmp_path, **over)
    assert read_latest(tmp_path) is None


def test_read_latest_refuses_broken_json(tmp_path):
    (tmp_path / "latest.json").write_text("{nope")
    assert read_latest(tmp_path) is None


@pytest.mark.parametrize("name", ["../roost-1.0.1+2.apk", "roost-1.0.1+2.apk/", "roost-1.0.1.apk",
                                  "latest.json", "roost-a+2.apk", "roost-1.0.1+2.apk.bak", ""])
def test_apk_path_refuses_any_other_name(tmp_path, name):
    _publish(tmp_path)
    assert apk_path(tmp_path, name) is None


def test_apk_path_finds_a_published_file_only(tmp_path):
    _publish(tmp_path)
    assert apk_path(tmp_path, NAME) == tmp_path / NAME
    assert apk_path(tmp_path, "roost-9.9.9+99.apk") is None


def test_apk_path_refuses_a_symlink(tmp_path):
    outside = tmp_path / "outside.apk"
    outside.write_bytes(APK)
    folder = tmp_path / "mobile"
    folder.mkdir()
    (folder / NAME).symlink_to(outside)
    assert apk_path(folder, NAME) is None


# --- the routes ------------------------------------------------------------------------------------------------

async def test_latest_is_a_plain_404_when_nothing_is_published(client):
    got = await client.get("/api/mobile/latest")
    assert got.status_code == 404
    assert got.json()["detail"] == "No app update has been published yet."


async def test_latest_returns_the_published_release(client, mobile_dir):
    latest = _publish(mobile_dir)
    got = await client.get("/api/mobile/latest")
    assert got.status_code == 200 and got.json() == latest
    assert got.headers["cache-control"] == "no-store"


async def test_apk_streams_with_the_android_type(client, mobile_dir):
    _publish(mobile_dir)
    got = await client.get(f"/api/mobile/apk/{NAME}")
    assert got.status_code == 200 and got.content == APK
    assert got.headers["content-type"] == "application/vnd.android.package-archive"


@pytest.mark.parametrize("name", ["roost-9.9.9+99.apk", "latest.json", "..%2Flatest.json", "roost-1.0.1%2B2.apk.bak"])
async def test_apk_is_404_for_anything_else(client, mobile_dir, name):
    _publish(mobile_dir)
    got = await client.get(f"/api/mobile/apk/{name}")
    assert got.status_code == 404


async def test_both_routes_need_a_session(mobile_dir):
    _publish(mobile_dir)
    cfg = load_config()
    await init_db(cfg)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as anon:
        assert (await anon.get("/api/mobile/latest")).status_code == 401
        assert (await anon.get(f"/api/mobile/apk/{NAME}")).status_code == 401
