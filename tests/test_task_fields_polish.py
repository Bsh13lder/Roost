"""Tasks & Money polish Task 2: a star, a sealed estimate, and a repeat and reminder on TaskIn."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _raw(sql: str) -> list[tuple]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_estimate_is_stored_sealed():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Paint", "estimate_minutes": 90, "starred": True}, headers=O).json()
    [(starred, estimate)] = _raw(f"SELECT starred, estimate FROM tasks WHERE id = '{task['id']}'")
    assert starred == 1 and estimate.startswith("enc:v2")
    assert "90" not in estimate
    assert c.get("/api/tasks").json()[0]["estimate_minutes"] == 90


def test_task_in_takes_recurring_reminder_star_estimate():
    c = _client()
    r = c.post("/api/tasks", json={"title": "Water plants", "due_date": "2026-12-01T09:00", "reminder_at": "2026-11-30 at 18:00",
                                   "recurring": "0 9 * * 1", "starred": True, "estimate_minutes": 30}, headers=O)
    assert r.status_code == 201
    task = r.json()
    assert (task["recurring"], task["starred"], task["estimate_minutes"]) == ("0 9 * * 1", True, 30)
    assert task["reminder_at"] == "2026-11-30T17:00:00+00:00"          # Madrid winter time
    assert task["due_date"] == "2026-12-01T09:00:00+01:00"
    assert task["repeat_text"] is None or isinstance(task["repeat_text"], str)


def test_a_new_task_is_not_starred_and_has_no_estimate():
    task = _client().post("/api/tasks", json={"title": "Plain"}, headers=O).json()
    assert (task["starred"], task["estimate_minutes"]) == (False, None)


@pytest.mark.parametrize("body", [
    {"recurring": "every now and then"}, {"estimate_minutes": 0}, {"estimate_minutes": 6001},
    {"estimate_minutes": 1.5}, {"starred": "yes"}, {"reminder_at": "someday-ish"},
])
def test_bad_cron_or_estimate_is_a_422(body):
    c = _client()
    r = c.post("/api/tasks", json={"title": "x", **body}, headers=O)
    assert r.status_code == 422
    assert c.get("/api/tasks").json() == []


def test_patch_sets_and_clears_star_and_estimate():
    c = _client()
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    set_ = c.patch(f"/api/tasks/{task['id']}", json={"starred": True, "estimate_minutes": 45}, headers=O).json()
    assert (set_["starred"], set_["estimate_minutes"]) == (True, 45)
    cleared = c.patch(f"/api/tasks/{task['id']}", json={"starred": False, "estimate_minutes": None}, headers=O).json()
    assert (cleared["starred"], cleared["estimate_minutes"]) == (False, None)
    assert c.patch(f"/api/tasks/{task['id']}", json={"estimate_minutes": 0}, headers=O).status_code == 422
    assert c.patch(f"/api/tasks/{task['id']}", json={"starred": None}, headers=O).status_code == 422
