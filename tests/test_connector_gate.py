"""Connectors at the gate (design §4): GET and HEAD are reads; every write asks at the hard floor in every mode,
a tainted run still asks (never runs on its own), and a run that can't show a card is refused."""

from __future__ import annotations

import pytest

from roost.approvals import floor, topics
from roost.approvals.models import ApprovalState
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.talk.gate import GateContext, judge
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import HELPER_DENIED, helper_tool_names

_ALL = frozenset(CATALOG)
_MODES = ("ask", "auto_edit", "plan")


def _judge(method, *, mode="auto_edit", tainted=False, approval="state", cards=True):
    state = ApprovalState(mode=mode, ask_topics=frozenset(), cards=cards) if approval == "state" else approval
    ctx = GateContext(allowed=_ALL, tainted=tainted, approval=state)
    args = {"connector": "Search", "method": method, "path": "/x"}
    return judge(CATALOG["use_connector"], "use_connector", args, ctx)


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("method", ["GET", "get", "HEAD"])
@pytest.mark.parametrize("tainted", [False, True])
def test_reads_run(mode, method, tainted):
    assert _judge(method, mode=mode, tainted=tainted).decision == "do"


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("method", ["POST", "put", "PATCH", "DELETE", "TRACE", None])
@pytest.mark.parametrize("tainted", [False, True])
def test_writes_always_ask(mode, method, tainted):
    verdict = _judge(method, mode=mode, tainted=tainted)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


@pytest.mark.parametrize("approval,cards", [(None, True), ("state", False)])
def test_writes_are_refused_where_no_card_can_show(approval, cards):
    verdict = _judge("POST", approval=approval, cards=cards)
    assert (verdict.decision, verdict.text) == ("never", NEEDS_YOUR_OK_TEXT)
    assert _judge("GET", approval=approval, cards=cards).decision == "do"


def test_the_write_is_on_the_floor_and_posting():
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)
    assert topics.topic_of("use_connector") == "posting"
    assert floor.hard_floor("use_connector", {"method": "POST"}, state) == "posting"
    assert CATALOG["use_connector"].kind_for({"method": "GET"}) == "read"
    assert CATALOG["use_connector"].kind_for({"method": "POST"}) == "write_change"
    assert CATALOG["list_connectors"].kind == "read"


def test_not_allowed_is_never():
    ctx = GateContext(allowed=frozenset(), approval=None)
    assert judge(CATALOG["use_connector"], "use_connector", {"method": "GET"}, ctx).decision == "never"


def test_helpers_never_get_use_connector():
    assert "use_connector" not in helper_tool_names(_ALL)
    assert "use_connector" in HELPER_DENIED or CATALOG["use_connector"].kind != "read"
