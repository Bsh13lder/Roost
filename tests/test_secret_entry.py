"""B3 (owner decision 2026-10-23): ``POST /api/stuck/{id}/secret`` types your password or code into the box on the
bot's own computer, and the value is never logged, stored, published, put in a message or in the audit."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import asynccontextmanager

import httpx
import pytest

from roost.bots.models import BotPatch
from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path, init_db
from roost.desk.stuck import Block
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.signin import secret_texts
from roost.stuck.models import CardDraft, CardState
from roost.stuck.store import StuckStore

from cu_run_helpers import SHOP
from team_helpers import make_bot, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
SECRET = "Tr0ub4dor&3-horse"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


class _Seen:
    """Every frame the event hub publishes."""

    def __init__(self, hub) -> None:
        self.frames: list[str] = []
        original = hub.publish

        async def publish(user_id, event):
            self.frames.append(json.dumps(event, default=str))
            return await original(user_id, event)

        hub.publish = publish


async def _app(cfg, *, field: str | None = "password", name: str = "alice", linux: bool = True):
    app = create_app()
    user = await register_user(cfg, name, PASSWORD)
    bot = await make_bot(cfg, user.id, "Gela")
    if linux:
        bot = await app.state.bots.update(user.id, bot.id, BotPatch(computer="linux"))
        desk = app.state.desks.for_bot(bot.id, "linux")
        await desk.start_browser()
        desk.serve_screen(SHOP)
    thread = await app.state.talk.create_thread(user.id, bot.id)
    card = await StuckStore(cfg).open(user.id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, request="sign in", tainted=True, sign_in=True,
        block=Block(reason="login", url="https://shop.example/", host="shop.example", sign_in=True,
                    field=field or "")))
    return app, user, bot, thread, card


@asynccontextmanager
async def _client(app, username: str = "alice"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


def _audit_rows(cfg) -> list[tuple]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT user_id, action, decision, detail FROM audit ORDER BY rowid").fetchall()
    finally:
        con.close()


async def test_your_password_goes_into_the_box_and_nowhere_else(cfg, caplog):
    caplog.set_level(logging.DEBUG)
    app, user, bot, thread, card = await _app(cfg)
    seen = _Seen(app.state.events)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "cleared" and SECRET not in r.text
    desk = app.state.desks.for_bot(bot.id, "linux")
    assert desk.typed_lengths == (len(SECRET),)
    assert [verb for verb, _, _ in desk.inputs] == ["move", "click", "type"]       # the one box, clicked first
    messages = await app.state.talk.list_messages(user.id, thread.id)
    assert secret_texts.typed_line("password") in [m.body.split(" Stay")[0] for m in messages]
    assert all(SECRET not in m.body for m in messages)
    assert all(SECRET not in frame for frame in seen.frames)
    assert SECRET not in caplog.text
    dek = await get_user_dek(cfg, user.id)
    rows = [r for r in _audit_rows(cfg) if r[1] == "secret_typed"]
    assert len(rows) == 1 and rows[0][2] == "do"
    detail = json.loads(decrypt(rows[0][3], dek, user_aad(user.id, "audit:detail")))
    assert detail == {"kind": "password", "length": len(SECRET)}
    con = sqlite3.connect(get_db_path(cfg))
    try:
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in con.execute(f"SELECT * FROM {table}").fetchall():     # nothing stores it, sealed or not
                assert SECRET not in " ".join(str(v) for v in row), table
    finally:
        con.close()


async def test_the_focused_box_takes_it_without_a_click(cfg):
    app, user, bot, thread, card = await _app(cfg)
    page = app.state.desks.for_bot(bot.id, "linux").page()
    page._focused = next(t for t in page.state.targets if t.secret_field)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": "123456"}, headers=ORIGIN)
    assert r.status_code == 200
    assert [verb for verb, _, _ in app.state.desks.for_bot(bot.id, "linux").inputs] == ["type"]


async def test_no_box_or_another_site_is_409_and_the_card_stays_open(cfg):
    app, user, bot, thread, card = await _app(cfg)
    page = app.state.desks.for_bot(bot.id, "linux").page()
    async with _client(app) as client:
        page.state_name = "jobs"                                     # no password box there
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
        assert r.status_code == 409 and r.json()["detail"] == secret_texts.NO_BOX_DETAIL
        page.state_name = "partner"                                  # partner.example
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
        assert r.status_code == 409
        assert r.json()["detail"] == secret_texts.WRONG_PAGE_DETAIL.format(host="shop.example")
    assert (await StuckStore(cfg).get(user.id, card.id)).state is CardState.OPEN
    assert app.state.desks.for_bot(bot.id, "linux").typed_lengths == ()


async def test_while_you_hold_the_computer_it_is_409(cfg):
    app, user, bot, thread, card = await _app(cfg)
    app.state.control.take(bot.id)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
    assert r.status_code == 409 and r.json()["detail"] == secret_texts.HELD_DETAIL


async def test_origin_another_user_a_plain_card_and_a_bad_value(cfg):
    app, user, bot, thread, card = await _app(cfg)
    await register_user(cfg, "bob", PASSWORD)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET})
        assert r.status_code == 403
        for body in ({"value": ""}, {"value": "x" * 257}, {"value": 5}, {"other": "x"}, {"value": "x", "y": 1}):
            r = await client.post(f"/api/stuck/{card.id}/secret", json=body, headers=ORIGIN)
            assert r.status_code == 422 and "x" * 20 not in r.text
        r = await client.post(f"/api/stuck/{card.id}/secret", content=b"not json", headers=ORIGIN)
        assert r.status_code == 422
    async with _client(app, "bob") as other:
        r = await other.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
        assert r.status_code == 404
    plain_app, _, _, _, plain = await _app(cfg, field=None, name="carol")
    async with _client(plain_app, "carol") as client:
        r = await client.post(f"/api/stuck/{plain.id}/secret", json={"value": SECRET}, headers=ORIGIN)
        assert r.status_code == 400 and r.json()["detail"] == secret_texts.NOT_FIELD_CARD_DETAIL


async def test_a_closed_card_is_409(cfg):
    app, user, bot, thread, card = await _app(cfg)
    async with _client(app) as client:
        assert (await client.post(f"/api/stuck/{card.id}/later", headers=ORIGIN)).status_code == 200
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET}, headers=ORIGIN)
    assert r.status_code == 409


async def test_save_in_vault_keeps_the_password_sealed_for_the_cards_site(cfg):
    # owner, 2026-11-08 (docs/plans/2026-11-08-roost-vault-passwords.md V3.1): Save in Vault on the masked field
    from roost.vault.passwords import VaultPasswordStore
    app, user, bot, _, card = await _app(cfg)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET, "save": True}, headers=ORIGIN)
        assert r.status_code == 200 and SECRET not in r.text
        listed = (await client.get("/api/vault/passwords")).json()
    assert [(row["host"], row["username"]) for row in listed] == [("shop.example", "")]
    store = VaultPasswordStore(cfg)
    assert (await store.secret(user.id, listed[0]["id"])).password == SECRET
    con = sqlite3.connect(get_db_path(cfg))
    try:
        assert all(SECRET not in str(v) for row in con.execute("SELECT * FROM vault_passwords") for v in row)
    finally:
        con.close()


async def test_a_code_is_never_saved_even_when_asked(cfg):
    app, _, _, _, card = await _app(cfg, field="code")
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": "123456", "save": True}, headers=ORIGIN)
        assert r.status_code == 200
        assert (await client.get("/api/vault/passwords")).json() == []


async def test_a_full_vault_still_types_and_closes_the_card_and_says_it_was_not_saved(cfg, monkeypatch):
    # security review L4: a save that fails after the typing never leaves the card open or loses the audit row
    from roost.vault import passwords
    app, _, bot, thread, card = await _app(cfg)
    monkeypatch.setattr(passwords, "VAULT_PASSWORDS_MAX", 0)
    async with _client(app) as client:
        r = await client.post(f"/api/stuck/{card.id}/secret", json={"value": SECRET, "save": True}, headers=ORIGIN)
        assert r.status_code == 200 and r.json()["state"] == "cleared"
        assert (await client.get("/api/vault/passwords")).json() == []
    assert [row for row in _audit_rows(cfg) if row[1] == "secret_typed"]
