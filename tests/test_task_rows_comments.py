"""Task rows carry how many live comments they have, so the phone's row can show a comment mark."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from roost.gateway.auth import register_user
from roost.config import load_config
from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}


def client() -> TestClient:
    c = TestClient(create_app())
    made = c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    assert made.status_code == 201
    return c


def bob_client() -> TestClient:
    """Registration closes after the first account, so Bob is made directly, then logs in."""
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    c = TestClient(create_app())
    assert c.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    return c


def task(c: TestClient, title: str) -> dict:
    made = c.post("/api/tasks", json={"title": title}, headers=O)
    assert made.status_code == 201, made.text
    return made.json()


def comment(c: TestClient, task_id: str, body: str) -> dict:
    made = c.post(f"/api/tasks/{task_id}/comments", json={"body": body}, headers=O)
    assert made.status_code == 201, made.text
    return made.json()


def counts(c: TestClient, url: str) -> dict[str, int]:
    return {r["id"]: r["comment_count"] for r in c.get(url).json()}


def test_rows_count_live_comments_and_skip_deleted_ones():
    c = client()
    talked, quiet = task(c, "Plumber"), task(c, "Paint")
    comment(c, talked["id"], "At 9")
    gone = comment(c, talked["id"], "Bring 15 mm")
    comment(c, talked["id"], "Done")
    assert c.delete(f"/api/comments/{gone['id']}", headers=O).status_code in (200, 204)
    for url in ("/api/tasks", "/api/tasks?sort=due", "/api/tasks?view=someday"):
        assert counts(c, url) == {talked["id"]: 2, quiet["id"]: 0}


def test_another_users_comments_never_count():
    alice = client()
    mine = task(alice, "Mine")
    comment(alice, mine["id"], "Hello")
    bob = bob_client()
    task(bob, "Bob's")
    assert set(counts(bob, "/api/tasks").values()) == {0}
