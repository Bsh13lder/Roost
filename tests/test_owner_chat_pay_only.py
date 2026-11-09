"""Only paying asks in your own chat (owner, 2026-11-05: "only pay needs confirmation, like Grok").

In a run of your own 1:1 chat that can show a card, a send, submit, accept, delete or account click just runs
(``owner_chat_act``), typing your ID numbers runs, and the bot's programs run after web
content. Paying still asks; a button Roost can't read keeps the reviewer or its card; a password box stays never.
Routines, handoffs and rooms are unchanged."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.standing.models import StandingState
from roost.talk.gate import GateContext, judge
from roost.talk.tool_catalog import CATALOG

_FENCE = SiteFence(frozenset({"alsa.es"}))
_CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)


def _ctx(**changes: object) -> GateContext:
    """Your own chat after it read a page."""
    base = GateContext(allowed=frozenset(CATALOG), tainted=True, approval=_CARDS, owner_chat=True,
                       site_fresh=False, fence=_FENCE)
    return replace(base, **changes)  # type: ignore[arg-type]


def _target(text: str, **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False,
    )
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(text: str, **over: object) -> ActResolution:
    target = _target(text)
    fields: dict[str, object] = dict(tool="click", url="https://www.alsa.es/checkout", host="www.alsa.es",
                                     target=target, point=target.box.center(), covered_by="", nav_host="",
                                     commit=commit_class(target))
    fields.update(over)
    return ActResolution(**fields)  # type: ignore[arg-type]


def _typing(*, text_ok: bool, flags: frozenset[str]) -> ActResolution:
    box = _target("Document number", kind="field", tag="input", input_type="text", editable=True)
    return replace(_click("x"), tool="type", target=box, commit="browsing", text_ok=text_ok, text_flags=flags)


@pytest.mark.parametrize("label", ["Send", "Submit", "Accept", "Confirm booking", "Delete", "Continue"])
def test_your_own_chat_just_clicks_everything_but_paying(label):
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert verdict.decision == "do"


def test_a_send_of_the_bots_own_text_just_sends_in_your_own_chat():
    verdict = judge_act("click", _click("Send", own_text=True), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_act")


@pytest.mark.parametrize("label", ["Pay now", "Buy now", "Pagar"])
def test_paying_still_asks_in_your_own_chat(label):
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_your_id_number_from_your_own_message_is_typed():
    verdict = judge_act("type", _typing(text_ok=True, flags=frozenset({"secret"})), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_act")


def test_a_secret_you_never_gave_still_asks():
    verdict = judge_act("type", _typing(text_ok=False, flags=frozenset({"secret"})), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_a_phone_or_email_you_never_gave_still_asks():
    verdict = judge_act("type", _typing(text_ok=False, flags=frozenset({"contact"})), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_a_password_box_is_still_never_typed_into():
    box = _target("Password", kind="field", tag="input", input_type="password", editable=True, secret_field=True)
    act = replace(_typing(text_ok=True, flags=frozenset()), target=box)
    assert judge_act("type", act, _ctx(), _FENCE).decision == "never"


@pytest.mark.parametrize("changes", [{"owner_chat": False}, {"approval": replace(_CARDS, cards=False)},
                                     {"approval": replace(_CARDS, standing=StandingState("r1", "", (), "2026-11-05"))}])
def test_outside_your_own_chat_a_send_is_unchanged(changes):
    verdict = judge_act("click", _click("Send"), _ctx(**changes), _FENCE)
    assert verdict.decision != "do"


def test_a_program_runs_after_web_content_in_your_own_chat():
    verdict = judge(CATALOG["run_program"], "run_program", {"command": "curl -s https://example.com"}, _ctx())
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_act")


def test_a_program_in_a_tainted_routine_still_asks_or_refuses():
    verdict = judge(CATALOG["run_program"], "run_program", {"command": "ls"}, _ctx(owner_chat=False))
    assert verdict.decision != "do"
