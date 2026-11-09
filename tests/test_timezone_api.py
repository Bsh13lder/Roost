"""``PUT /api/auth/timezone`` and the zone on ``GET /api/auth/me`` (docs/plans/2026-11-09-roost-time-zone.md)."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app
from roost.timezones import local_tz_name

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}


def _signed_in() -> TestClient:
    client = TestClient(create_app())
    client.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    client.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O)
    return client


def _stored() -> str | None:
    with sqlite3.connect(get_db_path(load_config())) as raw:
        return raw.execute("SELECT timezone FROM users").fetchone()[0]


def test_me_shows_no_zone_until_one_is_set():
    client = _signed_in()
    assert client.get("/api/auth/me").json() == {"id": client.get("/api/auth/me").json()["id"], "username": "me",
                                                 "timezone": None}


def test_put_sets_the_zone_for_the_install():
    client = _signed_in()
    r = client.put("/api/auth/timezone", json={"timezone": "America/New_York"}, headers=O)
    assert r.status_code == 200 and r.json() == {"timezone": "America/New_York"}
    assert client.get("/api/auth/me").json()["timezone"] == "America/New_York"
    assert _stored() == "America/New_York"
    assert local_tz_name() == "America/New_York"


@pytest.mark.parametrize("body", [
    {"timezone": "localtime"}, {"timezone": "Mars/Olympus"}, {"timezone": ""}, {"timezone": "x" * 65},
    {"timezone": 5}, {}, {"timezone": "UTC", "extra": 1}, {"timezone": "Europe/Madrid\u0000secret-words"},
])
def test_put_refuses_a_bad_zone_without_echoing_it(body):
    client = _signed_in()
    r = client.put("/api/auth/timezone", json=body, headers=O)
    assert r.status_code == 422
    assert "secret-words" not in r.text and "Mars" not in r.text and "xxxx" not in r.text
    assert _stored() is None and local_tz_name() == "Europe/Madrid"


def test_put_needs_a_session():
    client = TestClient(create_app())
    assert client.put("/api/auth/timezone", json={"timezone": "UTC"}, headers=O).status_code == 401


def test_put_needs_the_origin():
    client = _signed_in()
    assert client.put("/api/auth/timezone", json={"timezone": "UTC"}, headers=BAD_O).status_code == 403
    assert _stored() is None
