"""Home's chat list (S1.4): one row per bot and per room, newest first, previews decrypted server-side."""

from __future__ import annotations

import json

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.chats import chat_preview
from roost.talk.store import Message, TalkStore
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}


async def _login(app, cfg, username):
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    assert (await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"},
                              headers=O)).status_code == 200
    return client


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice = await _login(app, cfg, "alice")
    user_id = (await alice.get("/api/auth/me")).json()["id"]
    yield cfg, app, alice, user_id
    await alice.aclose()


async def test_chats_are_newest_first_with_one_line_previews(rig):
    cfg, app, alice, user_id = rig
    helper = await make_bot(cfg, user_id, "Helper")
    quiet = await make_bot(cfg, user_id, "Quiet")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, helper.id)
    await talk.add_message(user_id, thread.id, "user", "first\nline two")
    await talk.add_message(user_id, thread.id, "bot", "x" * 300, author_bot_id=helper.id)
    rows = (await alice.get("/api/chats")).json()
    assert [r["name"] for r in rows] == ["Helper", "Quiet"]
    top = rows[0]
    assert (top["kind"], top["id"], top["preview_kind"], top["from_you"], top["thread_id"]) == (
        "bot", helper.id, "text", False, thread.id)
    assert len(top["preview"]) == 120 and top["preview"].endswith("…")
    assert (rows[1]["preview"], rows[1]["last_at"]) == (None, quiet.created_at)


async def test_your_message_a_card_and_a_room_get_their_own_previews(rig):
    cfg, app, alice, user_id = rig
    a, b = await make_bot(cfg, user_id, "Ann"), await make_bot(cfg, user_id, "Bob")
    talk = TalkStore(cfg)
    thread_a = await talk.create_thread(user_id, a.id)
    await talk.add_message(user_id, thread_a.id, "user", "hello\nthere")
    thread_b = await talk.create_thread(user_id, b.id)
    await talk.add_message(user_id, thread_b.id, "bot", json.dumps({"bot_id": "x", "name": "HiMap SEO"}),
                           kind="bot_created", author_bot_id=b.id)
    room = (await alice.post("/api/rooms", json={"name": "Saturday", "member_ids": [a.id, b.id]}, headers=O)).json()
    rows = {r["name"]: r for r in (await alice.get("/api/chats")).json()}
    assert (rows["Ann"]["preview"], rows["Ann"]["from_you"]) == ("hello there", True)
    assert (rows["Bob"]["preview"], rows["Bob"]["preview_kind"]) == ("Created HiMap SEO", "card")
    assert (rows["Saturday"]["kind"], rows["Saturday"]["id"], rows["Saturday"]["thread_id"]) == (
        "room", room["id"], room["thread_id"])


async def test_another_users_chats_never_show(rig):
    cfg, app, alice, user_id = rig
    await make_bot(cfg, user_id, "Helper")
    bob = await _login(app, cfg, "bob")
    assert (await bob.get("/api/chats")).json() == []
    await bob.aclose()


def _message(body: str, *, role: str = "bot", kind: str = "text") -> Message:
    return Message(id="m", user_id="u", thread_id="t", role=role, body=body, tainted=False, seq=1,
                   created_at="2026-10-14T10:00:00+00:00", kind=kind)


def test_each_kind_of_message_reads_as_its_own_preview():
    assert chat_preview(_message('{"name": "Scout"}', kind="suggestion")) == ("Suggested Scout", "card")
    assert chat_preview(_message("not json", kind="bot_created")) == ("Created a bot", "card")
    assert chat_preview(_message('{"name": 7}', kind="bot_created")) == ("Created a bot", "card")
    assert chat_preview(_message("Chief → Scout:\nprice it", kind="handoff")) == ("Chief → Scout: price it", "handoff")
    assert chat_preview(_message("Stopped.", role="system", kind="notice")) == ("Stopped.", "notice")


def test_a_bot_reply_previews_without_its_on_it_line():
    """Owner, 2026-10-27: "On it: …" is the working robot's line, never the chat list's preview."""
    reply = "On it: checking the WhatsApp chat.\n\nSent: your message is in the chat."
    assert chat_preview(_message(reply)) == ("Sent: your message is in the chat.", "text")
    assert chat_preview(_message("On it: checking your tasks.")) == ("checking your tasks.", "text")
    assert chat_preview(_message("On it: me", role="user")) == ("On it: me", "text")


def test_a_report_a_routine_line_and_a_proposal_preview_as_words_never_as_json():
    report = '{"source":"routine","headline":"Routine checked: nothing new","text":"x","routine_id":"r"}'
    assert chat_preview(_message(report, kind="report")) == ("Routine checked: nothing new", "notice")
    note = '{"routine_id": null, "verb": "updated", "name": "plan", "text": "Updated plan · 1 items"}'
    assert chat_preview(_message(note, role="activity", kind="routine_note")) == ("Updated plan · 1 items", "notice")
    assert chat_preview(_message(note, role="activity", kind="question_note")) == ("Updated plan · 1 items", "notice")
    assert chat_preview(_message('{"proposal_id": "p"}', kind="routine_proposal")) == ("Asking you: a routine", "card")
    assert chat_preview(_message("not json", kind="report")) == ("A report", "notice")
    assert chat_preview(_message("not json", role="activity", kind="routine_note")) == ("A routine update", "notice")
