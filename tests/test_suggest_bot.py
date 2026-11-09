"""``suggest_bot`` (D-D): a card, never a bot, until the user clicks."""

from __future__ import annotations

import json

import pytest

from roost.bots.models import Avatar, BotPatch
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.gate import REFUSAL_TEXT
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


CHIEF_LOOK = Avatar("classic", "#8b5cf6", "none")   # violet, so the card must suggest the next colour


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
    await BotStore(cfg).update(user_id, bot.id, BotPatch(avatar=CHIEF_LOOK))   # violet: the first default colour
    await BotStore(cfg).set_primary(user_id, bot.id)
    return await BotStore(cfg).get(user_id, bot.id)


def suggest(call_id: str, **args) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="suggest_bot", arguments=args)


async def _run(cfg, user_id, bot, steps):
    rig = make_rig(cfg, team_model({bot.name: steps}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "I keep tracking expenses by hand")
    await wait_idle(rig.runner)
    tool_texts = [t.text for r in rig.model.requests for t in r.turns if t.role == "tool"]
    return rig, thread, tool_texts


async def _bot_count(cfg, user_id):
    async with db_session(cfg) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM bots WHERE user_id = ?", (user_id,))).fetchone())[0]


async def test_the_main_bot_shows_a_card_and_nothing_is_created(cfg, user_id, chief):
    rig, thread, tool_texts = await _run(cfg, user_id, chief, [
        [suggest("s1", name="Ledger", job="Keeps the books", shape="wide"), TurnDone("tool_use")],
        say("I suggested Ledger."),
    ])
    [card] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "suggestion"]
    assert (card.role, card.author_bot_id, card.tainted) == ("bot", chief.id, False)
    assert json.loads(card.body) == {
        "name": "Ledger", "job": "Keeps the books",
        "avatar": {"shape": "wide", "color": "#3b82f6", "badge": "none", "screen": "glow"},   # Chief wears violet
    }
    assert tool_texts == ["Shown a card suggesting Ledger. "
                          "Nothing is created until the user clicks Create this bot."]
    assert await _bot_count(cfg, user_id) == 1


async def test_a_card_from_a_run_that_read_a_page_is_stored_tainted(cfg, user_id, chief):
    """The card's job text becomes lasting prompt text on one click, so a
    card from a tainted run must say so (spec §8.2)."""
    rig, thread, _ = await _run(cfg, user_id, chief, [
        [ToolCallRequested(id="p", name="open_page", arguments={"url": "https://example.com"}), TurnDone("tool_use")],
        [suggest("s1", name="Ledger", job="Keeps the books"), TurnDone("tool_use")],
        say("I suggested Ledger."),
    ])
    [card] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "suggestion"]
    assert card.tainted is True


async def test_a_card_is_never_fed_back_to_the_model(cfg, user_id, chief):
    rig, thread, _ = await _run(cfg, user_id, chief, [
        [suggest("s1", name="Ledger", job="Keeps the books"), TurnDone("tool_use")], say("done"),
    ])
    await send(rig, user_id, chief.id, thread.id, "thanks")
    await wait_idle(rig.runner)
    last = rig.model.requests[-1]
    assert not any('"avatar"' in t.text for t in last.turns if t.role in ("user", "assistant"))


async def test_bad_arguments_or_a_taken_name_are_refused_without_a_card(cfg, user_id, chief):
    rig, thread, tool_texts = await _run(cfg, user_id, chief, [
        [suggest("s1", name="Ledger", job="books", color="red"),
         suggest("s2", name="Chief", job="a second chief"), TurnDone("tool_use")],
        say("ok"),
    ])
    assert tool_texts == [
        "Refused: suggest_bot needs a name (letters, numbers, spaces, . or -, up to 40), a one-line job, "
        "and optionally a shape (mochi, loaf, gumdrop, pebble, bun, acorn, marsh, dumpling, muffs, squish, cub, sprout, "
        "cheeky, tower, helmet, bell, puck, pod), a role (general, tasks, code, seo, money, social, research, writer), "
        "a screen (glow, pixel, signal) and a #RRGGBB color.",
        "Refused: a bot named Chief is already on the team.",
    ]
    assert [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "suggestion"] == []


async def test_at_most_three_suggestions_per_run(cfg, user_id, chief):
    calls = [suggest(f"s{n}", name=f"Helper {n}", job="helps") for n in range(4)]
    rig, thread, tool_texts = await _run(cfg, user_id, chief, [[*calls, TurnDone("tool_use")], say("ok")])
    assert tool_texts[-1] == "Refused: at most 3 suggestions per run."
    assert len([m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "suggestion"]) == 3


async def test_a_bot_that_is_not_the_main_bot_cannot_suggest(cfg, user_id, chief):
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig, thread, tool_texts = await _run(cfg, user_id, scout, [
        [suggest("s1", name="Ledger", job="books"), TurnDone("tool_use")], say("ok"),
    ])
    assert tool_texts == [REFUSAL_TEXT]
    assert "suggest_bot" not in [spec.name for spec in rig.model.requests[0].tools]


