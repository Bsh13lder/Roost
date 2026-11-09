"""Full computer, Step 1 (D1, D2): a screen act (anything but Brave in front) and open_app just happen; inside
Brave the page's checks are unchanged."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.floor import act_commits, floor_of
from roost.approvals.models import ApprovalState
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import ACT_TEXTS, judge_act
from roost.computer_use.models import ActResolution, resolution_from_json, resolution_to_json
from roost.mac.redact import redact_for_audit
from roost.talk.verdict import GateContext

_FENCE = SiteFence(frozenset({"example.com"}))
_ALL = frozenset({"click", "type", "press_key", "open_app"})


def _screen(tool: str = "click", point: tuple[int, int] | None = (300, 200)) -> ActResolution:
    return ActResolution(tool, "", "", None, point, "", "", "browsing", space="screen")  # type: ignore[arg-type]


def _ctx(*, tainted: bool = True, cards: bool = False, topics: frozenset[str] = frozenset({"browsing"}),
         allowed: frozenset[str] = _ALL) -> GateContext:
    return GateContext(allowed=allowed, tainted=tainted,
                       approval=ApprovalState("ask", topics, cards))  # type: ignore[arg-type]


def test_a_resolution_is_on_the_page_unless_it_says_screen():
    assert ActResolution("click", "", "", None, None, "", "", "unknown").space == "page"
    assert _screen().space == "screen"


@pytest.mark.parametrize("tool", ["click", "type", "press_key"])
def test_a_screen_act_just_happens_in_every_taint_mode_and_topic(tool):
    for ctx in (_ctx(), _ctx(tainted=False), _ctx(cards=True), _ctx(topics=frozenset())):
        for fence in (_FENCE, None):                  # Brave may be closed: no guards, no fence
            verdict = judge_act(tool, _screen(tool, None if tool != "click" else (1, 1)), ctx, fence, typed_chars=40)
            assert (verdict.decision, verdict.reason) == ("do", "allowed")


def test_a_screen_act_still_needs_its_tool_allowed_and_matching():
    assert judge_act("click", _screen(), _ctx(allowed=frozenset({"type"})), _FENCE).decision == "never"
    assert judge_act("type", _screen("click"), _ctx(), _FENCE).reason == "act_refused"


def test_no_target_still_commits_on_the_page_but_not_on_the_screen():
    page = ActResolution("click", "https://example.com/", "example.com", None, (1, 1), "", "", "browsing")
    assert act_commits(page) and floor_of(page, _FENCE) == "commit_click"
    assert not act_commits(_screen()) and floor_of(_screen(), _FENCE) is None
    assert judge_act("click", page, _ctx(cards=True), _FENCE).reason == "hard_floor"     # D2: unchanged


def test_a_page_password_box_is_still_never():
    from test_cu_gate import _target

    box = _target("Password", kind="field", tag="input", input_type="password", editable=True, secret_field=True)
    page = ActResolution("type", "https://example.com/", "example.com", box, (1, 1), "", "", "browsing")
    assert judge_act("type", page, _ctx(cards=True), _FENCE).text == ACT_TEXTS.password


def test_open_app_just_happens_when_allowed():
    assert judge_act("open_app", None, _ctx(), None).decision == "do"
    assert judge_act("open_app", None, _ctx(allowed=frozenset({"click"})), None).decision == "never"


def test_space_survives_the_card_json():
    page = ActResolution("click", "https://example.com/", "example.com", None, (1, 1), "", "", "browsing")
    assert resolution_from_json(resolution_to_json(page)).space == "page"
    assert resolution_from_json(resolution_to_json(_screen())).space == "screen"
    stored = {k: v for k, v in resolution_to_json(page).items() if k != "space"}       # a card from before
    assert resolution_from_json(stored).space == "page"


def test_the_audit_of_a_screen_act_and_open_app_keeps_no_words():
    dek = b"k" * 32
    typed = redact_for_audit("type", {"text": "rm -rf my words", "source": {"from": "message"}, "expect": "ok"},
                             dek, act=replace(_screen("type"), point=None))
    assert "rm -rf" not in str(typed) and typed["space"] == "screen" and typed["length"] == 15
    opened = redact_for_audit("open_app", {"app": "files", "why": "to read the report"}, dek)
    assert opened == {"app": "files", "why": {"chars": 18}}
    assert redact_for_audit("open_app", {"app": "my secret words", "why": 3}, dek) == {"why": None}
