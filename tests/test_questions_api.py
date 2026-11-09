"""The question routes: list (all bots or one), answer, dismiss; another user's question is 404."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"


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
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _note(app, user, bot, question="Daily or weekly?"):
    thread, _ = await app.state.talk.ensure_main_thread(user.id, bot.id)
    return await app.state.questions.note(user.id, bot.id, thread.id, question, "weekly", None,
                                          routine_id=None, tainted=False)


async def test_list_all_or_one_bot_then_answer_and_dismiss(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    scout, pip = await make_bot(cfg, alice.id, "Scout"), await make_bot(cfg, alice.id, "Pip")
    first, second, third = await _note(app, alice, scout), await _note(app, alice, pip, "Which tone?"), await _note(app, alice, scout, "Which day?")
    async with signed_in(app, "alice") as client:
        everything = (await client.get("/api/questions?state=open")).json()["questions"]
        only_scout = (await client.get(f"/api/questions?bot_id={scout.id}")).json()["questions"]
        assert {q["id"] for q in everything} == {first.id, second.id, third.id}
        assert {q["id"] for q in only_scout} == {first.id, third.id} and only_scout[0]["default_choice"] == "weekly"

        answered = await client.post(f"/api/questions/{first.id}/answer", json={"answer": "Weekly."}, headers=O)
        dismissed = await client.post(f"/api/questions/{second.id}/dismiss", headers=O)

        assert answered.status_code == 200 and answered.json()["state"] == "answered"
        assert answered.json()["answer"] == "Weekly." and dismissed.json()["state"] == "dismissed"
        assert {q["id"] for q in (await client.get("/api/questions")).json()["questions"]} == {third.id}
        assert (await client.post(f"/api/questions/{first.id}/answer", json={"answer": "x"}, headers=O)).status_code == 409
        assert (await client.post(f"/api/questions/{third.id}/answer", json={"answer": " "}, headers=O)).status_code == 422
        assert (await client.get("/api/questions?state=weird")).status_code == 422


async def test_another_users_questions_are_404(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    await register_user(cfg, "bob", PASSWORD)
    question = await _note(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "bob") as client:
        assert (await client.get("/api/questions")).json() == {"questions": []}
        assert (await client.post(f"/api/questions/{question.id}/answer", json={"answer": "x"}, headers=O)).status_code == 404
        assert (await client.post(f"/api/questions/{question.id}/dismiss", headers=O)).status_code == 404
    async with signed_in(app, "alice") as client:
        assert len((await client.get("/api/questions")).json()["questions"]) == 1


async def test_every_write_needs_the_origin(cfg, app):
    alice = await register_user(cfg, "alice", PASSWORD)
    question = await _note(app, alice, await make_bot(cfg, alice.id, "Scout"))
    async with signed_in(app, "alice") as client:
        bad = {"Origin": "http://evil.example"}
        assert (await client.post(f"/api/questions/{question.id}/answer", json={"answer": "x"}, headers=bad)).status_code == 403
        assert (await client.post(f"/api/questions/{question.id}/dismiss", headers=bad)).status_code == 403
        assert (await client.get("/api/questions")).json()["questions"][0]["state"] == "open"
