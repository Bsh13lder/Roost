"""Tool groups in a real run (scripted model): what each step is offered, ``load_tools``, and the switch."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.bots.models import BotPatch
from roost.bots.store import BotStore
from roost.talk.instructions import SCREEN_PROSE
from roost.talk.tool_groups import INDEX_LEAD, LOAD_TOOLS, TOOL_GROUPS
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _offered(request) -> set[str]:
    return {spec.name for spec in request.tools}


async def _run(cfg, user_id, text, script):
    bot = await make_bot(cfg, user_id, "Scout", "helps out")
    rig = make_rig(cfg, team_model({"Scout": script}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return [r for r in rig.model.requests if r.agent == "Scout"]


async def test_a_plain_message_is_offered_the_core_and_the_index(cfg, user_id):
    requests = await _run(cfg, user_id, "hello there", [say("Hi!")])
    offered = _offered(requests[0])
    assert {"remember", "open_page", LOAD_TOOLS} <= offered
    assert "add_task" not in offered and "log_expense" not in offered
    assert INDEX_LEAD in requests[0].system and "add_task" in requests[0].system


async def test_the_request_words_load_their_group_before_the_first_step(cfg, user_id):
    requests = await _run(cfg, user_id, "add a task to call Ana", [say("Added.")])
    offered = _offered(requests[0])
    assert {"add_task", "list_tasks"} <= offered and "log_expense" not in offered


async def test_load_tools_offers_the_group_from_the_next_step(cfg, user_id):
    requests = await _run(cfg, user_id, "hello there", [
        [ToolCallRequested(id="l1", name=LOAD_TOOLS, arguments={"groups": ["money"]}), TurnDone("tool_use")],
        say("Ready."),
    ])
    assert "log_expense" not in _offered(requests[0])
    assert "log_expense" in _offered(requests[1])
    tool_text = [t.text for t in requests[1].turns if t.role == "tool"][-1]
    assert "log_expense" in tool_text


async def test_off_offers_every_tool(cfg, user_id, monkeypatch):
    monkeypatch.setenv("ROOST_TOOL_GROUPS", "off")
    requests = await _run(cfg, user_id, "hello there", [say("Hi!")])
    offered = _offered(requests[0])
    assert {"add_task", "log_expense"} <= offered and LOAD_TOOLS not in offered
    assert INDEX_LEAD not in requests[0].system


# Keeping the cache warm (docs/plans/2026-11-09-roost-tool-groups.md §4, 2026-11-10).

def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _run_in(rig, user_id, bot, thread, text):
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return [r for r in rig.model.requests if r.agent == bot.name]


async def test_load_tools_stays_offered_after_a_group_loads(cfg, user_id):
    """The offered list only grows during a run: load_tools never drops out of its tail."""
    requests = await _run(cfg, user_id, "hello there", [
        _tool("l1", LOAD_TOOLS, groups=sorted(TOOL_GROUPS)), say("Ready."),
    ])
    assert LOAD_TOOLS in _offered(requests[0]) and LOAD_TOOLS in _offered(requests[1])
    assert {"add_task", "log_expense", "create_routine"} <= _offered(requests[1])


async def test_the_groups_a_thread_used_lately_start_loaded_in_its_next_run(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout", "helps out")
    rig = make_rig(cfg, team_model({"Scout": [_tool("t1", "list_tasks", status="all"), say("None."), say("Hi!")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    first = await _run_in(rig, user_id, bot, thread, "what are my tasks?")
    assert "add_task" in _offered(first[0])
    requests = await _run_in(rig, user_id, bot, thread, "hello there")
    assert "add_task" in _offered(requests[-1]) and "log_expense" not in _offered(requests[-1])


async def test_a_group_only_loaded_but_never_used_is_not_preloaded(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout", "helps out")
    rig = make_rig(cfg, team_model({"Scout": [_tool("l1", LOAD_TOOLS, groups=["money"]), say("Ok."), say("Hi!")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await _run_in(rig, user_id, bot, thread, "hello there")
    requests = await _run_in(rig, user_id, bot, thread, "hello again")
    assert "log_expense" not in _offered(requests[-1])


async def _linux_bot(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Gela", "books trips")
    updated = await BotStore(cfg).update(user_id, bot.id, BotPatch(computer="linux"))
    assert updated is not None
    return updated


async def test_a_plain_message_to_a_linux_bot_carries_no_screen_prose(cfg, user_id):
    bot = await _linux_bot(cfg, user_id)
    rig = make_rig(cfg, team_model({"Gela": [say("Hi!")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    [request] = await _run_in(rig, user_id, bot, thread, "hello there")
    assert "click" not in _offered(request)
    for text in SCREEN_PROSE:
        assert text not in request.system
    assert "You have your own computer" in request.system


async def test_browsing_words_put_the_screen_prose_in_the_first_step(cfg, user_id):
    bot = await _linux_bot(cfg, user_id)
    rig = make_rig(cfg, team_model({"Gela": [say("Opening.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    [request] = await _run_in(rig, user_id, bot, thread, "open upwork.com and find jobs")
    assert "click" in _offered(request)
    for text in SCREEN_PROSE:
        assert text in request.system


async def test_loading_the_computer_group_mid_run_brings_the_screen_prose_with_it(cfg, user_id):
    bot = await _linux_bot(cfg, user_id)
    rig = make_rig(cfg, team_model({"Gela": [_tool("l1", LOAD_TOOLS, groups=["computer"]), say("Ready.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    before, after = await _run_in(rig, user_id, bot, thread, "hello there")
    assert all(text not in before.system for text in SCREEN_PROSE)
    assert all(text in after.system for text in SCREEN_PROSE) and "click" in _offered(after)
