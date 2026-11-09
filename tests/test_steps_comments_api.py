"""A task's steps and comments over HTTP (redesign P3), and Review Focus 5: another user's task,
step or comment is a 404, never the object."""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.store import TaskStore

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _second_user() -> TestClient:
    """Bob: registration closes after the first account, so he is made directly, then logs in."""
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    c = TestClient(create_app())
    assert c.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    return c


def _task(c: TestClient, title: str = "Fix the sink") -> dict:
    return c.post("/api/tasks", json={"title": title}, headers=O).json()


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_add_rename_tick_move_and_delete_steps():
    c = _client()
    task = _task(c)
    first = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O)
    assert first.status_code == 201
    second = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Fit it"}, headers=O).json()
    washer, fit = (step["id"] for step in second["steps"])
    ticked = c.patch(f"/api/tasks/{task['id']}/steps/{washer}", json={"done": True, "title": "Buy two washers"}, headers=O)
    assert ticked.json()["steps"][0] == {"id": washer, "title": "Buy two washers", "done": True}
    moved = c.post(f"/api/tasks/{task['id']}/steps/{fit}/move", json={"position": 0}, headers=O).json()
    assert [step["id"] for step in moved["steps"]] == [fit, washer]
    deleted = c.delete(f"/api/tasks/{task['id']}/steps/{fit}", headers=O).json()
    assert ([step["id"] for step in deleted["steps"]], deleted["moved_expenses"], deleted["moved_comments"]) == ([washer], 0, 0)
    assert _frames()[-5:] == ["tasks_changed"] * 5


def test_a_step_change_it_refuses_says_why():
    c = _client()
    task = _task(c)
    assert c.post(f"/api/tasks/{task['id']}/steps", json={"title": "  "}, headers=O).json()["detail"] == "A step needs a title."
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    assert c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={}, headers=O).status_code == 422
    assert c.post(f"/api/tasks/{task['id']}/steps/{step['id']}/move", json={"position": -1}, headers=O).status_code == 422
    unknown = c.patch(f"/api/tasks/{task['id']}/steps/s-nope", json={"done": True}, headers=O)
    assert (unknown.status_code, unknown.json()["detail"]) == (404, "That task has no such step.")
    assert c.post("/api/tasks/no-such-task/steps", json={"title": "x"}, headers=O).status_code == 404


def test_comment_thread_add_edit_delete():
    c = _client()
    task = _task(c)
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    on_task = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "Plumber at 9"}, headers=O)
    assert on_task.status_code == 201 and on_task.json()["author"] == "user"
    on_step = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "15 mm", "step_id": step["id"]}, headers=O).json()
    assert on_step["step_id"] == step["id"]
    edited = c.patch(f"/api/comments/{on_task.json()['id']}", json={"body": "Plumber at 10"}, headers=O).json()
    assert edited["body"] == "Plumber at 10" and edited["edited_at"]
    assert c.delete(f"/api/comments/{on_step['id']}", headers=O).status_code == 204
    assert [comment["body"] for comment in c.get(f"/api/tasks/{task['id']}/comments").json()] == ["Plumber at 10"]
    refused = c.post(f"/api/tasks/{task['id']}/comments", json={"body": "x", "step_id": "s-nope"}, headers=O)
    assert (refused.status_code, refused.json()["detail"]) == (422, "That task has no such step.")
    assert c.post(f"/api/tasks/{task['id']}/comments", json={"body": "   "}, headers=O).status_code == 422


def test_a_bots_comment_is_403_to_edit_or_delete():
    c = _client()
    task = _task(c)
    user_id = c.get("/api/auth/me").json()["id"]
    cfg = load_config()
    bots = asyncio.run(CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg)).add(
        user_id, task["id"], "Found it on shop.example", author="bot-1", tainted=True))
    [shown] = c.get(f"/api/tasks/{task['id']}/comments").json()
    assert (shown["author"], shown["tainted"]) == ("bot-1", True)
    edit = c.patch(f"/api/comments/{bots.id}", json={"body": "mine now"}, headers=O)
    assert (edit.status_code, edit.json()["detail"]) == (403, "Only your own comments can be changed.")
    assert c.delete(f"/api/comments/{bots.id}", headers=O).status_code == 403


def test_another_users_task_steps_and_comments_are_404():
    """Review Focus 5."""
    alice = _client()
    task = _task(alice)
    step = alice.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    comment = alice.post(f"/api/tasks/{task['id']}/comments", json={"body": "Mine"}, headers=O).json()
    bob = _second_user()
    tid, sid = task["id"], step["id"]
    for response in (
        bob.post(f"/api/tasks/{tid}/steps", json={"title": "x"}, headers=O),
        bob.patch(f"/api/tasks/{tid}/steps/{sid}", json={"done": True}, headers=O),
        bob.post(f"/api/tasks/{tid}/steps/{sid}/move", json={"position": 0}, headers=O),
        bob.delete(f"/api/tasks/{tid}/steps/{sid}", headers=O),
        bob.get(f"/api/tasks/{tid}/comments"),
        bob.post(f"/api/tasks/{tid}/comments", json={"body": "x"}, headers=O),
        bob.patch(f"/api/comments/{comment['id']}", json={"body": "x"}, headers=O),
        bob.delete(f"/api/comments/{comment['id']}", headers=O),
    ):
        assert response.status_code == 404, response.request.url
        assert "Mine" not in response.text and "Buy a washer" not in response.text
    [kept] = alice.get(f"/api/tasks/{tid}/comments").json()
    assert kept["body"] == "Mine"


def test_step_and_comment_changes_need_the_origin_and_a_login():
    c = _client()
    task = _task(c)
    evil = {"Origin": "http://evil.example"}
    assert c.post(f"/api/tasks/{task['id']}/steps", json={"title": "x"}, headers=evil).status_code == 403
    assert c.post(f"/api/tasks/{task['id']}/comments", json={"body": "x"}, headers=evil).status_code == 403
    assert TestClient(create_app()).get(f"/api/tasks/{task['id']}/comments").status_code == 401
