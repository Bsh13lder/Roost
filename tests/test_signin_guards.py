"""The Sign-in card's guards (review fixes, docs/plans/2026-10-22-roost-signin.md).

- A tainted run may ask you to sign in only on a site it already has in scope (the open page or its link scope).
- Give it back on a Sign-in card must answer "Keep me signed in on this computer?" (400 without it).
- "No, this time" waits for the whole task: an open Ask, Proposal or options card, or queued work, holds the clear.
- Open sign-in and the clear follow the bot's current computer; a gone bot's pending row is dropped."""

from __future__ import annotations

import pytest

from roost.approvals.models import ApprovalDraft
from roost.bots.models import BotPatch
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.signin.texts import KEEP_ANSWER_NEEDED_DETAIL, SITE_NOT_IN_SCOPE_TEXT
from roost.stuck.models import CardState as StuckState
from roost.stuck.store import StuckStore
from roost.llm.types import TurnDone
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle
from test_signin_cards import ORIGIN, PASSWORD, REQUEST, _app_with_card, _call, _signed_in

NEWS = "https://news.example/"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _linux_run(cfg, user_id: str, steps):
    bot = await make_bot(cfg, user_id, "Helper")
    model = team_model({"Helper": steps})
    rig = make_rig(cfg, model)
    bot = await rig.bots.update(user_id, bot.id, BotPatch(computer="linux"))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, REQUEST)
    await wait_idle(rig.runner, timeout=8)
    return model, bot, thread


# --- FAIL 1: request_sign_in can't launder an off-scope address in a tainted run -------------------------------

async def test_a_tainted_run_cannot_ask_to_sign_in_on_a_site_it_never_saw(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    model, bot, _ = await _linux_run(cfg, user.id, [
        [_call("o", "open_page", url=NEWS), TurnDone("tool_use")],
        [_call("s", "request_sign_in", site="evil.example", why="to read your account"), TurnDone("tool_use")],
        say("x")])
    assert await StuckStore(cfg).open_for_bot(user.id, bot.id) is None
    assert SITE_NOT_IN_SCOPE_TEXT in str(model.requests[-1])     # the refusal is what the model reads


async def test_a_tainted_run_may_ask_to_sign_in_on_the_page_it_has_open(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    _, bot, _ = await _linux_run(cfg, user.id, [
        [_call("o", "open_page", url=NEWS), TurnDone("tool_use")],
        [_call("s", "request_sign_in", site="news.example", why="to read the paywalled story"), TurnDone("tool_use")],
        say("x")])
    card = await StuckStore(cfg).open_for_bot(user.id, bot.id)
    assert card is not None and card.sign_in is True and card.host == "news.example" and card.tainted is True


async def test_a_clean_run_may_still_ask_to_sign_in_on_any_public_site(cfg):
    user = await register_user(cfg, "alice", PASSWORD)
    _, bot, _ = await _linux_run(cfg, user.id, [
        [_call("s", "request_sign_in", site="github.com", why="to read your pull requests"), TurnDone("tool_use")],
        say("x")])
    card = await StuckStore(cfg).open_for_bot(user.id, bot.id)
    assert card is not None and card.host == "github.com"


# --- FAIL 2: Give it back on a Sign-in card must answer Keep me signed in --------------------------------------

async def test_give_it_back_on_a_sign_in_card_without_keep_is_refused_and_the_card_stays_open(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    app.state.desks.for_bot(bot.id, "linux").cookie_domains = ("shop.example",)    # signed in (A1)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={}, headers=ORIGIN)
        assert r.status_code == 400 and r.json()["detail"] == KEEP_ANSWER_NEEDED_DETAIL
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me"}, headers=ORIGIN)
        assert r.status_code == 400
        assert (await c.post(f"/api/stuck/{card.id}/clear", json={"keep": True}, headers=ORIGIN)).status_code == 200
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert login.kept is True


# --- FAIL 3: "No, this time" waits for a parked run -------------------------------------------------------------

async def _pending(app, user_id: str, bot_id: str) -> None:
    """A "No, this time" login whose continue item has finished; the bot's Sign-in card was answered."""
    card = await app.state.stuck.open_for_bot(user_id, bot_id)
    if card is not None:
        await app.state.stuck.close(user_id, card.id, StuckState.CLEARED)
    await app.state.vault_store.remember(user_id, bot_id, "shop.example", "", kept=False,
                                         clear_after_item_id="finished-item")


async def test_a_pending_clear_waits_while_the_bot_has_an_open_ask_card(cfg):
    app, user, bot, thread, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    await _pending(app, user.id, bot.id)
    card = await app.state.approvals.open(user.id, ApprovalDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, kind="ask", steps=(), request="r", tainted=False))
    await app.state.signin.clear_pending(user.id, bot.id)
    assert desk.cleared_hosts == ()
    assert len(await app.state.vault_store.pending_clears(user.id, bot.id)) == 1
    from roost.approvals.models import CardState as AskState
    await app.state.approvals.close(user.id, card.id, AskState.EXPIRED)
    await app.state.signin.clear_pending(user.id, bot.id)
    assert desk.cleared_hosts == ("shop.example",)


async def test_a_pending_clear_waits_while_the_bot_has_queued_work(cfg):
    app, user, bot, thread, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    await _pending(app, user.id, bot.id)
    await app.state.bots.set_off_duty(user.id, bot.id, True)
    from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind
    await app.state.turns.submit(user.id, WorkDraft(
        bot_id=bot.id, thread_id=thread.id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_YOU, body="yes"))
    await app.state.signin.clear_pending(user.id, bot.id)
    assert desk.cleared_hosts == ()


async def test_a_pending_clear_waits_while_the_bot_has_an_open_stuck_card(cfg):
    app, user, bot, thread, _ = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    await _pending(app, user.id, bot.id)
    from roost.desk.stuck import Block
    from roost.stuck.models import CardDraft
    await StuckStore(cfg).open(user.id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, request=REQUEST, tainted=False,
        block=Block(reason="refused", url="https://shop.example/", host="shop.example")))
    await app.state.signin.clear_pending(user.id, bot.id)
    assert desk.cleared_hosts == ()


# --- FAIL 4: the bot's current computer -------------------------------------------------------------------------

async def test_open_sign_in_on_a_bot_now_on_mac_brave_is_refused_and_starts_no_linux_computer(cfg):
    app, user, bot, _, card = await _app_with_card(cfg)
    await app.state.bots.update(user.id, bot.id, BotPatch(computer="mac_brave"))
    linux = app.state.desks.for_bot(bot.id, "linux")
    async with _signed_in(app) as c:
        assert (await c.post(f"/api/stuck/{card.id}/open-sign-in", headers=ORIGIN)).status_code == 400
    assert linux.open_page_calls == [] and app.state.control.held(bot.id) is None


async def test_a_pending_clear_of_a_bot_now_on_mac_brave_waits_and_touches_no_linux_computer(cfg):
    app, user, bot, _, _ = await _app_with_card(cfg)
    linux = app.state.desks.for_bot(bot.id, "linux")
    await _pending(app, user.id, bot.id)
    await app.state.bots.update(user.id, bot.id, BotPatch(computer="mac_brave"))
    await app.state.signin.clear_pending(user.id, bot.id)
    assert linux.cleared_hosts == ()
    assert len(await app.state.vault_store.pending_clears(user.id, bot.id)) == 1


async def test_a_pending_clear_of_a_gone_bot_is_dropped(cfg, monkeypatch):
    app, user, bot, _, _ = await _app_with_card(cfg)
    linux = app.state.desks.for_bot(bot.id, "linux")
    await _pending(app, user.id, bot.id)

    async def gone(_user_id, _bot_id):
        return None

    monkeypatch.setattr(app.state.bots, "get", gone)
    await app.state.signin.sweep_on_boot()
    assert linux.cleared_hosts == ()
    assert await app.state.vault_store.pending_clears(user.id, bot.id) == ()
