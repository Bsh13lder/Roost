"""Install an app at the gate (docs/plans/2026-10-22-roost-install-app.md §1): install_app and remove_app ask at the
hard floor in every approval mode, Auto-edit included, clean or tainted; where no card can show they are never;
list_apps is a read. Only a bot on its Linux computer is offered them, and never a helper."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals import floor, topics
from roost.approvals.models import ApprovalState
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.bots.models import Avatar, Bot, BotStatus
from roost.talk.gate import GateContext, judge
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import helper_tool_names, run_tool_names

_ALL = frozenset(CATALOG)
_MODES = ("ask", "auto_edit", "plan")
_CALLS = {"install_app": {"package": "gimp", "why": "Edit the logo"}, "remove_app": {"package": "gimp"}}


def _judge(name, *, mode="auto_edit", tainted=False, cards=True, approval="state", ask_topics=frozenset()):
    state = ApprovalState(mode=mode, ask_topics=ask_topics, cards=cards) if approval == "state" else approval
    ctx = GateContext(allowed=_ALL, tainted=tainted, approval=state)
    return judge(CATALOG[name], name, _CALLS.get(name, {}), ctx)


@pytest.mark.parametrize("name", sorted(_CALLS))
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("tainted", [False, True])
def test_install_and_remove_always_ask(name, mode, tainted):
    verdict = _judge(name, mode=mode, tainted=tainted)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


@pytest.mark.parametrize("name", sorted(_CALLS))
@pytest.mark.parametrize("approval,cards", [(None, True), ("state", False)])
def test_never_where_no_card_can_show(name, approval, cards):
    verdict = _judge(name, approval=approval, cards=cards)
    assert (verdict.decision, verdict.text) == ("never", NEEDS_YOUR_OK_TEXT)


def test_list_apps_is_a_read():
    assert CATALOG["list_apps"].kind == "read"
    assert _judge("list_apps").decision == "do"


def test_they_sit_on_the_floor_and_a_tainted_card_may_still_run():
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)
    for name in _CALLS:
        assert floor.hard_floor(name, _CALLS[name], state) == "install_app"
        assert topics.topic_of(name) == "programs"
        assert name in topics.ASK_WHEN_TAINTED_TOOLS


_BOT = Bot(id="b1", user_id="u1", name="Scout", job="installs", instructions="", avatar=Avatar("round", "#22c55e", "none"),
           template_id=None, status=BotStatus.RESTING, model_override=None,
           created_at="2026-10-22T00:00:00+00:00", updated_at="2026-10-22T00:00:00+00:00")


def _bot(computer: str) -> Bot:
    return replace(_BOT, computer=computer)


@pytest.mark.parametrize("team", [False, True])
def test_only_a_linux_bot_gets_the_app_tools(team):
    names = {"install_app", "remove_app", "list_apps"}
    assert names <= run_tool_names(_bot("linux"), team=team)
    assert not names & run_tool_names(_bot("mac_brave"), team=team)


def test_helpers_never_install_or_remove():
    helper = helper_tool_names(_ALL)
    assert "install_app" not in helper and "remove_app" not in helper
