"""suggest_model (an Ask card) and set_bot_model (the main bot, your own chat, clean runs only)."""

from __future__ import annotations

import json

import pytest

from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.bots.store import BotStore
from roost.events.hub import EventHub
from roost.llm.registry import HAIKU, OPUS, SONNET, FABLE, pickable_model_ids
from roost.llm.types import ToolCallRequested, TurnDone
from roost.models_check.store import SeenModelStore
from roost.talk.instructions import Teammate, build_instructions
from roost.talk.model_tools import ModelTools
from roost.talk.store import TalkStore
from roost.talk.team_tools import RunScope
from team_helpers import ask, make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def chief(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Chief", "leads the team")
    await BotStore(cfg).set_primary(user_id, bot.id)
    return await BotStore(cfg).get(user_id, bot.id)


@pytest.fixture
async def scout(cfg, user_id, chief):
    return await make_bot(cfg, user_id, "Scout", "finds prices")


def call(name: str, call_id: str = "m1", **args) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=args)


async def _run(cfg, user_id, bot, steps, text="use a stronger model for Scout", extra=None):
    scripts = {bot.name: steps, **(extra or {})}
    rig = make_rig(cfg, team_model(scripts))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    last = [r for r in rig.model.requests if r.agent == bot.name][-1]
    texts = [t.text for t in last.turns if t.role == "tool"]
    return rig, thread, texts


async def _cards(rig, user_id, thread):
    return [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "model_suggestion"]


async def _audit(cfg, user_id, action):
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT decision, reason FROM audit WHERE user_id = ? AND action = ?", (user_id, action))).fetchall()
    return [tuple(r) for r in rows]


async def test_suggest_model_posts_an_ask_card_and_changes_nothing(cfg, user_id, chief, scout):
    rig, thread, texts = await _run(cfg, user_id, chief, [
        [call("suggest_model", bot="Scout", model=OPUS.id, effort="high", reason="Long research needs it"),
         TurnDone("tool_use")], say("I suggested Opus.")])
    [card] = await _cards(rig, user_id, thread)
    assert (card.role, card.author_bot_id, card.tainted) == ("bot", chief.id, False)
    assert json.loads(card.body) == {"bot_id": scout.id, "bot": "Scout", "model": OPUS.id, "label": OPUS.label,
                                     "effort": "high", "reason": "Long research needs it"}
    assert "Nothing changes" in texts[0]
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override is None
    assert not any("Long research" in t.text for t in rig.model.requests[-1].turns if t.role in ("user", "assistant"))


async def test_suggest_model_refuses_an_unknown_bot_or_the_same_choice(cfg, user_id, chief, scout):
    await BotStore(cfg).set_model(user_id, scout.id, OPUS.id, None)
    rig, thread, texts = await _run(cfg, user_id, chief, [
        [call("suggest_model", "a", bot="Nobody", model=OPUS.id, reason="r"),
         call("suggest_model", "b", bot="Scout", model=OPUS.id, reason="r"),
         call("suggest_model", "d", bot="Scout", model="claude-nope-1", reason="r"),
         call("suggest_model", "e", bot="Scout", model=SONNET.id, reason=""), TurnDone("tool_use")], say("ok")])
    assert texts[0] == "Refused: there is no teammate named Nobody."
    assert texts[1] == "Refused: Scout already runs on Opus 5.5."
    assert texts[2] == "That model isn't available."
    assert texts[3].startswith("Refused: suggest_model needs")
    assert await _cards(rig, user_id, thread) == []


async def test_a_card_from_a_tainted_run_is_stored_tainted(cfg, user_id, chief, scout):
    rig, thread, _ = await _run(cfg, user_id, chief, [
        [call("open_page", "p", url="https://example.com"), TurnDone("tool_use")],
        [call("suggest_model", bot="Scout", model=FABLE.id, reason="r"), TurnDone("tool_use")], say("ok")])
    [card] = await _cards(rig, user_id, thread)
    assert card.tainted is True


async def test_set_bot_model_switches_and_posts_a_quiet_line(cfg, user_id, chief, scout):
    rig, thread, texts = await _run(cfg, user_id, chief, [
        [call("set_bot_model", bot="Scout", model="Opus 5.5", effort="max"), TurnDone("tool_use")], say("Done.")])
    bot = await BotStore(cfg).get(user_id, scout.id)
    assert (bot.model_override, bot.effort) == (OPUS.id, "max")
    assert texts == ["Switched Scout to Opus 5.5 at max effort."]
    lines = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "model_switched"]
    assert [(m.role, m.body) for m in lines] == [("activity", "Switched Scout to Opus 5.5 at max effort")]
    assert [r[0] for r in await _audit(cfg, user_id, "set_bot_model")] == ["do"]


async def test_set_bot_model_is_refused_after_web_content(cfg, user_id, chief, scout):
    rig, thread, texts = await _run(cfg, user_id, chief, [
        [call("open_page", "p", url="https://example.com"), TurnDone("tool_use")],
        [call("set_bot_model", bot="Scout", model=OPUS.id), TurnDone("tool_use")], say("ok")])
    assert "outside content" in texts[1]
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override is None
    assert await _audit(cfg, user_id, "set_bot_model") == [("never", "tainted_change")]


async def test_only_the_main_bot_in_your_own_chat_gets_set_bot_model(cfg, user_id, chief, scout):
    # another bot: neither tool is offered
    rig, _, _ = await _run(cfg, user_id, scout, [say("hi")])
    assert not {"set_bot_model", "suggest_model"} & {s.name for s in rig.model.requests[0].tools}
    # the main bot, but in a handoff: it may suggest, not switch
    rig, _, texts = await _run(cfg, user_id, scout, [[ask("a", "Chief", "switch Scout to Opus"), TurnDone("tool_use")],
                                                       say("asked")],
                               extra={"Chief": [[call("set_bot_model", bot="Scout", model=OPUS.id),
                                                 TurnDone("tool_use")], say("could not")]})
    chief_request = [r for r in rig.model.requests if r.agent == "Chief"][0]
    assert "set_bot_model" not in {s.name for s in chief_request.tools}
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override is None
    # the main bot in your own chat is offered both
    rig, _, _ = await _run(cfg, user_id, chief, [say("hi")])
    assert {"set_bot_model", "suggest_model"} <= {s.name for s in rig.model.requests[0].tools}


async def test_a_room_run_refuses_set_bot_model(cfg, user_id, chief, scout):
    tools = _tools(cfg, chief, in_room=True, user_started=True)
    out = await tools.set_bot_model({"bot": "Scout", "model": OPUS.id}, tainted=False)
    assert out.text.startswith("Refused: ")
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override is None
    assert (await tools.suggest_model({"bot": "Scout", "model": OPUS.id, "reason": "r"}, tainted=False)
            ).text.startswith("Refused: ")


async def test_the_main_bot_can_set_haiku(cfg, user_id, chief, scout):
    thread = await TalkStore(cfg).create_thread(user_id, chief.id)
    tools = _tools(cfg, chief, user_started=True, thread_id=thread.id)
    assert HAIKU.id in pickable_model_ids()
    assert (await tools.set_bot_model({"bot": "Scout", "model": "Haiku"}, tainted=False)).text == "Switched Scout to Haiku 5.5."


async def test_a_newly_seen_model_can_be_picked(cfg, user_id, chief, scout):
    await SeenModelStore(cfg).add_new({"claude-opus-6": "Opus 6"})
    thread = await TalkStore(cfg).create_thread(user_id, chief.id)
    tools = _tools(cfg, chief, user_started=True, thread_id=thread.id)
    out = await tools.set_bot_model({"bot": "Scout", "model": "Opus 6"}, tainted=False)
    assert out.text == "Switched Scout to Opus 6."


def test_the_main_bots_roster_shows_each_model_and_effort(chief):
    mates = (Teammate("Scout", "finds prices", False, model="Opus 5.5, high effort"),
             Teammate("Ledger", "books", False, model="Sonnet 5.5, default effort"))
    prompt = build_instructions(chief, teammates=mates, can_create=True)
    assert "- Scout: finds prices · Opus 5.5, high effort" in prompt
    assert "- Ledger: books · Sonnet 5.5, default effort" in prompt
    assert "suggest_model" in prompt and "set_bot_model" in prompt
    assert "set_bot_model" not in build_instructions(chief, teammates=mates, can_create=False)


async def test_the_roster_is_built_from_each_bots_model_and_effort(cfg, user_id, chief, scout):
    await BotStore(cfg).set_model(user_id, scout.id, OPUS.id, "high")
    rig, _, _ = await _run(cfg, user_id, chief, [say("hi")])
    assert "- Scout: finds prices · Opus 5.5, high effort" in rig.model.requests[0].system


def _tools(cfg, bot, *, in_room=False, user_started=False, thread_id="t"):
    scope = RunScope(user_id=bot.user_id, bot=bot, thread_id=thread_id, in_room=in_room, user_started=user_started)
    return ModelTools(scope, bots=BotStore(cfg), talk=TalkStore(cfg), events=EventHub(cfg),
                      seen=SeenModelStore(cfg))
