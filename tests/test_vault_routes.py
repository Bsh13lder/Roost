"""Give it back with an account, Vault: site logins' list and Forget (Computers 2.0, C2, Task 14)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.stuck.models import CardDraft
from roost.stuck.store import StuckStore
from roost.talk.store import TalkStore
from roost.vault.models import NO_SITE_TEXT
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
GITHUB = "https://www.github.com/login"
REQUEST = "Check my pull requests"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@asynccontextmanager
async def _signed_in(app, username: str = "alice"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _setup(cfg, name="alice", on: str | None = GITHUB):
    app = create_app()
    user = await register_user(cfg, name, PASSWORD)
    bot = await make_bot(cfg, user.id, "Scout")
    if on:
        app.state.desks.for_bot(bot.id, bot.computer).open_page_calls.append(on)
    return app, user, bot


async def _chat_lines(app, user_id, bot_id) -> list[str]:
    thread, _ = await app.state.talk.ensure_main_thread(user_id, bot_id)
    return [m.body for m in await app.state.talk.list_messages(user_id, thread.id) if m.role == "user"]


async def test_give_back_with_an_account_saves_it_and_tells_the_bot(cfg):
    app, user, bot = await _setup(cfg)
    app.state.control.take(bot.id)
    async with _signed_in(app) as c:
        r = await c.request("DELETE", f"/api/bots/{bot.id}/control", json={"account": " work   email "}, headers=O)
    assert r.status_code == 200 and app.state.control.held(bot.id) is None
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert (login.host, login.label) == ("github.com", "work email")
    assert await _chat_lines(app, user.id, bot.id) == ["I signed in on github.com as work email."]


async def test_give_back_without_an_account_saves_and_says_nothing(cfg):
    app, user, bot = await _setup(cfg)
    app.state.control.take(bot.id)
    async with _signed_in(app) as c:
        for body in (None, {"account": None}, {"account": "  "}):
            app.state.control.take(bot.id)
            r = await c.request("DELETE", f"/api/bots/{bot.id}/control", headers=O,
                                **({} if body is None else {"json": body}))
            assert r.status_code == 200
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()
    assert await _chat_lines(app, user.id, bot.id) == []


async def test_clearing_a_stuck_card_with_an_account_puts_it_in_the_continue_line(cfg):
    app, user, bot = await _setup(cfg, on=None)
    thread = await TalkStore(cfg).create_thread(user.id, bot.id)
    url = "https://shop.example/kettle"
    card = await StuckStore(cfg).open(user.id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, request=REQUEST, tainted=False,
        block=Block(reason="login", url=url, host=host_of_url(url), note="")))
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me@shop"}, headers=O)
    assert r.status_code == 200
    [line] = [m for m in await app.state.talk.list_messages(user.id, thread.id) if m.kind == "card_answer"]
    assert line.body.endswith("I signed in on shop.example as me@shop.")
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert (login.host, login.label) == ("shop.example", "me@shop")


async def test_no_site_is_a_400_with_the_plain_sentence(cfg):
    app, user, bot = await _setup(cfg, on=None)
    app.state.control.take(bot.id)
    async with _signed_in(app) as c:
        r = await c.request("DELETE", f"/api/bots/{bot.id}/control", json={"account": "x"}, headers=O)
    assert (r.status_code, r.json()["detail"]) == (400, NO_SITE_TEXT)
    assert app.state.control.held(bot.id) is not None          # nothing was given back by a refused request


async def test_an_over_long_account_is_a_422(cfg):
    app, user, bot = await _setup(cfg)
    async with _signed_in(app) as c:
        r = await c.request("DELETE", f"/api/bots/{bot.id}/control", json={"account": "x" * 101}, headers=O)
        bad = await c.request("DELETE", f"/api/bots/{bot.id}/control", json={"account": "a", "x": 1}, headers=O)
    assert (r.status_code, bad.status_code) == (422, 422)


async def test_list_is_newest_first_and_forget_removes_one(cfg):
    app, user, bot = await _setup(cfg)
    other = await make_bot(cfg, user.id, "Quill")
    store = app.state.vault_store
    older = await store.remember(user.id, bot.id, "github.com", "work")
    await store.remember(user.id, bot.id, "gitlab.com", "play")
    await store.remember(user.id, other.id, "github.com", "quill's")
    async with _signed_in(app) as c:
        listed = (await c.get(f"/api/bots/{bot.id}/site-logins")).json()
        assert [(i["host"], i["label"]) for i in listed] == [("gitlab.com", "play"), ("github.com", "work")]
        assert set(listed[0]) == {"id", "bot_id", "host", "label", "updated_at", "kept"}
        assert (await c.delete(f"/api/bots/{bot.id}/site-logins/{older.id}", headers=O)).status_code == 204
        assert (await c.delete(f"/api/bots/{bot.id}/site-logins/{older.id}", headers=O)).status_code == 404
        assert [i["host"] for i in (await c.get(f"/api/bots/{bot.id}/site-logins")).json()] == ["gitlab.com"]
    assert [l.label for l in await store.list_for_bot(user.id, other.id)] == ["quill's"]


async def test_forget_needs_the_login_to_belong_to_that_bot(cfg):
    app, user, bot = await _setup(cfg)
    other = await make_bot(cfg, user.id, "Quill")
    theirs = await app.state.vault_store.remember(user.id, other.id, "github.com", "q")
    async with _signed_in(app) as c:
        assert (await c.delete(f"/api/bots/{bot.id}/site-logins/{theirs.id}", headers=O)).status_code == 404
    assert len(await app.state.vault_store.list_for_bot(user.id, other.id)) == 1


async def test_another_users_logins_are_404(cfg):
    app, alice, bot = await _setup(cfg)
    login = await app.state.vault_store.remember(alice.id, bot.id, "github.com", "mine")
    await register_user(cfg, "bob", PASSWORD)
    async with _signed_in(app, "bob") as c:
        assert (await c.get(f"/api/bots/{bot.id}/site-logins")).status_code == 404
        assert (await c.delete(f"/api/bots/{bot.id}/site-logins/{login.id}", headers=O)).status_code == 404
        r = await c.request("DELETE", f"/api/bots/{bot.id}/control", json={"account": "x"}, headers=O)
        assert r.status_code == 404
    assert len(await app.state.vault_store.list_for_bot(alice.id, bot.id)) == 1
