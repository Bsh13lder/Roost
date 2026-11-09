"""``PUT /api/threads/{id}/messages/{message_id}/reminder-answer``: a reminder card's answer (Done · Failed ·
Reschedule · Skip) is stored on the Report itself, so the web and the phone both show it after a reload or a
restart. Only the owner's reminder Reports take one; anything else is a 404."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.models import ReportBody
from roost.routines.reminder_answers import reminder_answer
from roost.talk.store import TalkStore
from team_helpers import frames_so_far, make_bot

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}


async def _login(app, cfg, username):
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"},
                              headers=O)).status_code == 200
    return client, (await client.get("/api/auth/me")).json()["id"]


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice, alice_id = await _login(app, cfg, "alice")
    bob, bob_id = await _login(app, cfg, "bob")
    scout = await make_bot(cfg, alice_id, "Scout")
    thread = await TalkStore(cfg).create_thread(alice_id, scout.id)
    yield cfg, app, alice, alice_id, bob, scout, thread
    await alice.aclose()
    await bob.aclose()


async def _report(cfg, user_id, bot_id, thread_id, *, task_id="task-1", source="reminder"):
    body = ReportBody(source=source, headline="Reminder: Call the bank", text="Due today.", bot_id=bot_id,
                      task_id=task_id)
    return await TalkStore(cfg).add_message(user_id, thread_id, "bot", body.model_dump_json(), kind="report",
                                            author_bot_id=bot_id)


def _url(thread_id, message_id):
    return f"/api/threads/{thread_id}/messages/{message_id}/reminder-answer"


def _sealed_body(cfg, message_id):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT body FROM messages WHERE id = ?", (message_id,)).fetchone()[0]
    finally:
        con.close()


async def test_skip_is_stored_on_the_report_and_survives_a_reload(rig):
    cfg, app, alice, alice_id, _bob, scout, thread = rig
    message = await _report(cfg, alice_id, scout.id, thread.id)
    r = await alice.put(_url(thread.id, message.id), json={"answer": "skipped"}, headers=O)
    assert r.status_code == 200
    body = json.loads(r.json()["body"])
    assert body["answer"] == "skipped" and body["answer_due"] is None and body["answered_at"]
    assert body["task_id"] == "task-1" and body["headline"] == "Reminder: Call the bank"
    listed = (await alice.get(f"/api/threads/{thread.id}/messages")).json()
    [again] = [m for m in listed if m["id"] == message.id]
    assert json.loads(again["body"])["answer"] == "skipped"
    sealed = _sealed_body(cfg, message.id)
    assert sealed.startswith("enc:v2") and "skipped" not in sealed


async def test_each_answer_is_kept_and_a_reschedule_keeps_its_new_due(rig):
    cfg, _app, alice, alice_id, _bob, scout, thread = rig
    for answer in ("done", "failed"):
        message = await _report(cfg, alice_id, scout.id, thread.id)
        r = await alice.put(_url(thread.id, message.id), json={"answer": answer}, headers=O)
        assert r.status_code == 200 and json.loads(r.json()["body"])["answer"] == answer
    for due in ("2026-10-29T10:00", "2026-10-29", None):
        message = await _report(cfg, alice_id, scout.id, thread.id)
        r = await alice.put(_url(thread.id, message.id), json={"answer": "rescheduled", "due": due}, headers=O)
        assert r.status_code == 200
        body = json.loads(r.json()["body"])
        assert body["answer"] == "rescheduled" and body["answer_due"] == due


async def test_the_answer_is_published_so_every_screen_folds_the_card(rig):
    cfg, app, alice, alice_id, _bob, scout, thread = rig
    message = await _report(cfg, alice_id, scout.id, thread.id)
    sub = app.state.events.subscribe(alice_id)
    await alice.put(_url(thread.id, message.id), json={"answer": "skipped"}, headers=O)
    frames = [f for f in await frames_so_far(sub) if f["type"] == "message"]
    assert [f["message"]["id"] for f in frames] == [message.id]
    assert json.loads(frames[0]["message"]["body"])["answer"] == "skipped"


async def test_another_users_reminder_is_a_404_and_stays_unanswered(rig):
    cfg, _app, _alice, alice_id, bob, scout, thread = rig
    message = await _report(cfg, alice_id, scout.id, thread.id)
    r = await bob.put(_url(thread.id, message.id), json={"answer": "skipped"}, headers=O)
    assert r.status_code == 404
    stored = await TalkStore(cfg).get_message(alice_id, message.id)
    assert json.loads(stored.body).get("answer") is None


async def test_only_a_task_reminder_report_in_this_thread_takes_an_answer(rig):
    cfg, _app, alice, alice_id, _bob, scout, thread = rig
    plain = await _report(cfg, alice_id, scout.id, thread.id, task_id=None)
    routine = await _report(cfg, alice_id, scout.id, thread.id, source="routine")
    reply = await TalkStore(cfg).add_message(alice_id, thread.id, "bot", "hello", author_bot_id=scout.id)
    other = await TalkStore(cfg).create_thread(alice_id, scout.id)
    reminder = await _report(cfg, alice_id, scout.id, thread.id)
    for thread_id, message_id in ((thread.id, plain.id), (thread.id, routine.id), (thread.id, reply.id),
                                  (other.id, reminder.id), (thread.id, "nope"), ("nope", reminder.id)):
        r = await alice.put(_url(thread_id, message_id), json={"answer": "skipped"}, headers=O)
        assert r.status_code == 404, (thread_id, message_id)


async def test_bad_answers_and_foreign_origins_are_refused(rig):
    cfg, _app, alice, alice_id, _bob, scout, thread = rig
    message = await _report(cfg, alice_id, scout.id, thread.id)
    url = _url(thread.id, message.id)
    for payload in ({"answer": "maybe"}, {"answer": "skipped", "due": "2026-10-29"},
                    {"answer": "rescheduled", "due": "Thursday"}, {"answer": "skipped", "extra": 1}, {}):
        assert (await alice.put(url, json=payload, headers=O)).status_code == 422, payload
    assert (await alice.put(url, json={"answer": "skipped"}, headers=BAD_O)).status_code == 403


async def test_a_later_answer_replaces_the_earlier_one(rig):
    cfg, _app, alice, alice_id, _bob, scout, thread = rig
    message = await _report(cfg, alice_id, scout.id, thread.id)
    await alice.put(_url(thread.id, message.id), json={"answer": "skipped"}, headers=O)
    r = await alice.put(_url(thread.id, message.id), json={"answer": "done"}, headers=O)
    assert json.loads(r.json()["body"])["answer"] == "done"


async def test_the_store_helper_returns_none_for_no_such_reminder(rig):
    cfg, _app, _alice, alice_id, _bob, scout, thread = rig
    talk = TalkStore(cfg)
    assert await reminder_answer(talk, alice_id, thread.id, "nope", "skipped", None) is None
    message = await _report(cfg, alice_id, scout.id, thread.id)
    answered = await reminder_answer(talk, "someone-else", thread.id, message.id, "skipped", None)
    assert answered is None


def test_an_old_report_body_reads_unanswered():
    old = json.dumps({"source": "reminder", "headline": "Reminder: x", "text": "", "task_id": "t"})
    body = ReportBody.model_validate_json(old)
    assert body.answer is None and body.answer_due is None and body.answered_at is None
