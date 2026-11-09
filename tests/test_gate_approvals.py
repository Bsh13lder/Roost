"""The gate's ask and plan verdicts, topic switches and hard floor (approvals plan Task 3, security review a)."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from roost.approvals import floor, topics
from roost.approvals.models import ApprovalState
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT, PLAN_FULL_TEXT
from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import APPROVAL_PLAN_MAX_STEPS, CU_FREE_ACT_TOOLS, MAC_WRITES_PER_RUN
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolSpec
from roost.talk.gate import Gate, GateContext, judge
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef

_EMPTY = {"type": "object", "properties": {}}


def _tool(name: str, kind: str) -> ToolDef:
    return ToolDef(ToolSpec(name, name, _EMPTY), kind)


_FAKE = MappingProxyType({
    **CATALOG,
    "mac_read": _tool("mac_read", "read"),
    "mac_find": _tool("mac_find", "read"),
    "mac_edit": _tool("mac_edit", "write_change"),
    "mac_rename": _tool("mac_rename", "write_change"),
    "post_message": _tool("post_message", "write_create"),
    "wire_money": _tool("wire_money", "write_change"),
})
_ALL = frozenset(_FAKE)
_MODES = ("ask", "auto_edit", "plan")


@pytest.fixture(autouse=True)
def fake_topics(monkeypatch):
    monkeypatch.setattr(topics, "TOOL_TOPICS", {
        **topics.TOOL_TOPICS,
        "mac_read": "files", "mac_find": "files", "mac_edit": "files", "mac_rename": "files",
        "post_message": "posting", "wire_money": "money",
    })
    monkeypatch.setattr(topics, "FLOOR_TOOLS", {"wire_money": "money_move"})


def _state(mode="auto_edit", **kw) -> ApprovalState:
    return ApprovalState(mode=mode, ask_topics=kw.pop("ask_topics", frozenset()), cards=kw.pop("cards", True), **kw)


def _judge(name, args=None, *, mode="auto_edit", tainted=False, creates=0, approval="state", **kw):
    state = _state(mode, **kw) if approval == "state" else approval
    ctx = GateContext(allowed=_ALL, tainted=tainted, creates=creates, approval=state)
    return judge(_FAKE.get(name), name, args or {}, ctx)


def _pair(v):
    return v.decision, v.reason


def test_every_write_tool_has_a_topic(monkeypatch):
    monkeypatch.undo()
    for name, tool in CATALOG.items():
        if tool.no_ask:
            assert name not in topics.TOOL_TOPICS, name   # it leaves the decision to its own card or question
        elif tool.kind in ("write_create", "write_change"):
            assert name in topics.TOOL_TOPICS, name
        elif tool.kind == "act" and name in CU_FREE_ACT_TOOLS:
            assert topics.topic_of(name) is None, name     # open_app is free inside the bot's computer (D1)
        elif tool.kind == "act":
            assert topics.topic_of(name) == "browsing", name
        else:
            assert topics.topic_of(name) is None or name in ("mac_find", "mac_read"), name
    # Install an app: installing or removing a package on the bot's computer always asks.
    assert topics.FLOOR_TOOLS == {"install_app": "install_app", "remove_app": "install_app"}
    assert topics.RELAX_TAINTED_TOOLS == frozenset({"mac_edit"})
    assert topics.topic_of("not_a_tool") is None


def test_every_act_tool_has_a_topic(monkeypatch):
    """C3: every click or key tool belongs to Browsing actions, so its switch covers all of them."""
    monkeypatch.undo()
    from roost.constants import CU_ACT_TOOLS, CU_TOOLS

    for name in CU_ACT_TOOLS:
        assert topics.topic_of(name) == "browsing", name
    for name in set(CU_TOOLS) - CU_ACT_TOOLS:
        assert topics.topic_of(name) is None, name


def test_no_state_keeps_todays_verdicts():
    for name, tool in _FAKE.items():
        if tool.kind == "act":   # C3: judged only on a page resolution (tests/test_cu_gate.py)
            continue
        if tool.asks_always:     # a connector write or an app never runs without a card (tests/test_connector_gate.py)
            assert _pair(_judge(name, approval=None)) == ("never", "needs_your_ok"), name
            if tool.read_when is not None:
                assert _pair(_judge(name, {"method": "GET"}, approval=None)) == ("do", "allowed"), name
            continue
        if tool.own_settings:    # set_my_voice: only your own 1:1 chat changes a bot's settings with no card
            assert _pair(_judge(name, approval=None)) == ("never", "needs_your_ok"), name   # (tests/test_voice_tool.py)
            continue
        assert _pair(_judge(name, approval=None)) == ("do", "allowed"), name
    assert _pair(_judge("add_task", approval=None, tainted=True)) == ("do", "tainted_create")
    assert _pair(_judge("update_task", approval=None, tainted=True)) == ("never", "tainted_change")
    assert _pair(_judge("mac_edit", approval=None, tainted=True)) == ("never", "tainted_change")


def test_ask_mode_asks_for_every_write_and_never_for_a_read():
    assert _pair(_judge("add_task", mode="ask")) == ("ask", "approval_ask")
    assert _pair(_judge("update_task", mode="ask")) == ("ask", "approval_ask")
    assert _pair(_judge("list_tasks", mode="ask")) == ("do", "allowed")
    assert _pair(_judge("get_time", mode="ask")) == ("do", "allowed")


def test_auto_edit_does_ordinary_writes():
    assert _pair(_judge("add_task")) == ("do", "auto_edit")
    assert _pair(_judge("delete_note")) == ("do", "auto_edit")
    assert _pair(_judge("add_task", tainted=True)) == ("do", "tainted_create")


def test_a_topic_switch_asks_even_in_auto_edit_and_plan():
    on = frozenset({"money"})
    for mode in ("auto_edit", "plan"):
        assert _pair(_judge("log_expense", mode=mode, ask_topics=on)) == ("ask", "topic_asks")
        assert _judge("add_task", mode=mode, ask_topics=on).decision != "ask"
    assert _pair(_judge("log_expense", mode="ask", ask_topics=on)) == ("ask", "approval_ask")


def test_plan_mode_plans_writes_up_to_the_cap():
    assert _pair(_judge("add_task", mode="plan")) == ("plan", "planned")
    assert _pair(_judge("add_task", mode="plan", plan_steps=APPROVAL_PLAN_MAX_STEPS - 1)) == ("plan", "planned")
    full = _judge("add_task", mode="plan", plan_steps=APPROVAL_PLAN_MAX_STEPS)
    assert _pair(full) == ("never", "plan_full") and full.text == PLAN_FULL_TEXT
    assert _pair(_judge("list_tasks", mode="plan")) == ("do", "allowed")


@pytest.mark.parametrize("mode", _MODES)
def test_the_hard_floor_asks_in_every_mode(mode):
    secret = _judge("add_note", {"text": "my key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"}, mode=mode)
    nested = _judge("add_note", {"items": [{"deep": ["sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"]}]}, mode=mode)
    posting = _judge("post_message", mode=mode)
    listed = _judge("wire_money", mode=mode)
    mass = _judge("mac_edit", mode=mode, mac_writes=MAC_WRITES_PER_RUN)
    for verdict in (secret, nested, posting, listed, mass):
        assert _pair(verdict) == ("ask", "hard_floor")
    # a topic switch or a plan cap never turns a floor call into something else
    assert _judge("add_note", {"text": "hello"}, mode=mode).reason != "hard_floor"
    assert _judge("mac_edit", mode=mode, mac_writes=MAC_WRITES_PER_RUN - 1).reason != "hard_floor"


def test_the_floor_kinds_are_named():
    state = _state()
    assert floor.hard_floor("post_message", {}, state) == "posting"
    assert floor.hard_floor("wire_money", {}, state) == "money_move"
    assert floor.hard_floor("add_note", {"text": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"}, state) == "secret"
    assert floor.hard_floor("mac_edit", {}, _state(mac_writes=MAC_WRITES_PER_RUN)) == "mass_edit"
    assert floor.hard_floor("add_note", {"text": "plain", "n": 4}, state) is None


@pytest.mark.parametrize("mode", _MODES)
def test_tainted_change_stays_refused_in_ask_mode_and_for_records_in_every_mode(mode):
    for name in ("update_task", "delete_note", "mac_rename", "forget"):
        assert _pair(_judge(name, mode=mode, tainted=True)) == ("never", "tainted_change"), (name, mode)
    assert _pair(_judge("mac_edit", mode="ask", tainted=True)) == ("never", "tainted_change")


def test_tainted_mac_edit_is_relaxed_only_in_auto_edit_and_plan():
    assert _pair(_judge("mac_edit", mode="ask", tainted=True)) == ("never", "tainted_change")
    assert _pair(_judge("mac_edit", mode="auto_edit", tainted=True)) == ("do", "tainted_mac_edit")
    assert _pair(_judge("mac_edit", mode="plan", tainted=True)) == ("plan", "planned")
    for mode in _MODES:
        assert _pair(_judge("mac_rename", mode=mode, tainted=True)) == ("never", "tainted_change")


def test_a_relaxed_tainted_mac_edit_still_meets_the_floor_and_topic_switch():
    assert _pair(_judge("mac_edit", mode="auto_edit", tainted=True, mac_writes=MAC_WRITES_PER_RUN)) == ("ask", "hard_floor")
    assert _pair(_judge("mac_edit", mode="auto_edit", tainted=True, ask_topics=frozenset({"files"}))) == ("ask", "topic_asks")


def test_a_mac_read_asks_unless_its_folder_has_a_session_ok_and_the_run_is_clean():
    assert _pair(_judge("mac_read", {"folder": "Notes"}, mode="auto_edit")) == ("ask", "mac_read_asks")
    assert _pair(_judge("mac_find", {"folder": "Notes"}, mode="plan")) == ("ask", "mac_read_asks")
    ok = frozenset({"notes"})
    assert _pair(_judge("mac_read", {"folder": "NOTES"}, session_folders=ok)) == ("do", "allowed")
    assert _pair(_judge("mac_read", {"folder": "Other"}, session_folders=ok)) == ("ask", "mac_read_asks")
    assert _pair(_judge("mac_read", {"folder": "Notes"}, session_folders=ok, tainted=True)) == ("ask", "mac_read_asks")
    assert _pair(_judge("mac_read", {}, session_folders=ok)) == ("ask", "mac_read_asks")
    assert _pair(_judge("mac_read", {"folder": ["Notes"]}, session_folders=ok)) == ("ask", "mac_read_asks")


def test_ask_or_plan_outside_your_own_chat_is_refused():
    for mode in ("ask", "plan"):
        verdict = _judge("add_task", mode=mode, cards=False)
        assert _pair(verdict) == ("never", "needs_your_ok") and verdict.text == NEEDS_YOUR_OK_TEXT
    for mode in _MODES:
        assert _pair(_judge("post_message", mode=mode, cards=False)) == ("never", "needs_your_ok")
        assert _pair(_judge("mac_read", {"folder": "x"}, mode=mode, cards=False)) == ("never", "needs_your_ok")
    assert _pair(_judge("add_task", mode="auto_edit", cards=False)) == ("do", "auto_edit")
    assert _pair(_judge("list_tasks", mode="ask", cards=False)) == ("do", "allowed")
    on = frozenset({"money"})
    assert _pair(_judge("log_expense", mode="auto_edit", cards=False, ask_topics=on)) == ("never", "needs_your_ok")


def test_unknown_or_unallowed_names_stay_never_with_a_state():
    ctx = GateContext(allowed=frozenset({"get_time"}), approval=_state("ask"))
    assert _pair(judge(_FAKE["add_task"], "add_task", {}, ctx)) == ("never", "not_allowed")
    assert _pair(judge(None, "zzz", {}, ctx)) == ("never", "not_allowed")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await BotStore(cfg).create(user.id, BotDraft("Scout", "j", "", Avatar("round", "#22c55e", "none")))
    return user.id, bot.id


async def _rows(cfg, user_id):
    async with db_session(cfg) as db:
        cursor = await db.execute("SELECT action, decision, reason, tainted FROM audit WHERE user_id = ? ORDER BY id",
                                  (user_id,))
        return [tuple(r) for r in await cursor.fetchall()]


async def test_every_verdict_writes_one_audit_row_with_its_reason(cfg, ids):
    user_id, bot_id = ids
    gate = Gate(cfg, catalog=_FAKE)
    asks = GateContext(allowed=_ALL, approval=_state("ask"))
    plans = GateContext(allowed=_ALL, approval=_state("plan"))
    auto = GateContext(allowed=_ALL, approval=_state("auto_edit"))
    assert (await gate.decide(user_id, bot_id, "add_task", {}, asks)).decision == "ask"
    assert (await gate.decide(user_id, bot_id, "add_task", {}, plans)).decision == "plan"
    assert (await gate.decide(user_id, bot_id, "add_task", {}, auto)).decision == "do"
    assert (await gate.decide(user_id, bot_id, "nope", {}, auto)).decision == "never"
    assert await _rows(cfg, user_id) == [
        ("add_task", "ask", "approval_ask", 0), ("add_task", "plan", "planned", 0),
        ("add_task", "do", "auto_edit", 0), ("nope", "never", "not_allowed", 0),
    ]


async def test_record_approved_writes_do_approved_and_plan_accepted(cfg, ids):
    user_id, bot_id = ids
    gate = Gate(cfg, catalog=_FAKE)
    await gate.record_approved(user_id, bot_id, "add_task", {"title": "x"}, reason="approved", tainted=False)
    await gate.record_approved(user_id, bot_id, "mac_edit", {}, reason="plan_accepted", tainted=True)
    assert await _rows(cfg, user_id) == [
        ("add_task", "do", "approved", 0), ("mac_edit", "do", "plan_accepted", 1)]
