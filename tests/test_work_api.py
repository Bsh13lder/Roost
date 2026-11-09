"""``POST /api/bots/{id}/stop`` and ``PUT /api/bots/{id}/duty``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client_with_bot() -> tuple[TestClient, str]:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    r = c.post("/api/bots", json={"name": "Scout", "job": "read news", "instructions": "", "avatar": AVATAR}, headers=O)
    return c, r.json()["id"]


def test_stop_an_idle_bot_drops_nothing():
    c, bot_id = _client_with_bot()
    r = c.post(f"/api/bots/{bot_id}/stop", headers=O)
    assert (r.status_code, r.json()) == (200, {"dropped": 0, "interrupted": 0, "done": []})


def test_duty_round_trip():
    c, bot_id = _client_with_bot()
    off = c.put(f"/api/bots/{bot_id}/duty", json={"off_duty": True}, headers=O).json()
    assert (off["off_duty"], off["status"]) == (True, "off_duty")
    back = c.put(f"/api/bots/{bot_id}/duty", json={"off_duty": False}, headers=O).json()
    assert (back["off_duty"], back["status"]) == (False, "resting")


def test_duty_rejects_a_non_boolean():
    c, bot_id = _client_with_bot()
    assert c.put(f"/api/bots/{bot_id}/duty", json={"off_duty": "yes"}, headers=O).status_code == 422


def test_unknown_or_foreign_bot_is_404():
    c, _ = _client_with_bot()
    assert c.post("/api/bots/not-a-bot/stop", headers=O).status_code == 404
    assert c.put("/api/bots/not-a-bot/duty", json={"off_duty": True}, headers=O).status_code == 404


def test_controls_need_an_allowed_origin():
    c, bot_id = _client_with_bot()
    assert c.post(f"/api/bots/{bot_id}/stop", headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.put(f"/api/bots/{bot_id}/duty", json={"off_duty": True}).status_code == 403
