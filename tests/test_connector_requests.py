"""The Add a key card (request_connector): a bot asks for a key it doesn't have; the user's Save makes the
connector through the same checks as POST /api/connectors, and the key is never in a message, an event, the
audit or the bot's run."""

from __future__ import annotations

import json
import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.connectors import texts
from roost.connectors.requests import KEY_ADDED, NOT_NOW
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.talk.domain_tools import RecordContext
from roost.talk.tool_catalog import CATALOG

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
SECRET = "sk-live-REQUESTED-key-987654321"
ASK = {"service": "Ahrefs", "base_url": "https://api.ahrefs.com/v3", "why": "to read keyword volumes"}


class Turns:
    """Captures the work items a card's answer queues (no real run)."""

    def __init__(self) -> None:
        self.drafts = []

    async def submit(self, user_id, draft, *, item_id=None):
        self.drafts.append(draft)


def _client(app) -> tuple[TestClient, str, str]:
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                  headers=ORIGIN).status_code == 201
    return c, c.get("/api/auth/me").json()["id"], c.get("/api/bots").json()[0]["id"]


async def _ask(app, user_id, bot_id, args=None, *, tainted=False):
    thread, _ = await app.state.talk.ensure_main_thread(user_id, bot_id)
    ctx = RecordContext(user_id=user_id, bot_id=bot_id, tainted=tainted, thread_id=thread.id, run_id="r1")
    outcome = await app.state.turns.domain.run("request_connector", args or ASK, ctx)
    return outcome, thread.id


def _rows(sql: str, params=()) -> list[tuple]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


async def _message_bodies(user_id: str) -> str:
    dek = await get_user_dek(load_config(), user_id)
    rows = _rows("SELECT body FROM messages WHERE user_id = ?", (user_id,))
    return " ".join(decrypt_field(r[0], dek, user_aad(user_id, "messages:body")) or "" for r in rows)


def _event_text() -> str:
    return repr(_rows("SELECT * FROM events"))


def test_the_tool_is_a_read_for_every_bot():
    assert CATALOG["request_connector"].kind == "read" and CATALOG["request_connector"].no_ask


async def test_save_makes_the_connector_and_the_key_goes_nowhere_else():
    app = create_app()
    turns = Turns()
    c, user_id, bot_id = _client(app)
    app.state.connector_requests.attach(turns)
    outcome, thread_id = await _ask(app, user_id, bot_id)
    assert "Ahrefs" in outcome.text and not outcome.tainted
    [row] = c.get("/api/connector-requests?state=open").json()
    assert (row["service"], row["host"], row["why"], row["state"]) == (
        "Ahrefs", "api.ahrefs.com", "to read keyword volumes", "open")
    assert c.get(f"/api/connector-requests/{row['id']}").json()["bot_id"] == bot_id
    card = [m for m in c.get(f"/api/threads/{thread_id}/messages").json() if m["kind"] == "connector_request"]
    assert len(card) == 1 and json.loads(card[0]["body"])["request_id"] == row["id"]
    saved = c.post(f"/api/connector-requests/{row['id']}/save", json={"secret": SECRET}, headers=ORIGIN)
    assert saved.status_code == 200 and saved.json()["state"] == "saved" and SECRET not in saved.text
    [made] = c.get("/api/connectors").json()
    assert (made["name"], made["host"], made["purpose"]) == ("Ahrefs", "api.ahrefs.com", "to read keyword volumes")
    assert made["key_hint"].endswith("4321")
    assert [d.body for d in turns.drafts] == [KEY_ADDED.format(name="Ahrefs")]
    assert turns.drafts[0].thread_id == thread_id and turns.drafts[0].bot_id == bot_id
    assert SECRET not in await _message_bodies(user_id) and SECRET not in _event_text()
    assert KEY_ADDED.format(name="Ahrefs") in await _message_bodies(user_id)
    assert c.get("/api/connector-requests?state=open").json() == []
    again = c.post(f"/api/connector-requests/{row['id']}/save", json={"secret": SECRET}, headers=ORIGIN)
    assert again.status_code == 409 and SECRET not in again.text


async def test_not_now_tells_the_bot_and_makes_nothing():
    app = create_app()
    turns = Turns()
    c, user_id, bot_id = _client(app)
    app.state.connector_requests.attach(turns)
    await _ask(app, user_id, bot_id)
    [row] = c.get("/api/connector-requests").json()
    declined = c.post(f"/api/connector-requests/{row['id']}/decline", headers=ORIGIN)
    assert declined.status_code == 200 and declined.json()["state"] == "declined"
    assert c.get("/api/connectors").json() == []
    assert turns.drafts[0].body.startswith(NOT_NOW.format(service="Ahrefs")[:20])
    assert c.post(f"/api/connector-requests/{row['id']}/decline", headers=ORIGIN).status_code == 409


async def test_a_refused_base_url_makes_no_card():
    app = create_app()
    c, user_id, bot_id = _client(app)
    for url, sentence in (("https://127.0.0.1/v1", texts.PRIVATE_HOST), ("http://api.example.com", texts.HTTPS_ONLY),
                          ("https://metadata.internal", texts.PRIVATE_HOST), ("https://[::1]", texts.PRIVATE_HOST)):
        outcome, _ = await _ask(app, user_id, bot_id, ASK | {"base_url": url})
        assert outcome.text == sentence
    assert c.get("/api/connector-requests").json() == []


async def test_a_bad_key_keeps_the_card_open_and_never_echoes_it():
    app = create_app()
    c, user_id, bot_id = _client(app)
    app.state.connector_requests.attach(Turns())
    await _ask(app, user_id, bot_id)
    [row] = c.get("/api/connector-requests").json()
    bad = c.post(f"/api/connector-requests/{row['id']}/save", json={"secret": SECRET + " \n"}, headers=ORIGIN)
    assert bad.status_code == 422 and bad.json() == {"detail": texts.BAD_SECRET} and SECRET not in bad.text
    missing = c.post(f"/api/connector-requests/{row['id']}/save", json={}, headers=ORIGIN)
    assert missing.json() == {"detail": texts.NEEDS_SECRET}
    assert c.get(f"/api/connector-requests/{row['id']}").json()["state"] == "open"
    assert c.get("/api/connectors").json() == []


async def test_a_taken_name_keeps_the_card_open():
    app = create_app()
    c, user_id, bot_id = _client(app)
    app.state.connector_requests.attach(Turns())
    await _ask(app, user_id, bot_id)
    c.post("/api/connectors", json={"name": "ahrefs", "base_url": "https://api.ahrefs.com", "secret": "k" * 20},
           headers=ORIGIN)
    [row] = c.get("/api/connector-requests").json()
    taken = c.post(f"/api/connector-requests/{row['id']}/save", json={"secret": SECRET}, headers=ORIGIN)
    assert taken.status_code == 422 and taken.json() == {"detail": texts.NAME_TAKEN}
    assert c.get(f"/api/connector-requests/{row['id']}").json()["state"] == "open"


async def test_tool_refusals_and_the_open_cap():
    app = create_app()
    c, user_id, bot_id = _client(app)
    bad_style, _ = await _ask(app, user_id, bot_id, ASK | {"auth_style": "header"})
    assert bad_style.text == texts.BAD_AUTH_NAME
    no_thread = await app.state.turns.domain.run(
        "request_connector", ASK, RecordContext(user_id=user_id, bot_id=bot_id, tainted=False))
    assert no_thread.text == texts.REQUEST_NEEDS_CHAT
    first, _ = await _ask(app, user_id, bot_id)
    again, _ = await _ask(app, user_id, bot_id)
    assert again.text == texts.ALREADY_ASKED.format(service="Ahrefs")
    for n in range(2):
        await _ask(app, user_id, bot_id, ASK | {"service": f"Svc{n}"})
    over, _ = await _ask(app, user_id, bot_id, ASK | {"service": "Svc9"})
    assert over.text == texts.TOO_MANY_REQUESTS
    c.post("/api/connectors", json={"name": "Have", "base_url": "https://api.have.com", "secret": "k" * 20},
           headers=ORIGIN)
    have, _ = await _ask(app, user_id, bot_id, ASK | {"service": "have"})
    assert have.text == texts.ALREADY_HAVE.format(name="Have")


async def test_a_tainted_request_is_marked():
    app = create_app()
    c, user_id, bot_id = _client(app)
    await _ask(app, user_id, bot_id, tainted=True)
    assert c.get("/api/connector-requests").json()[0]["tainted"] is True


async def test_another_users_request_is_404():
    app = create_app()
    c, alice, bot_id = _client(app)
    await _ask(app, alice, bot_id)
    [row] = c.get("/api/connector-requests").json()
    await register_user(load_config(), "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18800") as b:
        assert (await b.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"},
                             headers=ORIGIN)).status_code == 200
        assert (await b.get("/api/connector-requests")).json() == []
        assert (await b.get(f"/api/connector-requests/{row['id']}")).status_code == 404
        assert (await b.post(f"/api/connector-requests/{row['id']}/save", json={"secret": SECRET},
                             headers=ORIGIN)).status_code == 404
        assert (await b.post(f"/api/connector-requests/{row['id']}/decline", headers=ORIGIN)).status_code == 404


async def test_the_card_previews_as_words_and_is_never_replayed():
    from roost.talk.chats import chat_preview
    from roost.talk.turn import _MODEL_KINDS

    app = create_app()
    c, user_id, bot_id = _client(app)
    _, thread_id = await _ask(app, user_id, bot_id)
    [card] = [m for m in await app.state.talk.list_messages(user_id, thread_id) if m.kind == "connector_request"]
    assert chat_preview(card) == ("Add a key · Ahrefs", "card")
    assert "connector_request" not in _MODEL_KINDS
