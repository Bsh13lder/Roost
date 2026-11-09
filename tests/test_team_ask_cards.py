"""create_bot and set_bot_model (topic team) have a Yes path: an Ask card whose Yes runs the stored call."""

from __future__ import annotations

import json

import pytest

from plan_helpers import call, mode_rig, step
from roost.approvals.models import ApprovalDraft, CardState
from roost.approvals.texts import NOT_ASKABLE_TEXT
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.registry import OPUS
from roost.talk.domain_tools import RecordContext
from roost.talk.team_tools import BAD_CREATE
from team_helpers import make_bot, say, send, wait_idle

SEO = {"name": "HiMap SEO", "job": "Improves HiMap's search ranking", "instructions": "Audit pages."}


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


async def _names(cfg, user_id) -> set[str]:
    return {b.name for b in await BotStore(cfg).list(user_id)}


async def _asked(cfg, user_id, chief, mode, script):
    rig, thread = await mode_rig(cfg, user_id, chief, mode, script)
    await send(rig, user_id, chief.id, thread.id, "make me a bot")
    await wait_idle(rig.runner)
    return rig, thread


async def test_create_bot_in_ask_mode_parks_on_a_card_and_yes_creates_the_stored_bot(cfg, user_id, chief):
    rig, thread = await _asked(cfg, user_id, chief, "ask", [step(call("create_bot", **SEO)), say("Asked."), say("Made.")])
    card = (await rig.store.list_open(user_id))[0]
    assert card.kind == "ask" and card.steps[0].tool == "create_bot" and card.steps[0].topic == "team"
    assert "HiMap SEO" in card.steps[0].title and await _names(cfg, user_id) == {"Chief"}
    answered = await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert answered.state is CardState.APPROVED and await _names(cfg, user_id) == {"Chief", "HiMap SEO"}
    kinds = [m.kind for m in await rig.talk.list_messages(user_id, thread.id)]
    assert "bot_created" in kinds and "approval_result" in kinds


async def test_no_creates_nothing(cfg, user_id, chief):
    rig, _ = await _asked(cfg, user_id, chief, "ask", [step(call("create_bot", **SEO)), say("Asked."), say("Ok.")])
    card = (await rig.store.list_open(user_id))[0]
    await rig.service.answer(user_id, card.id, "no")
    await wait_idle(rig.runner)
    assert await _names(cfg, user_id) == {"Chief"}


async def test_set_bot_model_in_ask_mode_has_a_yes_path(cfg, user_id, chief):
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig, _ = await _asked(cfg, user_id, chief, "ask", [
        step(call("set_bot_model", bot="Scout", model=OPUS.id, effort="high")), say("Asked."), say("Done.")])
    card = (await rig.store.list_open(user_id))[0]
    assert card.steps[0].tool == "set_bot_model" and "Scout" in card.steps[0].title
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override != OPUS.id
    await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert (await BotStore(cfg).get(user_id, scout.id)).model_override == OPUS.id


async def test_a_bad_create_is_refused_with_no_card(cfg, user_id, chief):
    rig, _ = await _asked(cfg, user_id, chief, "ask", [step(call("create_bot", name="")), say("Sorry.")])
    assert await rig.store.list_open(user_id) == ()
    tool_texts = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]
    assert tool_texts == [BAD_CREATE]


async def test_another_bots_card_for_create_bot_is_refused(cfg, user_id, chief):
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig, thread = await mode_rig(cfg, user_id, scout, "ask", [])
    ctx = RecordContext(user_id=user_id, bot_id=scout.id, tainted=False, thread_id=thread.id)
    refused = await rig.runner.domain.prepare("create_bot", dict(SEO), ctx)
    assert isinstance(refused, str) and "main bot" in refused and NOT_ASKABLE_TEXT not in refused


async def test_a_tainted_card_never_creates_a_bot(cfg, user_id, chief):
    rig, thread = await mode_rig(cfg, user_id, chief, "ask", [say("ok")])
    ctx = RecordContext(user_id=user_id, bot_id=chief.id, tainted=False, thread_id=thread.id)
    pending = await rig.runner.domain.prepare("create_bot", dict(SEO), ctx)
    card = await rig.store.open(user_id, ApprovalDraft(
        bot_id=chief.id, thread_id=thread.id, work_item_id=None, kind="ask", steps=(pending,), request="r",
        tainted=True))
    await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert await _names(cfg, user_id) == {"Chief"}
    assert (await rig.store.get(user_id, card.id)).state is CardState.FAILED


async def test_a_plan_with_create_bot_creates_it_on_accept(cfg, user_id, chief):
    rig, _ = await _asked(cfg, user_id, chief, "plan", [step(call("create_bot", **SEO)), say("Ready."), say("Made.")])
    card = (await rig.store.list_open(user_id))[0]
    assert card.kind == "plan" and await _names(cfg, user_id) == {"Chief"}
    await rig.service.answer(user_id, card.id, "accept")
    await wait_idle(rig.runner)
    assert await _names(cfg, user_id) == {"Chief", "HiMap SEO"}
