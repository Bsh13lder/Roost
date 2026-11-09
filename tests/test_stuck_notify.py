"""A bot announces that it is Stuck once per stay (final review M8, Python half).

``TurnRunner._settle_status`` publishes ``bot_status: stuck`` with an activity text ("Stuck on {host}",
or "Needs your help" for a card with no address) only when the bot enters Stuck. Every Stuck frame (a settle, a run of an already-Stuck bot, a restart) carries the same line,
so a reason is never missing (chat-feel Task 7)."""

from __future__ import annotations

import pytest

from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import PageText
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.stuck.models import CardState
from roost.stuck.store import StuckStore
from roost.stuck.texts import stuck_activity
from team_helpers import frames_so_far, make_bot, make_rig, say, send, team_model, wait_idle

SHOP = "https://shop.example/"
CHALLENGE = PageText(url=SHOP, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture(autouse=True)
def _no_challenge_wait(monkeypatch):
    import roost.talk.tool_runner as tool_runner_module
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _open_shop(call_id: str = "p"):
    return [ToolCallRequested(id=call_id, name="open_page", arguments={"url": SHOP}), TurnDone("tool_use")]


LINE = "Stuck on shop.example: a check that I'm human. Take control to clear it."


def _status_frames(frames: list[dict]) -> list[dict]:
    return [f for f in frames if f["type"] == "bot_status"]


def _stuck_frames(frames: list[dict]) -> list[dict]:
    return [f for f in _status_frames(frames) if f["status"] == "stuck"]


async def _blocked_bot(cfg, user_id, script):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": script}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    return rig, bot, thread


def test_the_activity_names_the_host_or_asks_for_help():
    assert stuck_activity("shop.example") == "Stuck on shop.example"
    assert stuck_activity("") == "Needs your help"


async def test_a_bot_that_gets_stuck_announces_it_with_the_host(cfg, user_id):
    rig, bot, thread = await _blocked_bot(cfg, user_id, [_open_shop()])
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)

    stuck = _stuck_frames(await frames_so_far(sub))
    assert [(f["bot_id"], f["activity"]) for f in stuck] == [(bot.id, LINE)]


async def test_a_bot_that_asks_for_help_without_a_page_says_it_needs_your_help(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        [ToolCallRequested(id="h", name="ask_for_help", arguments={"reason": "approve the payment"}),
         TurnDone("tool_use")],
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, "renew my parking permit")
    await wait_idle(rig.runner, timeout=8)

    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == ["Needs your help: approve the payment. Take control to clear it."]


async def test_a_run_of_an_already_stuck_bot_does_not_announce_it_again(cfg, user_id):
    rig, bot, thread = await _blocked_bot(cfg, user_id, [_open_shop(), say("Yes, I'm waiting for you.")])
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)
    sub = rig.events.subscribe(user_id)

    await send(rig, user_id, bot.id, thread.id, "are you still on it?")
    await wait_idle(rig.runner, timeout=8)

    statuses = _status_frames(await frames_so_far(sub))
    assert statuses[0]["status"] == "on_it" and statuses[-1]["status"] == "stuck"      # the face follows the run
    assert [f["activity"] for f in _stuck_frames(statuses)] == [LINE]                  # with the reason, every time
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.STUCK


async def test_a_settle_that_changes_nothing_publishes_nothing(cfg, user_id):
    rig, bot, thread = await _blocked_bot(cfg, user_id, [_open_shop()])
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)
    sub = rig.events.subscribe(user_id)

    await rig.runner.settle(user_id, bot.id)
    await rig.runner.stop(user_id, bot.id)

    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [LINE, LINE]   # each settle says why
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.STUCK


async def test_a_bot_that_gets_stuck_again_after_its_card_closed_announces_it_again(cfg, user_id):
    rig, bot, thread = await _blocked_bot(cfg, user_id, [_open_shop(), _open_shop("p2")])
    store = StuckStore(cfg)
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)
    card = await store.open_for_bot(user_id, bot.id)
    await store.close(user_id, card.id, CardState.GIVEN_UP)
    await rig.runner.settle(user_id, bot.id)
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.RESTING
    sub = rig.events.subscribe(user_id)

    await send(rig, user_id, bot.id, thread.id, f"try the kettle at {SHOP} once more")
    await wait_idle(rig.runner, timeout=8)

    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [LINE]


async def test_a_bot_that_comes_back_on_duty_with_an_open_card_announces_it(cfg, user_id):
    rig, bot, thread = await _blocked_bot(cfg, user_id, [_open_shop()])
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)
    await rig.runner.set_off_duty(user_id, bot.id, True)
    await rig.runner.settle(user_id, bot.id)
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.OFF_DUTY
    sub = rig.events.subscribe(user_id)

    await rig.runner.set_off_duty(user_id, bot.id, False)
    await wait_idle(rig.runner)

    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [LINE]
