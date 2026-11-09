"""Owner, 2026-11-03: "the bot just does what you ask". In your own 1:1 chat (a run your own message started that can
show a card), a change to your records, a memory, a routine, the bot's model or its instructions runs by the approval
mode as in a clean run, even after the chat read web content (reason ``owner_chat_change``); no model check. Routines,
handoffs, rooms and helpers keep D3's refusal. No real model: scripted fakes only."""

from __future__ import annotations

import pytest

from roost.approvals.models import ApprovalState, BotApproval
from roost.config import load_config
from roost.constants import MAX_TAINTED_CREATES_PER_RUN, NEW_BOT_APPROVAL_MODE
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.gate import Gate, GateContext, judge
from roost.talk.owner_chat import (
    OWNER_CHAT_OWN_TOOLS, OWNER_CHAT_REASON, OWNER_CHAT_RECORD_TOOLS, OWNER_CHAT_TOOLS, owner_chat_run,
)
from roost.talk.tool_catalog import CATALOG
from roost.tasks.service import TaskService
from roost.tasks.store import TaskStore
from approval_helpers import make_card_rig
from team_helpers import make_bot, say, send, team_model, wait_idle

_ARGS = {
    "remember": {"text": "likes wool", "kind": "preference"},
    "update_my_instructions": {"section": "Tone", "new_text": "Short.", "why": "asked"},
    "set_bot_model": {"bot": "Gela", "model": "claude-opus-5-5"},
    "create_routine": {"name": "x", "instructions": "y", "schedule": {"kind": "cron", "expr": "0 9 * * 1"}},
}


def _ctx(mode: str = "auto_edit", **over: object) -> GateContext:
    fields: dict[str, object] = dict(allowed=frozenset(CATALOG), tainted=True, owner_chat=True,
                                     approval=ApprovalState(mode=mode, ask_topics=frozenset(), cards=True))
    fields.update(over)
    return GateContext(**fields)  # type: ignore[arg-type]


def _pair(name: str, ctx: GateContext) -> tuple[str, str]:
    verdict = judge(CATALOG[name], name, _ARGS.get(name, {"task": "x", "routine_id": "r"}), ctx)
    return verdict.decision, verdict.reason


# --- the pure judge ---------------------------------------------------------------------------------------------

def test_the_owner_chat_tools_are_records_and_the_bots_own_things():
    assert {"update_task", "delete_task", "delete_note", "update_project", "forget"} <= OWNER_CHAT_RECORD_TOOLS
    assert OWNER_CHAT_OWN_TOOLS == {"remember", "set_bot_model", "update_my_instructions", "create_routine",
                                    "update_routine", "pause_routine", "resume_routine", "delete_routine"}
    assert OWNER_CHAT_TOOLS == OWNER_CHAT_RECORD_TOOLS | OWNER_CHAT_OWN_TOOLS
    assert all(name in CATALOG for name in OWNER_CHAT_TOOLS)


def test_a_tainted_change_in_your_own_chat_just_runs():
    for name in sorted(OWNER_CHAT_TOOLS):
        assert _pair(name, _ctx()) == ("do", OWNER_CHAT_REASON), name


def test_outside_your_own_chat_it_keeps_d3s_refusal():
    no_cards = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=False)
    for ctx in (_ctx(owner_chat=False), _ctx(approval=no_cards), _ctx(approval=None)):
        assert _pair("delete_task", ctx) == ("never", "tainted_change")
        assert _pair("remember", ctx)[0] == "never"
        assert _pair("update_routine", ctx)[0] == "never"
        assert _pair("set_bot_model", ctx)[0] == "never"
        assert not owner_chat_run(ctx)


def test_the_mode_and_topic_switches_still_rule():
    assert _pair("delete_task", _ctx("ask")) == ("ask", "approval_ask")
    assert _pair("delete_task", _ctx("plan")) == ("plan", "planned")
    topic = ApprovalState(mode="auto_edit", ask_topics=frozenset({"tasks"}), cards=True)
    assert _pair("delete_task", _ctx(approval=topic)) == ("ask", "topic_asks")
    assert _pair("delete_task", _ctx(tainted=False)) == ("do", "auto_edit")


def test_mac_files_keep_their_own_rule():
    assert _pair("mac_rename", _ctx()) == ("never", "tainted_change")
    assert _pair("mac_edit", _ctx()) == ("do", "tainted_mac_edit")


def test_new_bots_start_in_auto_edit_and_a_tainted_run_may_add_many():
    assert NEW_BOT_APPROVAL_MODE == "auto_edit"
    assert MAX_TAINTED_CREATES_PER_RUN == 50


# --- the gate writes the reason ----------------------------------------------------------------------------------

@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _audit(cfg, user_id: str, action: str) -> list[tuple[str, str]]:
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT decision, reason FROM audit WHERE user_id = ? AND action = ? ORDER BY id",
            (user_id, action))).fetchall()
    return [tuple(r) for r in rows]


async def test_the_gate_audits_the_owner_chat_reason(cfg, user_id):
    verdict = await Gate(cfg).decide(user_id, "b1", "delete_task", {"task": "x"}, _ctx())
    assert (verdict.decision, verdict.reason) == ("do", OWNER_CHAT_REASON)
    assert await _audit(cfg, user_id, "delete_task") == [("do", OWNER_CHAT_REASON)]


# --- whole runs: the Gela case, and a memory and a routine after a page ----------------------------------------

def _page() -> ToolCallRequested:
    return ToolCallRequested(id="p", name="open_page", arguments={"url": "https://example.com"})


def _call(tool: str, **args: object) -> ToolCallRequested:
    return ToolCallRequested(id=tool, name=tool, arguments=args)


_TITLE = "Meeting place with Alyssa tomorrow at 2 p.m."


async def _open_titles(cfg, user_id: str) -> list[str]:
    return [t.title for t in await TaskService(TaskStore(cfg), EventHub(cfg)).list(user_id, status="open")]


async def test_the_gela_case_deletes_the_task_with_no_card(cfg, user_id):
    rig = make_card_rig(cfg, team_model({"Gela": [
        [_page(), TurnDone("tool_use")], say("It says hello."),
        [_call("add_task", title=_TITLE), TurnDone("tool_use")], say("Added."),
        [_call("delete_task", task=_TITLE), TurnDone("tool_use")], say("Deleted."),
    ]}))
    bot = await make_bot(cfg, user_id, "Gela")
    await rig.bots.set_approval(user_id, bot.id, BotApproval("auto_edit", frozenset()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    for text in ("read https://example.com", "Remember me the meeting with Alyssa at two p.m.",
                 "Oh, sorry, I mistaked. Can you delete that task?"):
        await send(rig, user_id, bot.id, thread.id, text)
        await wait_idle(rig.runner)
    assert await _audit(cfg, user_id, "delete_task") == [("do", OWNER_CHAT_REASON)]
    assert await _open_titles(cfg, user_id) == []
    assert await rig.store.list_open(user_id) == ()


async def test_remember_and_create_routine_run_after_a_page_in_your_own_chat(cfg, user_id):
    rig = make_card_rig(cfg, team_model({"Gela": [
        [_page(), TurnDone("tool_use")], say("Read."),
        [_call("remember", **_ARGS["remember"]), TurnDone("tool_use")], say("Saved."),
        [_call("create_routine", **_ARGS["create_routine"]), TurnDone("tool_use")], say("Created."),
    ]}))
    bot = await make_bot(cfg, user_id, "Gela")
    await rig.bots.set_approval(user_id, bot.id, BotApproval("auto_edit", frozenset()))
    thread = await rig.talk.create_thread(user_id, bot.id)
    for text in ("read https://example.com", "remember I like wool", "make a routine every Monday at 9"):
        await send(rig, user_id, bot.id, thread.id, text)
        await wait_idle(rig.runner)
    assert await _audit(cfg, user_id, "remember") == [("do", OWNER_CHAT_REASON)]
    assert await _audit(cfg, user_id, "create_routine") == [("do", OWNER_CHAT_REASON)]
    async with db_session(cfg) as db:
        memories = (await (await db.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,)))
                    .fetchone())[0]
        routines = (await (await db.execute("SELECT COUNT(*) FROM routines WHERE user_id = ?", (user_id,)))
                    .fetchone())[0]
    assert (memories, routines) == (1, 1)
