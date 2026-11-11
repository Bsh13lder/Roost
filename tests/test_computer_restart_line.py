"""After a self-heal the bot's main chat gets one quiet line (owner, 2026-11-10): "My computer stopped answering, so
I restarted it." The desk's ``on_healed`` hook reaches the runner through ``RoomHooks``; with nobody's run to tell
(no user known for the bot) it says nothing and never raises."""

from __future__ import annotations

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import COMPUTER_RESTARTED_LINE
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from team_helpers import make_bot, team_model


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _rig(cfg):
    talk, events, desks = TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    runner = TurnRunner(cfg, BotStore(cfg), talk, events, desks, team_model({}), ActivityBoard())
    return talk, desks, runner


async def test_the_healed_hook_posts_one_plain_line_in_the_main_chat(cfg, user_id):
    talk, desks, runner = _rig(cfg)
    bot = await make_bot(cfg, user_id, "Gela")
    runner.note_run_user(user_id, bot.id)

    await desks.room_hooks.on_healed(bot.id)

    thread = await talk.main_thread(user_id, bot.id)
    lines = [m for m in await talk.list_messages(user_id, thread.id) if m.kind == "computer_restart"]
    assert [(m.role, m.body) for m in lines] == [("system", COMPUTER_RESTARTED_LINE)]
    assert COMPUTER_RESTARTED_LINE == "My computer stopped answering, so I restarted it."


async def test_with_no_run_to_tell_the_hook_says_nothing(cfg, user_id):
    talk, desks, _runner = _rig(cfg)
    bot = await make_bot(cfg, user_id, "Gela")

    await desks.room_hooks.on_healed(bot.id)

    assert await talk.main_thread(user_id, bot.id) is None
