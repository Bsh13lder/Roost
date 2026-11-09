"""A held computer refuses the bot's browser calls (S1.8)."""

from __future__ import annotations

import pytest

from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.control import ControlLock
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.instructions import CONTROL_HANDED_BACK_TEXT, CONTROL_HELD_TEXT
from roost.talk.runner import TurnRunner
from team_helpers import Rig, make_bot, make_rig, say, send, team_model, until, wait_idle

WAITING = "waiting: you have control of my computer"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _rig_with(cfg, lock: ControlLock, script) -> Rig:
    base = make_rig(cfg, team_model(script))
    runner = TurnRunner(cfg, base.bots, base.talk, base.events, base.desks, base.model, ActivityBoard(), control=lock)
    return Rig(runner=runner, bots=base.bots, talk=base.talk, events=base.events, desks=base.desks, model=base.model)


def _open(call_id: str = "p"):
    return [ToolCallRequested(id=call_id, name="open_page", arguments={"url": "https://example.com"}),
            TurnDone("tool_use")]


async def _run(rig, user_id, bot):
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read https://example.com")
    await wait_idle(rig.runner, timeout=8)
    return [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]


async def test_a_held_computer_refuses_the_bots_open_page(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    lock = ControlLock(wait_seconds=0.05)
    lock.take(bot.id)
    rig = _rig_with(cfg, lock, {"Helper": [_open(), say("waiting for you")]})
    assert await _run(rig, user_id, bot) == [CONTROL_HELD_TEXT]
    assert rig.desks.for_bot(bot.id).open_page_calls == []


async def test_after_give_back_the_waiting_call_is_still_not_performed(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    lock = ControlLock(wait_seconds=5.0)
    lock.take(bot.id)
    rig = _rig_with(cfg, lock, {"Helper": [_open(), say("I'll read it again")]})
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read https://example.com")
    await until(lambda: rig.runner._activity.get(bot.id) == WAITING)   # the call is now waiting on the hold
    lock.give_back(bot.id)
    await wait_idle(rig.runner, timeout=8)
    assert [t.text for t in rig.model.requests[-1].turns if t.role == "tool"] == [CONTROL_HANDED_BACK_TEXT]
    assert "read_page" in CONTROL_HANDED_BACK_TEXT
    assert rig.desks.for_bot(bot.id).open_page_calls == []


def test_no_tool_lets_a_bot_take_control():
    from roost.talk.tool_catalog import CATALOG
    assert not any("control" in name for name in CATALOG)
