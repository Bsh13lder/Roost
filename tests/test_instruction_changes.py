"""update_my_instructions (owner, 2026-10-23, A2): in a clean 1:1 run your own message started, a bot changes one
section of its own instructions directly and posts an ``instruction_change`` line with Undo. Undo restores the
text it replaced, by compare-and-swap, so it never overwrites a newer change. Anywhere else the tool is refused and
the bot uses propose_instructions_update."""

from __future__ import annotations

import json

import httpx
import pytest

from roost.bots.instruction_sections import parse_sections
from roost.bots.models import BotPatch
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.instruction_proposals.changes import (
    CHANGE_KIND, InstructionChanges, UndoRefused, replace_section,
)
from roost.instruction_proposals.change_tools import InstructionChangeTools
from roost.instruction_proposals.texts import (
    CHANGED_SINCE, CHANGE_NOT_HERE, UNDO_SPENT, change_done, change_line,
)
from roost.talk.chats import chat_preview
from roost.talk.domain_tools import RecordContext
from roost.talk.instructions import INSTRUCTIONS_TEXT, build_instructions
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, HELPER_DENIED, helper_tool_names
from roost.talk.turn import _MODEL_KINDS
from roost.llm.types import ToolCallRequested, TurnDone
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
OLD = "## What you do\n\nRead the news.\n\n## Tone\n\nLong and warm."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def world(cfg):
    user = (await register_user(cfg, "alice", PASSWORD)).id
    bots = BotStore(cfg)
    bot = await make_bot(cfg, user, "Scout", "reads the news")
    bot = await bots.update(user, bot.id, BotPatch(instructions=OLD))
    talk = TalkStore(cfg)
    thread, _ = await talk.ensure_main_thread(user, bot.id)
    changes = InstructionChanges(bots, talk, EventHub(cfg), cfg)
    return {"user": user, "bot": bot, "bots": bots, "talk": talk, "thread": thread, "changes": changes,
            "tools": InstructionChangeTools(changes)}


def _ctx(w, *, tainted=False, from_routine=False, user_started=True, thread=True):
    return RecordContext(user_id=w["user"], bot_id=w["bot"].id, tainted=tainted, from_routine=from_routine,
                         thread_id=w["thread"].id if thread else None, run_id="run-1", user_started=user_started)


async def _update(w, section="Tone", text="Short and plain.", why="You asked me to be brief.", **kw):
    return await w["tools"].run("update_my_instructions", {"section": section, "new_text": text, "why": why},
                                _ctx(w, **kw))


async def _lines(w):
    return [m for m in await w["talk"].list_messages(w["user"], w["thread"].id) if m.kind == CHANGE_KIND]


# --- the catalog, the prompt and the pure section swap ---------------------------------------------------------

def test_the_tool_is_every_bots_direct_and_never_a_helpers():
    tool = CATALOG["update_my_instructions"]
    assert tool.kind == "write_change" and tool.no_ask and not tool.allowed_when_tainted
    assert "propose_instructions_update" in (tool.tainted_refusal or "")
    assert "update_my_instructions" in EVERY_BOT_TOOLS and "update_my_instructions" in HELPER_DENIED
    assert "update_my_instructions" not in helper_tool_names(EVERY_BOT_TOOLS)
    assert CHANGE_KIND not in _MODEL_KINDS


async def test_every_bots_prompt_says_to_update_and_to_show_its_instructions(world):
    prompt = build_instructions(world["bot"])
    assert INSTRUCTIONS_TEXT in prompt
    assert "update_my_instructions" in INSTRUCTIONS_TEXT and "in full" in INSTRUCTIONS_TEXT


def test_replace_section_changes_only_the_named_section():
    after = replace_section(OLD, "tone", "Short and plain.", name="Scout", job="reads the news")
    sections = parse_sections(after)
    assert sections["tone"] == "Short and plain." and sections["what"] == "Read the news."


# --- the tool --------------------------------------------------------------------------------------------------

async def test_a_clean_user_started_run_changes_the_section_and_posts_a_line(world):
    outcome = await _update(world)
    assert outcome.text == change_done("Tone") and not outcome.failed
    bot = await world["bots"].get(world["user"], world["bot"].id)
    assert parse_sections(bot.instructions)["tone"] == "Short and plain."
    [line] = await _lines(world)
    data = json.loads(line.body)
    assert line.role == "activity" and line.author_bot_id == world["bot"].id
    assert data["section"] == "Tone" and data["before"] == OLD and data["after"] == bot.instructions
    assert data["undone"] is False
    assert chat_preview(line) == (change_line("Tone"), "notice")


@pytest.mark.parametrize("where", [{"tainted": True}, {"from_routine": True}, {"user_started": False},
                                   {"thread": False}])
async def test_it_is_refused_outside_a_clean_run_of_your_own_message(world, where):
    outcome = await _update(world, **where)
    assert outcome.failed and CHANGE_NOT_HERE in outcome.text
    assert (await world["bots"].get(world["user"], world["bot"].id)).instructions == OLD
    assert await _lines(world) == []


@pytest.mark.parametrize("args", [
    {"section": "Hobbies", "new_text": "x", "why": "y"},
    {"section": "Tone", "new_text": "", "why": "y"},
    {"section": "Tone", "new_text": "x"},
])
async def test_bad_arguments_change_nothing(world, args):
    outcome = await world["tools"].run("update_my_instructions", args, _ctx(world))
    assert outcome.failed and outcome.text.startswith("Refused")
    assert (await world["bots"].get(world["user"], world["bot"].id)).instructions == OLD


async def test_a_secret_or_no_change_is_refused(world):
    secret = await _update(world, text="My key is sk-ant-api03-" + "a" * 40)
    assert secret.failed
    await _update(world)
    same = await _update(world)
    assert same.failed and await _lines(world) != []
    assert len(await _lines(world)) == 1


async def test_a_section_name_is_read_loosely(world):
    outcome = await _update(world, section="rules", text="Never share links.")
    assert not outcome.failed
    bot = await world["bots"].get(world["user"], world["bot"].id)
    assert parse_sections(bot.instructions)["rules"] == "Never share links."


# --- Undo ------------------------------------------------------------------------------------------------------

async def test_undo_restores_the_text_it_replaced_once(world):
    await _update(world)
    [line] = await _lines(world)
    undone = await world["changes"].undo(world["user"], line.id)
    assert json.loads(undone.body)["undone"] is True
    assert (await world["bots"].get(world["user"], world["bot"].id)).instructions == OLD
    with pytest.raises(UndoRefused) as spent:
        await world["changes"].undo(world["user"], line.id)
    assert str(spent.value) == UNDO_SPENT


async def test_undo_never_overwrites_a_newer_change(world):
    await _update(world)
    [line] = await _lines(world)
    await world["bots"].update(world["user"], world["bot"].id, BotPatch(instructions="Newer words."))
    with pytest.raises(UndoRefused) as refused:
        await world["changes"].undo(world["user"], line.id)
    assert str(refused.value) == CHANGED_SINCE
    assert (await world["bots"].get(world["user"], world["bot"].id)).instructions == "Newer words."


async def test_undo_finds_only_your_own_change_lines(world, cfg):
    await _update(world)
    [line] = await _lines(world)
    bob = (await register_user(cfg, "bob", PASSWORD)).id
    assert await world["changes"].undo(bob, line.id) is None
    other = await world["talk"].add_message(world["user"], world["thread"].id, role="user", body="hi")
    assert await world["changes"].undo(world["user"], other.id) is None


async def _run(cfg, steps):
    user = (await register_user(cfg, "carol", PASSWORD)).id
    bot = await make_bot(cfg, user, "Helper")
    rig = make_rig(cfg, team_model({"Helper": steps}))
    await rig.bots.update(user, bot.id, BotPatch(instructions=OLD))
    thread = await rig.talk.create_thread(user, bot.id)
    await send(rig, user, bot.id, thread.id, "Be brief from now on.")
    await wait_idle(rig.runner, timeout=8)
    return (await rig.bots.get(user, bot.id)), await rig.talk.list_messages(user, thread.id)


def _call(call_id: str, name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


async def test_a_run_of_your_own_message_changes_the_instructions_directly(cfg):
    bot, messages = await _run(cfg, [
        [_call("u", "update_my_instructions", section="Tone", new_text="Brief.", why="asked"), TurnDone("tool_use")],
        say("Done.")])
    assert parse_sections(bot.instructions)["tone"] == "Brief."
    assert [m.kind for m in messages if m.kind == CHANGE_KIND] == [CHANGE_KIND]


async def test_a_run_that_read_a_page_is_refused_and_told_to_propose(cfg):
    bot, messages = await _run(cfg, [
        [_call("o", "open_page", url="https://news.example/"), TurnDone("tool_use")],
        [_call("u", "update_my_instructions", section="Tone", new_text="Brief.", why="asked"), TurnDone("tool_use")],
        say("Done.")])
    assert bot.instructions == OLD
    assert not [m for m in messages if m.kind == CHANGE_KIND]


async def test_the_undo_route(cfg):
    app = create_app()
    user = await register_user(cfg, "alice", PASSWORD)
    bot = await make_bot(cfg, user.id, "Scout", "reads the news")
    await app.state.bots.update(user.id, bot.id, BotPatch(instructions=OLD))
    thread, _ = await app.state.talk.ensure_main_thread(user.id, bot.id)
    tools = InstructionChangeTools(app.state.instruction_changes)
    ctx = RecordContext(user_id=user.id, bot_id=bot.id, tainted=False, thread_id=thread.id, user_started=True)
    await tools.run("update_my_instructions", {"section": "Tone", "new_text": "Short.", "why": "asked"}, ctx)
    [line] = [m for m in await app.state.talk.list_messages(user.id, thread.id) if m.kind == CHANGE_KIND]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as c:
        assert (await c.post("/api/auth/login", json={"username": "alice", "password": PASSWORD},
                             headers=ORIGIN)).status_code == 200
        r = await c.post(f"/api/instruction-changes/{line.id}/undo", headers=ORIGIN)
        assert r.status_code == 200 and json.loads(r.json()["message"]["body"])["undone"] is True
        again = await c.post(f"/api/instruction-changes/{line.id}/undo", headers=ORIGIN)
        assert again.status_code == 409 and again.json()["detail"] == UNDO_SPENT
        missing = await c.post("/api/instruction-changes/nope/undo", headers=ORIGIN)
        assert missing.status_code == 404
    assert (await app.state.bots.get(user.id, bot.id)).instructions == OLD
