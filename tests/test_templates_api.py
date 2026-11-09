"""Templates replace roles and presets (S1.7): they only fill the New bot form."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_templates_hold_name_job_instructions_and_look_only():
    c = _client()
    templates = c.get("/api/templates").json()
    assert [t["id"] for t in templates] == ["chief", "life_admin", "researcher"]
    assert [t["label"] for t in templates] == ["Main bot", "Life admin", "Researcher"]
    for template in templates:
        assert set(template) == {"id", "label", "name", "job", "instructions", "avatar"}
        assert template["avatar"]["badge"] == "none"
    assert "ask_bot" in templates[0]["instructions"]


def test_reading_templates_creates_no_bot_and_needs_a_login():
    assert TestClient(create_app()).get("/api/templates").status_code == 401
    c = _client()
    before = len(c.get("/api/bots").json())
    c.get("/api/templates")
    assert len(c.get("/api/bots").json()) == before


def test_the_role_routes_are_gone():
    c = _client()
    assert c.get("/api/roles").status_code == 404
    assert c.get("/api/presets").status_code == 404
