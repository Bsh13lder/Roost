"""The "from LazyClaw" mark: the server says which tasks and expenses an import made (migration Task 9)."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _link(kind: str, new_id: str, *, user_id: str | None = None) -> None:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        uid = user_id or con.execute("SELECT id FROM users").fetchone()[0]
        con.execute("INSERT INTO import_links VALUES (?, 'lazyclaw', ?, ?, ?, 'run-1', 'n')", (uid, kind, new_id, new_id))
        con.commit()
    finally:
        con.close()


def test_a_linked_task_and_expense_say_where_they_came_from():
    c = _client()
    imported = c.post("/api/tasks", json={"title": "Old task"}, headers=O).json()
    fresh = c.post("/api/tasks", json={"title": "New task"}, headers=O).json()
    c.post("/api/projects", json={"name": "food"}, headers=O)
    expense = c.post("/api/money/expenses", json={"amount": "4", "project": "food"}, headers=O).json()
    other = c.post("/api/money/expenses", json={"amount": "5", "project": "food"}, headers=O).json()
    _link("task", imported["id"])
    _link("expense", expense["id"])
    assert imported["imported_from"] is None            # the answer to the create is a fresh row
    tasks = {t["id"]: t for t in c.get("/api/tasks?status=all").json()}
    assert tasks[imported["id"]]["imported_from"] == "lazyclaw" and tasks[fresh["id"]]["imported_from"] is None
    assert c.get(f"/api/tasks/{imported['id']}").json()["imported_from"] == "lazyclaw"
    rows = {e["id"]: e for e in c.get("/api/money/expenses").json()}
    assert rows[expense["id"]]["imported_from"] == "lazyclaw" and rows[other["id"]]["imported_from"] is None


def test_a_link_of_another_kind_marks_nothing():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Mine"}, headers=O).json()
    _link("expense", task["id"])         # same id, wrong kind
    assert c.get(f"/api/tasks/{task['id']}").json()["imported_from"] is None
