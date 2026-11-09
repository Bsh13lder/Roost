"""`default_due` on POST /api/tasks/parse (G6): a Kanban column's day, used only when the line names none."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_default_due_fills_only_when_the_line_names_no_day():
    c = _client()
    plain = c.post("/api/tasks/parse", json={"text": "Call Ana", "default_due": "2026-10-21"}, headers=O).json()
    assert plain["due_date"] == "2026-10-21" and plain["title"] == "Call Ana"
    assert "21 Oct" in plain["due_text"]
    named = c.post("/api/tasks/parse", json={"text": "Call Ana on 2026-11-02", "default_due": "2026-10-21"}, headers=O).json()
    assert named["due_date"].startswith("2026-11-02")
    none = c.post("/api/tasks/parse", json={"text": "Call Ana"}, headers=O).json()
    assert none["due_date"] is None


def test_default_due_must_be_an_iso_day():
    c = _client()
    for bad in ("tomorrow", "2026-13-40", "2026-10-21T09:00"):
        r = c.post("/api/tasks/parse", json={"text": "Call Ana", "default_due": bad}, headers=O)
        assert r.status_code == 422, bad
