"""Spec step 15 as a story: told once, remembered by the right bot in a later chat."""

from __future__ import annotations

import html

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.scripted_worker import ScriptedWorker
from roost.memory.hooks import MemoryHooks
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from team_helpers import RecordingModel, make_bot, send, wait_idle


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    talk, events = TalkStore(cfg), EventHub(cfg)
    hooks = MemoryHooks(cfg, talk, events, worker=ScriptedWorker())
    brain = RecordingModel(ScriptedTeamModel({}))
    runner = TurnRunner(cfg, BotStore(cfg), talk, events, DeskFactory(cfg), brain, ActivityBoard(), memory=hooks)
    rig = type("R", (), {"talk": talk, "runner": runner})()
    return cfg, user_id, talk, rig, brain


async def _say(world, bot, thread, text):
    cfg, user_id, talk, rig, brain = world
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return brain.requests[-1].system


async def test_anas_birthday_is_captured_in_one_chat_and_recalled_in_a_later_run(world):
    cfg, user_id, talk, _, _ = world
    bot = await make_bot(cfg, user_id, "Scout")
    thread_a = await talk.create_thread(user_id, bot.id)
    await _say(world, bot, thread_a, "Remember that Ana's birthday is in May and she loves orchids")
    notes = [m for m in await talk.list_messages(user_id, thread_a.id) if m.kind == "memory_note"]
    assert len(notes) == 1

    thread_b = await talk.create_thread(user_id, bot.id)
    system = await _say(world, bot, thread_b, "What should I get Ana?")
    line = html.escape("Ana's birthday is in May and she loves orchids", quote=True)
    assert "<memory>" in system
    inside = system.split("<memory>", 1)[1].split("</memory>", 1)[0]
    assert "[about you · " in inside and "· bot] " + line in inside


async def test_a_preference_told_to_one_bot_does_not_reach_another(world):
    cfg, user_id, talk, _, _ = world
    scout, quill = await make_bot(cfg, user_id, "Scout"), await make_bot(cfg, user_id, "Quill")
    await _say(world, scout, await talk.create_thread(user_id, scout.id), "I prefer short answers")
    quill_system = await _say(world, quill, await talk.create_thread(user_id, quill.id), "Hello there Quill")
    scout_system = await _say(world, scout, await talk.create_thread(user_id, scout.id), "Hello again Scout")
    assert "Prefers short answers" not in quill_system
    assert "Prefers short answers" in scout_system
