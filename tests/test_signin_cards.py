"""The Sign-in card (docs/plans/2026-10-22-roost-signin.md): a Linux bot's sign-in Stuck card.

Open sign-in · Check again · Later; "Keep me signed in on this computer?" Yes keeps the login (Vault, kept), No
clears the site after the task; Sign out clears it later. Mac Brave bots keep today's Stuck card. Another user's
card, bot or login is a 404."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

import roost.talk.tool_runner as tool_runner_module
from roost.bots.models import BotPatch
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.signin.texts import LATER_LINE, NEVER_SEES_PASSWORD, kept_sentence
from roost.stuck.models import CardDraft, CardState
from roost.stuck.store import StuckStore
from roost.stuck.texts import stuck_line
from roost.talk.instructions import ASK_ONLY_IN_CHAT_TEXT
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
SHOP = "https://shop.example/account"
REQUEST = "Check my orders"
WALL = PageText(url=SHOP, title="Sign in", text="Sign in to the shop.", truncated=False, status=200,
                password_field=True)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture(autouse=True)
def _no_challenge_wait(monkeypatch):
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _call(call_id: str, name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


async def _linux(store, user_id: str, bot):
    return await store.update(user_id, bot.id, BotPatch(computer="linux"))


@asynccontextmanager
async def _signed_in(app, username: str = "alice"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _app_with_card(cfg, *, linux: bool = True, sign_in: bool = True, name: str = "alice"):
    app = create_app()
    user = await register_user(cfg, name, PASSWORD)
    bot = await make_bot(cfg, user.id, "Scout")
    if linux:
        bot = await _linux(app.state.bots, user.id, bot)
    thread = await app.state.talk.create_thread(user.id, bot.id)
    card = await StuckStore(cfg).open(user.id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, request=REQUEST, tainted=False, sign_in=sign_in,
        block=Block(reason="login", url=SHOP, host=host_of_url(SHOP))))
    return app, user, bot, thread, card


# --- the run side: which card a sign-in page opens ---------------------------------------------------------------

async def _run(cfg, user_id: str, *, linux: bool, steps, serve: bool = True):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": steps}))
    if linux:
        bot = await _linux(rig.bots, user_id, bot)
    if serve:
        rig.desks.for_bot(bot.id, bot.computer).serve(SHOP, WALL)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, REQUEST)
    await wait_idle(rig.runner, timeout=8)
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    messages = await rig.talk.list_messages(user_id, thread.id)
    return card, messages


_SIGN_IN_STEPS = [[_call("p", "open_page", url=SHOP), TurnDone("tool_use")],
                  [_call("s", "request_sign_in", site="shop.example", why="to see your orders"),
                   TurnDone("tool_use")], say("x")]


async def test_a_sign_in_page_alone_opens_no_card(cfg):
    """Owner, 2026-11-03: the page reaches the bot with a note; it signs in itself or asks."""
    user = await register_user(cfg, "alice", PASSWORD)
    card, _ = await _run(cfg, user.id, linux=True,
                         steps=[[_call("p", "open_page", url=SHOP), TurnDone("tool_use")], say("x")])
    assert card is None


async def test_a_linux_bot_that_asks_on_a_sign_in_page_opens_a_sign_in_card(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    card, messages = await _run(cfg, user.id, linux=True, steps=_SIGN_IN_STEPS)
    assert card.sign_in is True and card.reason == "login" and card.host == "shop.example"
    [stuck] = [m for m in messages if m.kind == "stuck"]
    body = json.loads(stuck.body)
    assert body["sign_in"] is True and NEVER_SEES_PASSWORD in body["line"]


async def test_a_mac_brave_bot_keeps_todays_stuck_card(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    card, messages = await _run(cfg, user.id, linux=False, steps=_SIGN_IN_STEPS)
    assert card.sign_in is False and card.reason == "login"
    [stuck] = [m for m in messages if m.kind == "stuck"]
    body = json.loads(stuck.body)
    assert body["sign_in"] is False and body["line"] == stuck_line(card)


async def test_request_sign_in_opens_a_sign_in_card_for_the_named_site(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    card, _ = await _run(cfg, user.id, linux=True, serve=False, steps=[
        [_call("s", "request_sign_in", site="github.com", why="to read your pull requests"), TurnDone("tool_use")],
        say("x")])
    assert card.sign_in is True and card.reason == "login"
    assert (card.host, card.url, card.note) == ("github.com", "https://github.com/", "to read your pull requests")


async def test_ask_for_help_naming_a_sign_in_is_a_sign_in_card_on_linux_only(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    steps = [[_call("o", "open_page", url="https://news.example/"), TurnDone("tool_use")],
             [_call("h", "ask_for_help", reason="Please log in to the news site for me"), TurnDone("tool_use")],
             say("x")]
    linux_card, _ = await _run(cfg, user.id, linux=True, serve=False, steps=steps)
    assert (linux_card.reason, linux_card.sign_in) == ("login", True)
    bob = await register_user(cfg, "bob", PASSWORD)
    mac_card, _ = await _run(cfg, bob.id, linux=False, serve=False, steps=steps)
    assert (mac_card.reason, mac_card.sign_in) == ("asked", False)


async def test_request_sign_in_is_refused_outside_your_own_chat_and_for_a_bad_site(cfg):
    from roost.signin.texts import BAD_SIGN_IN_ARGS_TEXT, SITE_REFUSED_TEXT
    from roost.signin.tool import sign_in_block

    assert sign_in_block({"site": "github.com", "why": "x"}, cards=False) == ASK_ONLY_IN_CHAT_TEXT
    assert sign_in_block({"site": "", "why": "x"}, cards=True) == BAD_SIGN_IN_ARGS_TEXT
    assert sign_in_block({"site": "github.com", "why": "y" * 301}, cards=True) == BAD_SIGN_IN_ARGS_TEXT
    assert sign_in_block({"site": "http://127.0.0.1/admin", "why": "x"}, cards=True) == SITE_REFUSED_TEXT
    block = sign_in_block({"site": "https://GitHub.com/login?next=/pulls", "why": " pull requests "}, cards=True)
    assert isinstance(block, Block) and block.reason == "login" and block.host == "github.com"
    assert block.note == "pull requests"


# --- the buttons ------------------------------------------------------------------------------------------------

async def test_open_sign_in_takes_control_and_opens_the_cards_page(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/open-sign-in", headers=ORIGIN)
    assert r.status_code == 200 and r.json()["sign_in"] is True
    assert app.state.control.held(bot.id) is not None
    assert desk.open_page_calls == [SHOP]


async def test_open_sign_in_leaves_the_page_alone_when_the_computer_is_already_there(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.open_page_calls.append("https://shop.example/login")
    async with _signed_in(app) as c:
        assert (await c.post(f"/api/stuck/{card.id}/open-sign-in", headers=ORIGIN)).status_code == 200
    assert desk.open_page_calls == ["https://shop.example/login"]


async def test_open_sign_in_is_only_for_a_sign_in_card_and_only_yours(cfg):
    app, user, bot, _, card = await _app_with_card(cfg, sign_in=False)
    await register_user(cfg, "bob", PASSWORD)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/open-sign-in", headers=ORIGIN)
        assert r.status_code == 400
    async with _signed_in(app, "bob") as c:
        assert (await c.post(f"/api/stuck/{card.id}/open-sign-in", headers=ORIGIN)).status_code == 404
        assert (await c.post(f"/api/stuck/{card.id}/later", headers=ORIGIN)).status_code == 404
    assert app.state.control.held(bot.id) is None


async def test_later_closes_the_card_and_the_bot_says_it_left_the_site(cfg):
    app, user, bot, thread, card = await _app_with_card(cfg)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/later", headers=ORIGIN)
        again = await c.post(f"/api/stuck/{card.id}/later", headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "given_up" and again.status_code == 409
    lines = [m.body for m in await app.state.talk.list_messages(user.id, thread.id) if m.role == "bot"]
    assert lines[-1] == LATER_LINE.format(host="shop.example")


async def test_check_again_is_try_again_and_asks_nothing_about_keeping(cfg):
    app, user, bot, thread, card = await _app_with_card(cfg)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"how": "try_again"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "cleared"
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()


# --- "Keep me signed in on this computer?" ---------------------------------------------------------------------

async def test_yes_keeps_the_login_in_the_vault_and_tells_the_bot(cfg):
    app, user, bot, thread, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.cookie_domains = (".shop.example",)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me@shop", "keep": True}, headers=ORIGIN)
    assert r.status_code == 200
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert (login.host, login.label, login.kept) == ("shop.example", "me@shop", True)
    [line] = [m for m in await app.state.talk.list_messages(user.id, thread.id) if m.kind == "card_answer"]
    assert line.body.endswith(kept_sentence("shop.example", True))
    assert desk.cleared_hosts == () and desk.cookie_domains == (".shop.example",)


async def test_no_this_time_clears_the_sites_cookies_after_the_task(cfg):
    app, user, bot, thread, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.cookie_domains = (".shop.example", "accounts.shop.example", "other.example")
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"keep": False}, headers=ORIGIN)
        assert r.status_code == 200
    await wait_idle(app.state.turns, timeout=8)
    assert desk.cleared_hosts == ("shop.example",)
    assert desk.cookie_domains == ("other.example",)
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()
    [line] = [m for m in await app.state.talk.list_messages(user.id, thread.id) if m.kind == "card_answer"]
    assert line.body.endswith(kept_sentence("shop.example", False))


async def test_a_pending_clear_waits_while_its_item_is_still_queued(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    thread = await app.state.talk.create_thread(user.id, bot.id)
    await app.state.bots.set_off_duty(user.id, bot.id, True)
    item = await send_item(app, user.id, bot.id, thread.id)
    await app.state.vault_store.remember(user.id, bot.id, "shop.example", "", kept=False, clear_after_item_id=item)
    await app.state.signin.clear_pending(user.id, bot.id)
    assert desk.cleared_hosts == ()
    assert len(await app.state.vault_store.pending_clears(user.id, bot.id)) == 1


async def send_item(app, user_id: str, bot_id: str, thread_id: str) -> str:
    from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

    item = await app.state.turns.submit(user_id, WorkDraft(
        bot_id=bot_id, thread_id=thread_id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body="later"))
    return item.id


async def test_the_boot_sweep_clears_a_finished_tasks_pending_site(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    await StuckStore(cfg).close(user.id, card.id, CardState.CLEARED)    # the card was answered: the task went on
    desk = app.state.desks.for_bot(bot.id, "linux")
    await app.state.vault_store.remember(user.id, bot.id, "shop.example", "", kept=False,
                                         clear_after_item_id="gone-item")
    await app.state.signin.sweep_on_boot()
    assert desk.cleared_hosts == ("shop.example",)
    assert await app.state.vault_store.pending_clears(user.id, bot.id) == ()


async def test_a_failed_clear_keeps_the_pending_row_for_next_time(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.force_unavailable = True
    await app.state.vault_store.remember(user.id, bot.id, "shop.example", "", kept=False, clear_after_item_id="x")
    await app.state.signin.clear_pending(user.id, bot.id)
    assert len(await app.state.vault_store.pending_clears(user.id, bot.id)) == 1


async def test_keep_on_a_mac_brave_stuck_card_changes_nothing_about_keeping(cfg):
    app, user, bot, thread, card = await _app_with_card(cfg, linux=False, sign_in=False)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me", "keep": False}, headers=ORIGIN)
    assert r.status_code == 200
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert login.kept is True and login.clear_after_item_id is None


# --- Vault: Sign out --------------------------------------------------------------------------------------------

async def test_sign_out_clears_the_site_and_removes_the_login(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.cookie_domains = ("shop.example", "keep.example")
    login = await app.state.vault_store.remember(user.id, bot.id, "shop.example", "me")
    async with _signed_in(app) as c:
        r = await c.post(f"/api/bots/{bot.id}/site-logins/{login.id}/sign-out", headers=ORIGIN)
    assert r.status_code == 204
    assert desk.cleared_hosts == ("shop.example",) and desk.cookie_domains == ("keep.example",)
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()


async def test_sign_out_refuses_mac_brave_and_another_users_login(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg, linux=False)
    login = await app.state.vault_store.remember(user.id, bot.id, "shop.example", "me")
    await register_user(cfg, "bob", PASSWORD)
    async with _signed_in(app) as c:
        assert (await c.post(f"/api/bots/{bot.id}/site-logins/{login.id}/sign-out", headers=ORIGIN)).status_code == 400
        assert (await c.post(f"/api/bots/{bot.id}/site-logins/nope/sign-out", headers=ORIGIN)).status_code == 404
    async with _signed_in(app, "bob") as c:
        assert (await c.post(f"/api/bots/{bot.id}/site-logins/{login.id}/sign-out", headers=ORIGIN)).status_code == 404
    assert len(await app.state.vault_store.list_for_bot(user.id, bot.id)) == 1


async def test_sign_out_with_the_computer_unavailable_is_a_503_and_keeps_the_login(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg)
    app.state.desks.for_bot(bot.id, "linux").force_unavailable = True
    login = await app.state.vault_store.remember(user.id, bot.id, "shop.example", "me")
    async with _signed_in(app) as c:
        assert (await c.post(f"/api/bots/{bot.id}/site-logins/{login.id}/sign-out", headers=ORIGIN)).status_code == 503
    assert len(await app.state.vault_store.list_for_bot(user.id, bot.id)) == 1


async def test_the_card_wire_shape_says_sign_in(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    async with _signed_in(app) as c:
        [listed] = (await c.get("/api/stuck")).json()
    assert listed["sign_in"] is True
    assert (await StuckStore(cfg).get(user.id, card.id)).state is CardState.OPEN
