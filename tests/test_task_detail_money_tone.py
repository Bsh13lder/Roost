"""The drawer's money carries the server's meter rule (G5): used_percent and tone from budget_line."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _task(c: TestClient, slice_: str | None) -> dict:
    project = c.post("/api/projects", json={"name": "Renovation", "currency": "EUR"}, headers=O).json()
    fields = {"title": "Fix the sink", "project_id": project["id"], **({"allocated_budget": slice_} if slice_ else {})}
    return c.post("/api/tasks", json=fields, headers=O).json()


def test_detail_money_carries_tone_and_percent():
    c = _client()
    task = _task(c, "100")
    assert c.post("/api/money/expenses", json={"amount": "120", "task_id": task["id"]}, headers=O).status_code == 201
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert (money["used_percent"], money["tone"]) == (120, "over")


def test_no_slice_has_no_tone():
    c = _client()
    task = _task(c, None)
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert (money["used_percent"], money["tone"]) == (None, None)
