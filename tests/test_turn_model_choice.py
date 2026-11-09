"""A run uses the bot's chosen model and effort; a new bot runs on the default."""

from __future__ import annotations

import pytest

from roost.bots.models import Avatar, BotDraft
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.registry import DEFAULT_BOT_MODEL, OPUS, SONNET
from roost.llm.scripted import ScriptedModel
from roost.models_check.store import SeenModelStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore


class _Recording:
    def __init__(self):
        self._inner = ScriptedModel()
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        async for event in self._inner.stream(request):
            yield event


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bots = BotStore(cfg)
    bot = await bots.create(user.id, BotDraft(name="Scout", job="j", instructions="", avatar=Avatar("round", "#22c55e", "none")))
    talk = TalkStore(cfg)
    model = _Recording()
    runner = TurnRunner(cfg, bots, talk, EventHub(cfg), DeskFactory(cfg), model, ActivityBoard(),
                        seen_models=SeenModelStore(cfg))
    thread = await talk.create_thread(user.id, bot.id)
    await talk.add_message(user.id, thread.id, "user", "hello")
    return cfg, user.id, bot.id, thread.id, bots, runner, model


async def test_a_run_uses_the_bots_model_and_effort(world):
    _cfg, user, bot, thread, bots, runner, model = world
    await bots.set_model(user, bot, OPUS.id, "max")
    await runner.run_turn(user, bot, thread)
    assert (model.requests[0].model, model.requests[0].effort) == (OPUS.id, "max")


async def test_a_new_bot_runs_on_sonnet_5_5(world):
    _cfg, user, bot, thread, _bots, runner, model = world
    await runner.run_turn(user, bot, thread)
    assert model.requests[0].model == DEFAULT_BOT_MODEL == SONNET.id
    assert model.requests[0].effort is None


async def test_a_seen_model_is_usable_and_a_retired_one_falls_back(world):
    cfg, user, bot, thread, bots, runner, model = world
    await SeenModelStore(cfg).add_new({"claude-new-9": "New 9"})
    await bots.set_model(user, bot, "claude-new-9", None)
    await runner.run_turn(user, bot, thread)
    await bots.set_model(user, bot, "claude-gone-1", None)
    await runner.run_turn(user, bot, thread)
    assert [r.model for r in model.requests] == ["claude-new-9", SONNET.id]
