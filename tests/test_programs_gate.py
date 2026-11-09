"""Programs: the gate runs sandbox tools in a clean run and asks in a tainted one (design §4)."""

from __future__ import annotations

import pytest

from roost.approvals import topics
from roost.approvals.models import ApprovalState
from roost.mac.redact import redact_for_audit
from roost.talk.gate import GateContext, judge
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, helper_tool_names

SANDBOX = ("run_program", "write_file")
READS = ("read_file", "list_files")
ARGS = {"run_program": {"command": "python3 a.py"}, "write_file": {"path": "a.py", "text": "print(1)"},
        "read_file": {"path": "a.py"}, "list_files": {}}
ALL = frozenset(CATALOG)


def _state(mode="auto_edit", ask=frozenset(), cards=True):
    return ApprovalState(mode, frozenset(ask), cards)


def _judge(name, **ctx):
    return judge(CATALOG[name], name, ARGS[name], GateContext(allowed=ALL, **ctx))


def test_every_bot_has_the_program_tools_and_helpers_only_the_reads():
    assert set(SANDBOX + READS) <= EVERY_BOT_TOOLS
    assert helper_tool_names(EVERY_BOT_TOOLS) & set(SANDBOX + READS) == set(READS)


def test_sandbox_tools_have_a_topic_and_the_reads_none():
    assert all(topics.topic_of(name) == "programs" for name in SANDBOX)
    assert all(topics.topic_of(name) is None for name in READS)
    assert all(CATALOG[name].sandbox for name in SANDBOX) and not any(CATALOG[name].sandbox for name in READS)


@pytest.mark.parametrize("mode", ["ask", "auto_edit", "plan"])
@pytest.mark.parametrize("name", SANDBOX)
def test_a_clean_run_just_runs_them_in_every_mode(mode, name):
    verdict = _judge(name, approval=_state(mode))
    assert (verdict.decision, verdict.reason) == ("do", "allowed")


@pytest.mark.parametrize("name", SANDBOX)
def test_a_clean_run_without_approvals_runs_them(name):
    assert _judge(name).decision == "do"


@pytest.mark.parametrize("mode", ["ask", "auto_edit", "plan"])
@pytest.mark.parametrize("name", SANDBOX)
def test_a_tainted_run_asks_in_every_mode_even_past_the_create_cap(mode, name):
    verdict = _judge(name, tainted=True, creates=99, approval=_state(mode))
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


@pytest.mark.parametrize("name", SANDBOX)
def test_a_tainted_run_with_no_cards_is_refused(name):
    for ctx in ({"approval": _state(cards=False)}, {}):
        verdict = _judge(name, tainted=True, **ctx)
        assert (verdict.decision, verdict.reason) == ("never", "needs_your_ok")


@pytest.mark.parametrize("name", SANDBOX)
def test_the_programs_topic_switch_asks_in_a_clean_run(name):
    verdict = _judge(name, approval=_state(ask={"programs"}))
    assert (verdict.decision, verdict.reason) == ("ask", "topic_asks")


@pytest.mark.parametrize("name", READS)
def test_reads_run_in_any_run(name):
    assert _judge(name, tainted=True, approval=_state("ask")).decision == "do"


def test_a_tool_outside_the_run_is_never():
    ctx = GateContext(allowed=frozenset({"get_time"}))
    assert judge(CATALOG["run_program"], "run_program", ARGS["run_program"], ctx).decision == "never"


def test_the_audit_keeps_lengths_never_the_command_or_text():
    kept = redact_for_audit("write_file", {"path": "a.py", "text": "secret words"}, b"k" * 32)
    assert kept == {"path": {"chars": 4}, "text": {"chars": 12}}
    assert redact_for_audit("run_program", {"command": "echo hi", "timeout_s": 5}, b"k" * 32) == {
        "command": {"chars": 7}, "timeout_s": 5}
