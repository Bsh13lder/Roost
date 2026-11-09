"""B3 (owner decision 2026-10-23): ``ask_secret_field`` stops the run on a Sign-in card with a masked field, only
when the page in front is on the site and shows a password or code box."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.signin import secret_tool
from roost.talk.instructions import ASK_ONLY_IN_CHAT_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import HELPER_DENIED

from cu_run_helpers import make_cu_rig, run_step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


def test_the_tool_is_a_read_every_bot_has_and_no_helper_gets():
    assert CATALOG["ask_secret_field"].kind == "read" and "ask_secret_field" in HELPER_DENIED
    assert "you never see it" in CATALOG["ask_secret_field"].spec.description


async def test_a_password_box_on_the_site_stops_the_run_on_a_field_card(rig):
    runner = rig.tool_runner()
    said = await run_step(runner, "ask_secret_field", kind="password", site="shop.example", why="to see your orders")
    assert said == secret_tool.ASKED_TEXT.format(kind="password", host="shop.example")
    block = runner.block
    assert block is not None and block.field == "password" and block.sign_in and block.reason == "login"
    assert block.host == "shop.example" and block.url == "https://shop.example/" and block.note == "to see your orders"


async def test_a_whole_address_names_the_site_too(rig):
    runner = rig.tool_runner()
    await run_step(runner, "ask_secret_field", kind="code", site="https://shop.example/login", why="2-step code")
    assert runner.block is not None and runner.block.field == "code"


async def test_another_site_or_no_box_is_refused(rig):
    runner = rig.tool_runner()
    other = await run_step(runner, "ask_secret_field", kind="password", site="bank.example", why="x")
    assert other == secret_tool.OTHER_SITE_TEXT.format(host="shop.example") and runner.block is None
    rig.page.state_name = "jobs"                                      # a page with no password box
    runner = rig.tool_runner()
    none = await run_step(runner, "ask_secret_field", kind="password", site="shop.example", why="x")
    assert none == secret_tool.NO_BOX_TEXT and runner.block is None


async def test_a_run_that_asks_ends_on_a_field_card_with_the_masked_line(cfg):
    import json

    from roost.bots.models import BotPatch
    from roost.gateway.auth import register_user
    from roost.llm.types import ToolCallRequested, TurnDone
    from roost.signin.secret_texts import secret_line
    from roost.stuck.store import StuckStore
    from cu_run_helpers import SHOP, YOUR_MESSAGE
    from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Gela")
    asks = [ToolCallRequested(id="a", name="ask_secret_field",
                              arguments={"kind": "password", "site": "shop.example", "why": "your orders"}),
            TurnDone("tool_use")]
    rig = make_rig(cfg, team_model({"Gela": [asks, say("Waiting.")]}))
    bot = await rig.bots.update(user.id, bot.id, BotPatch(computer="linux"))
    desk = rig.desks.for_bot(bot.id, "linux")
    await desk.start_browser()
    desk.serve_screen(SHOP)
    thread = await rig.talk.create_thread(user.id, bot.id)
    await send(rig, user.id, bot.id, thread.id, YOUR_MESSAGE)
    await wait_idle(rig.runner, timeout=8)
    card = await StuckStore(cfg).open_for_bot(user.id, bot.id)
    assert card is not None and card.sign_in and card.secret_field == "password" and card.host == "shop.example"
    [stuck] = [m for m in await rig.talk.list_messages(user.id, thread.id) if m.kind == "stuck"]
    body = json.loads(stuck.body)
    assert body["secret_field"] == "password" and body["line"] == secret_line("shop.example", "password",
                                                                               "your orders")


async def test_bad_arguments_another_chat_and_mac_brave_are_refused(rig, monkeypatch):
    runner = rig.tool_runner()
    bad = await run_step(runner, "ask_secret_field", kind="passkey", site="shop.example", why="x")
    assert bad == secret_tool.BAD_ARGS_TEXT
    away = rig.tool_runner(cards=False)
    assert await run_step(away, "ask_secret_field", kind="password", site="shop.example", why="x") == \
        ASK_ONLY_IN_CHAT_TEXT
    monkeypatch.setattr(rig.desk, "page", lambda: None)
    mac = rig.tool_runner()
    said = await run_step(mac, "ask_secret_field", kind="password", site="shop.example", why="x")
    assert said == secret_tool.LINUX_ONLY_TEXT and mac.block is None
