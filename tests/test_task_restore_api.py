"""Task undelete (mobile SERVER_NEEDS M2a): ``POST /api/tasks/{id}/restore`` brings a deleted task back.

Deleting is soft (``deleted_at``), so Undo restores the same task: its id, its comments and its steps. A task that
isn't deleted, an unknown id and another user's task are all 404."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
NOT_FOUND = {"detail": "No deleted task with that id"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def app(cfg):
    return create_app(cfg)


@asynccontextmanager
async def signed_in(app, username):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        yield client


async def _deleted_task(client) -> dict:
    task = (await client.post("/api/tasks", json={"title": "Call the dentist", "steps": ["Find the number"]},
                              headers=O)).json()
    assert (await client.post(f"/api/tasks/{task['id']}/comments", json={"body": "Ask about Tuesday"},
                              headers=O)).status_code == 201
    assert (await client.delete(f"/api/tasks/{task['id']}", headers=O)).status_code == 204
    return task


async def test_restore_brings_back_the_same_task_with_its_comments(cfg, app):
    await register_user(cfg, "alice", PASSWORD)
    async with signed_in(app, "alice") as client:
        task = await _deleted_task(client)
        assert (await client.get("/api/tasks")).json() == []

        restored = await client.post(f"/api/tasks/{task['id']}/restore", headers=O)

        assert restored.status_code == 200
        body = restored.json()
        assert (body["id"], body["title"], [s["title"] for s in body["steps"]]) == (
            task["id"], "Call the dentist", ["Find the number"])
        assert [t["id"] for t in (await client.get("/api/tasks")).json()] == [task["id"]]
        comments = (await client.get(f"/api/tasks/{task['id']}/comments")).json()
        assert [c["body"] for c in comments] == ["Ask about Tuesday"]
        user_id = (await client.get("/api/auth/me")).json()["id"]
        frames = [f for f in await app.state.events.since(user_id, 0) if f["type"] == "tasks_changed"]
        assert (frames[-1]["change"], frames[-1]["task_id"]) == ("restored", task["id"])


async def test_a_live_task_or_an_unknown_id_is_404_and_a_second_restore_too(cfg, app):
    await register_user(cfg, "alice", PASSWORD)
    async with signed_in(app, "alice") as client:
        live = (await client.post("/api/tasks", json={"title": "Still here"}, headers=O)).json()
        assert (await client.post(f"/api/tasks/{live['id']}/restore", headers=O)).json() == NOT_FOUND
        assert (await client.post("/api/tasks/no-such-task/restore", headers=O)).status_code == 404
        gone = await _deleted_task(client)
        assert (await client.post(f"/api/tasks/{gone['id']}/restore", headers=O)).status_code == 200
        assert (await client.post(f"/api/tasks/{gone['id']}/restore", headers=O)).status_code == 404


async def test_another_users_deleted_task_is_404_and_stays_deleted(cfg, app):
    await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    async with signed_in(app, "alice") as alice:
        task = await _deleted_task(alice)
    async with signed_in(app, "bob") as bob:
        answer = await bob.post(f"/api/tasks/{task['id']}/restore", headers=O)
        assert answer.status_code == 404 and answer.json() == NOT_FOUND
    async with signed_in(app, "alice") as alice:
        assert (await alice.get("/api/tasks")).json() == []


async def test_restore_needs_the_origin(cfg, app):
    await register_user(cfg, "alice", PASSWORD)
    async with signed_in(app, "alice") as client:
        task = await _deleted_task(client)
        refused = await client.post(f"/api/tasks/{task['id']}/restore", headers={"Origin": "http://evil.example"})
        assert refused.status_code == 403
