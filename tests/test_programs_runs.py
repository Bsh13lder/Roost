"""Programs in a real run: a clean run just runs them, a tainted run asks on a card and Yes runs exactly that."""

from __future__ import annotations

import json

import pytest

from approval_helpers import make_card_rig
from roost.approvals.models import BotApproval, CardState
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import ExecResult
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.programs.marks import WorkspaceMarks
from team_helpers import RecordingModel, make_bot, say, send, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _call(name, call_id="p1", **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


def _tool_texts(model):
    return [t.text for request in model.requests for t in request.turns if t.role == "tool"]


async def _rig(cfg, user_id, script, mode="ask"):
    bot = await make_bot(cfg, user_id, "Coder")
    model = RecordingModel(ScriptedTeamModel({"Coder": script}))
    rig = make_card_rig(cfg, model)
    assert await rig.bots.set_approval(user_id, bot.id, BotApproval(mode, frozenset())) is not None
    thread = await rig.talk.create_thread(user_id, bot.id)
    desk = rig.desks.for_bot(bot.id, bot.computer)
    desk.exec_replies = (ExecResult(0, "6\n", "", False, False),)
    return bot, rig, thread, desk, model


async def _program_lines(rig, user_id, thread):
    return [json.loads(m.body) for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "program_activity"]


async def test_a_clean_run_runs_a_program_without_a_card_even_in_ask_every_time(cfg, user_id):
    bot, rig, thread, desk, model = await _rig(
        cfg, user_id, [_call("run_program", command="python3 -c 'print(1+5)'"), say("It is 6.")])
    await send(rig, user_id, bot.id, thread.id, "what is 1+5? compute it")
    await wait_idle(rig.runner)
    assert await rig.store.list_open(user_id) == ()
    assert desk.exec_calls == [(["/bin/sh", "-c", "python3 -c 'print(1+5)'"], 60)]
    assert any("exit code 0" in text and "6" in text for text in _tool_texts(model))
    [line] = await _program_lines(rig, user_id, thread)
    assert line["command"] == "python3 -c 'print(1+5)'" and line["exit_code"] == 0
    assert all("program_activity" not in str(t) and '"op": "run"' not in t.text
               for request in model.requests for t in request.turns)   # the chat line is never replayed


async def test_your_own_chat_runs_a_program_after_web_content_with_no_card(cfg, user_id):
    """Owner, 2026-11-05: only paying asks in your own chat, so a program runs after the bot read a page; the
    workspace is still marked as touched by outside content."""
    bot, rig, thread, desk, model = await _rig(cfg, user_id, [
        _call("open_page", call_id="o1", url="https://example.com/"),
        _call("run_program", command="python3 fetch_like.py", timeout_s=30), say("done")],
        mode="auto_edit")
    await send(rig, user_id, bot.id, thread.id, "read example.com and run my script")
    await wait_idle(rig.runner)
    assert not await rig.store.list_open(user_id)
    assert desk.exec_calls == [(["/bin/sh", "-c", "python3 fetch_like.py"], 30)]
    [line] = await _program_lines(rig, user_id, thread)
    assert line["tainted_basis"] is True
    assert await WorkspaceMarks(cfg).marked(user_id, bot.id)


async def test_your_own_chat_writes_a_file_after_web_content_with_no_card(cfg, user_id):
    bot, rig, thread, desk, model = await _rig(cfg, user_id, [
        _call("open_page", call_id="o1", url="https://example.com/"),
        _call("write_file", path="a.py", text="print(1)\n"), say("ok")],
        mode="auto_edit")
    await send(rig, user_id, bot.id, thread.id, "save what the page says")
    await wait_idle(rig.runner)
    assert not await rig.store.list_open(user_id)
    assert len(await _program_lines(rig, user_id, thread)) == 1
