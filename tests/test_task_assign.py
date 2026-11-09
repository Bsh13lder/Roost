"""Assigning a task to a bot with @bot: only with your confirmation, and only as your own message."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.work.models import ORIGIN_YOU
from roost.work.queue import WorkQueue

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _bot(c: TestClient, name: str = "Scout") -> dict:
    return c.post("/api/bots", json={"name": name, "job": "helps", "instructions": "", "avatar": AVATAR},
                  headers=O).json()


def _rows(sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def test_assign_needs_confirmation():
    c = _client()
    scout = _bot(c)
    before = _rows("SELECT COUNT(*) FROM work_items")[0][0]
    r = c.post("/api/tasks", json={"title": "Call plumber", "assign_bot_id": scout["id"]}, headers=O)
    assert r.status_code == 422 and r.json()["detail"] == "Confirm handing this to Scout first."
    assert c.get("/api/tasks").json() == []
    assert _rows("SELECT COUNT(*) FROM work_items")[0][0] == before


def test_confirmed_assign_queues_your_message():
    c = _client()
    scout = _bot(c)
    r = c.post("/api/tasks", json={"title": "Call plumber", "due_date": "2026-12-01T09:00", "assign_bot_id": scout["id"],
                                   "assign_confirmed": True}, headers=O)
    assert r.status_code == 201 and r.json()["owner"] == scout["id"]
    [(item_id, user_id)] = _rows("SELECT id, user_id FROM work_items WHERE bot_id = ?", (scout["id"],))
    item = asyncio.run(WorkQueue(load_config()).get(user_id, item_id))
    assert (item.bot_id, item.kind.value, item.origin, item.tainted) == (scout["id"], "message", ORIGIN_YOU, False)
    thread = c.post(f"/api/bots/{scout['id']}/chat", headers=O).json()
    messages = c.get(f"/api/threads/{thread['id']}/messages").json()
    mine = [m for m in messages if m["role"] == "user"]
    assert [m["body"] for m in mine] == ["Please take this task: “Call plumber” (due Tue 01 Dec 09:00)."]


def test_another_users_bot_cannot_be_assigned():
    c = _client()
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    bobs_bot = _bot(bob, "Bobby")
    r = c.post("/api/tasks", json={"title": "Steal", "assign_bot_id": bobs_bot["id"], "assign_confirmed": True}, headers=O)
    assert r.status_code == 422 and r.json()["detail"] == "No such bot."
    assert c.get("/api/tasks").json() == []
    assert _rows("SELECT COUNT(*) FROM work_items WHERE bot_id = ?", (bobs_bot["id"],))[0][0] == 0


def test_a_task_with_no_assignee_queues_nothing():
    c = _client()
    scout = _bot(c)
    assert c.post("/api/tasks", json={"title": "Plain"}, headers=O).json()["owner"] == "user"
    assert _rows("SELECT COUNT(*) FROM work_items WHERE bot_id = ?", (scout["id"],))[0][0] == 0
