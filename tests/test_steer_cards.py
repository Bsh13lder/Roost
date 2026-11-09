"""Steer risk rule: a message read mid-run never answers an open Ask card; the card stays open and the message
is only context for the run."""

from __future__ import annotations

import asyncio

import pytest

from approval_helpers import make_card_rig
from roost.approvals.models import CardState
from roost.config import load_config
from roost.constants import STEER_TURN_PREFIX
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from team_helpers import make_bot, send, wait_idle
from test_steer_runner import HoldModel


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def test_a_steered_message_leaves_an_open_ask_card_open(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout")
    model = HoldModel([
        [ToolCallRequested(id="c1", name="add_task", arguments={"title": "Call bank"}), TurnDone("tool_use")],
        [TextDelta("Hello."), TurnDone("end_turn")],
        [TextDelta("Noted, yes."), TurnDone("end_turn")],
    ], hold=(2,))
    rig = make_card_rig(cfg, model)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Add a task to call the bank")
    await asyncio.wait_for(wait_idle(rig.runner), 5)
    card = (await rig.store.list_open(user_id))[0]

    await send(rig, user_id, bot.id, thread.id, "hi there")
    await asyncio.wait_for(model.reached[2].wait(), 2)
    await send(rig, user_id, bot.id, thread.id, "yes")
    model.release(2)
    await wait_idle(rig.runner)

    assert model.requests[2].turns[-1].text == STEER_TURN_PREFIX + "yes"
    still = await rig.store.get(user_id, card.id)
    assert still.state is CardState.OPEN
