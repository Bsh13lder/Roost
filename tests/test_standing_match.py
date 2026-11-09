"""The standing match (Step 2): a hard-floor act in a routine run that a live permission names (site, action,
count, date) gets ``do``/``standing_ok``; everything else asks exactly as before. The judge stays pure."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.standing.matching import act_action, match_act
from roost.standing.models import LivePermission, PermissionIn, StandingState, permission_site
from roost.talk.verdict import GateContext

_FENCE = SiteFence(frozenset({"x.com"}))
_ACTS = frozenset({"click", "type", "press_key"})


def _target(text: str = "Post", **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False,
    )
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(text: str = "Post", **over: object) -> ActResolution:
    target = over.pop("target", _target(text))
    fields: dict[str, object] = dict(
        tool="click", url="https://x.com/home", host="x.com", target=target, point=(140, 215), covered_by="",
        nav_host="", commit=commit_class(target))  # type: ignore[arg-type]
    fields.update(over)
    return ActResolution(**fields)  # type: ignore[arg-type]


def _typing(**over: object) -> ActResolution:
    box = _target("What is happening?", kind="field", tag="textarea", editable=True)
    return _click(target=box, tool="type", commit="browsing", text_ok=False, **over)


def _standing(*perms: LivePermission, today: str = "2026-10-23") -> StandingState:
    return StandingState(routine_id="r1", instructions="Post the weekly update.", permissions=perms, today=today)


def _perm(action: str = "post", host: str = "x.com", remaining: int = 1, pid: str = "p1") -> LivePermission:
    return LivePermission(pid, host, action, remaining)  # type: ignore[arg-type]


def _ctx(standing: StandingState | None, *, cards: bool = True, tainted: bool = True) -> GateContext:
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=cards, standing=standing)
    return GateContext(allowed=_ACTS, tainted=tainted, approval=state, fence=_FENCE)


@pytest.mark.parametrize(("label", "action"), [
    ("Post", "post"), ("Publish", "post"), ("Tweet", "post"), ("Publicar", "post"), ("Reply", "send"),
    ("Send message", "send"), ("Enviar", "send"), ("Submit", "submit"), ("Confirmar", "submit"),
    ("Buy now", None), ("Delete", None), ("Save changes", None), ("Accept offer", None), ("Next page", None),
])
def test_act_action_maps_commit_words_to_the_three_actions(label, action):
    assert act_action(_click(label)) == action


def test_a_post_form_without_words_is_submit_and_enter_reads_the_form():
    assert act_action(_click(target=_target("", is_form_submit=True, form_method="post"))) == "submit"
    box = _target("Message", kind="field", tag="input", editable=True, form_submit_text="Send")
    assert act_action(_click(target=box, tool="press_key", commit=commit_class(box, key="Enter"))) == "send"


def test_a_routine_permission_lets_a_matching_commit_through():
    verdict = judge_act("click", _click("Post"), _ctx(_standing(_perm())), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "standing_ok")
    assert verdict.standing is not None and verdict.standing.permission_id == "p1" and verdict.standing.consume


def test_a_subdomain_of_the_permitted_site_matches_but_a_look_alike_does_not():
    assert match_act(_standing(_perm()), _click(host="mobile.x.com"), "commit_click") is not None
    assert match_act(_standing(_perm()), _click(host="notx.com"), "commit_click") is None


@pytest.mark.parametrize("resolution", [
    _click("Reply"),                       # send, the permission says post
    _click("Buy now"),                     # spend never matches
    _click("Delete"),
    _click(host="linkedin.com"),           # another site
    _click(covered_by="Are you sure?"),    # something covers the button
    _click(nav_host="evil.example"),       # the form goes elsewhere
    _click(target=_target("Post", cross_origin_frame=True)),
])
def test_anything_else_still_asks(resolution):
    verdict = judge_act("click", resolution, _ctx(_standing(_perm())), _FENCE)
    assert verdict.decision != "do"


def test_no_standing_state_or_no_count_left_asks_as_before():
    assert judge_act("click", _click(), _ctx(None), _FENCE).reason == "hard_floor"
    assert judge_act("click", _click(), _ctx(_standing(_perm(remaining=0))), _FENCE).reason == "hard_floor"


def test_new_site_is_never_covered():
    off = _click(nav_host="other.com")
    assert judge_act("click", off, _ctx(_standing(_perm(host="other.com"))), _FENCE).reason == "new_site"


def test_typing_on_the_site_is_covered_without_using_the_count():
    found = match_act(_standing(_perm()), _typing(), "typed_text")
    assert found is not None and found.consume is False
    verdict = judge_act("type", _typing(), _ctx(_standing(_perm())), SiteFence(frozenset()), typed_chars=40)
    assert (verdict.decision, verdict.reason) == ("do", "allowed")      # typing never asks (owner, 2026-11-03)


@pytest.mark.parametrize("flags", [frozenset({"contact"}), frozenset({"secret"})])
def test_contact_details_and_secrets_are_never_covered(flags):
    verdict = judge_act("type", _typing(text_flags=flags), _ctx(_standing(_perm())), _FENCE, typed_chars=40)
    assert verdict.decision != "do"


def test_a_password_box_is_still_refused():
    box = _target("Password", kind="field", tag="input", input_type="password", editable=True, secret_field=True)
    verdict = judge_act("type", _click(target=box, tool="type", commit="browsing"), _ctx(_standing(_perm())), _FENCE)
    assert verdict.decision == "never"


def test_permission_site_and_input_validation():
    assert permission_site("https://x.com") == ""
    assert permission_site("WWW.Example.COM.") == "example.com"
    assert permission_site("localhost") == ""
    with pytest.raises(ValueError):
        PermissionIn(host="not a host", action="post", max_per_day=1, until="2026-11-01")
    with pytest.raises(ValueError):
        PermissionIn(host="x.com", action="spend", max_per_day=1, until="2026-11-01")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PermissionIn(host="x.com", action="post", max_per_day=21, until="2026-11-01")


def test_the_state_is_frozen():
    state = _standing(_perm())
    with pytest.raises(AttributeError):
        state.today = "x"  # type: ignore[misc]
    assert replace(state, today="2026-10-24").today == "2026-10-24"
