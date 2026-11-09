"""The computer-use loop's rules (C3 Task 11): one loop per computer, act then check, one screen action per
step, the control epoch, the try-once-more ladder and the budget."""

from __future__ import annotations

from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.computer_use.session import (
    BUDGET_TEXT, LOOK_FIRST_TEXT, ONE_ACTION_TEXT, TAKEN_TEXT, ComputerUseLease, LoopState, after_act, after_look,
    after_miss, after_scroll, aim_key, budget_left, new_step, precheck, target_key,
)
from roost.constants import CU_MAX_ACTS_PER_RUN, CU_MAX_LOOKS_PER_RUN, CU_TRIES_PER_TARGET


def _target(text: str = "Search", *, kind: str = "field", editable: bool = True) -> PageTarget:
    return PageTarget(
        node_id=7, kind=kind, text=text, tag="input" if editable else "button", input_type="text" if editable else "",
        box=Box(10, 10, 100, 20), form_method="get", form_submit_text="", is_form_submit=False, link_host="",
        in_dialog="", in_consent=False, cross_origin_frame=False, editable=editable, secret_field=False,
        searchish=editable, expands=False,
    )


def _click(target: PageTarget | None = None) -> ActResolution:
    t = target or _target()
    return ActResolution(tool="click", url="https://example.com/", host="example.com", target=t,
                         point=t.box.center(), covered_by="", nav_host="", commit="browsing")


def _typed() -> ActResolution:
    return ActResolution(tool="type", url="https://example.com/", host="example.com", target=_target(),
                         point=None, covered_by="", nav_host="", commit="browsing", text_ok=True)


def _looked(epoch: int = 0) -> LoopState:
    return new_step(after_look(LoopState(run_id="r1"), epoch))


def test_one_loop_per_computer():
    lease = ComputerUseLease()
    assert lease.acquire("b1", "r1") is True
    assert lease.acquire("b1", "r2") is False
    assert lease.holder("b1") == "r1"
    assert lease.acquire("b2", "r2") is True   # another bot's computer is its own
    lease.release("b1", "r2")                  # only the holder releases
    assert lease.holder("b1") == "r1"
    lease.release("b1", "r1")
    assert lease.holder("b1") is None
    assert lease.acquire("b1", "r2") is True


def test_the_same_run_may_reacquire():
    lease = ComputerUseLease()
    assert lease.acquire("b1", "r1") and lease.acquire("b1", "r1")
    assert lease.holder("b1") == "r1"


def test_an_act_needs_a_fresh_look():
    fresh = LoopState(run_id="r1")
    assert precheck(fresh, "click", 0) == LOOK_FIRST_TEXT
    assert precheck(fresh, "look", 0) is None
    looked = _looked()
    assert precheck(looked, "click", 0) is None
    moved = new_step(after_act(looked, _click(_target("Next", kind="button", editable=False)), "page 2"))
    assert precheck(moved, "press_key", 0) == LOOK_FIRST_TEXT
    assert precheck(new_step(after_look(moved, 0)), "press_key", 0) is None


def test_type_right_after_the_focusing_click_needs_no_look():
    clicked = new_step(after_act(_looked(), _click(), "the box is focused"))
    assert clicked.focused_by_click == target_key(_click())
    assert precheck(clicked, "type", 0) is None
    assert precheck(clicked, "click", 0) == LOOK_FIRST_TEXT
    typed = new_step(after_act(clicked, _typed(), "typed", typed_digest="abc"))
    assert typed.focused_by_click == ""
    assert precheck(typed, "type", 0) == LOOK_FIRST_TEXT
    button = new_step(after_act(_looked(), _click(_target("Go", kind="button", editable=False)), "went"))
    assert button.focused_by_click == "" and precheck(button, "type", 0) == LOOK_FIRST_TEXT


def test_typing_records_the_field_digest_only():
    clicked = new_step(after_act(_looked(), _click(), "focused"))
    r = _typed()
    typed = after_act(clicked, r, "typed", typed_digest="d1")
    assert dict(typed.typed) == {"Search": "d1"}   # the look says only whether it still holds it


def test_scroll_makes_the_next_act_look_first():
    scrolled = new_step(after_scroll(_looked()))
    assert precheck(scrolled, "click", 0) == LOOK_FIRST_TEXT
    assert scrolled.used_screen


def test_one_screen_action_per_step():
    looked = after_look(LoopState(run_id="r1"), 0)
    assert looked.acted_this_step
    assert precheck(looked, "click", 0) == ONE_ACTION_TEXT
    assert precheck(looked, "look", 0) == ONE_ACTION_TEXT
    assert precheck(new_step(looked), "click", 0) is None


def test_take_control_makes_the_next_act_look_first():
    looked = _looked(epoch=0)
    assert precheck(looked, "click", 1) == TAKEN_TEXT
    assert precheck(new_step(after_look(looked, 1)), "click", 1) is None


def test_second_miss_on_a_target_is_stuck():
    key = aim_key("click", {"target": {"text": "Apply"}, "expect": "applied"})
    once, stuck = after_miss(LoopState(run_id="r1"), key)
    assert stuck is False and once.tries[key] == 1
    other, stuck_other = after_miss(once, aim_key("click", {"target": {"text": "Next"}, "expect": "x"}))
    assert stuck_other is False
    state = other
    for _ in range(CU_TRIES_PER_TARGET - 2):          # owner, 2026-11-03: four tries in all
        state, stuck = after_miss(state, key)
        assert stuck is False
    last, stuck = after_miss(state, key)
    assert stuck is True and last.tries[key] == CU_TRIES_PER_TARGET
    assert aim_key("click", {"x": 4, "y": 5, "expect": "e"}) != key


def test_budget_runs_out_after_40_acts():
    state = _looked()
    for _ in range(CU_MAX_ACTS_PER_RUN):
        assert budget_left(state) is None
        state = new_step(after_look(new_step(after_act(state, _click(_target("Go", kind="button", editable=False)), "x")), 0))
    assert state.acts == CU_MAX_ACTS_PER_RUN
    assert budget_left(state) == BUDGET_TEXT
    assert precheck(state, "click", 0) == BUDGET_TEXT
    assert precheck(state, "look", 0) == BUDGET_TEXT


def test_budget_runs_out_after_60_looks():
    state = LoopState(run_id="r1", looks=CU_MAX_LOOKS_PER_RUN)
    assert budget_left(state) == BUDGET_TEXT
    assert precheck(state, "wait_ready", 0) == BUDGET_TEXT


def test_states_are_new_objects():
    start = LoopState(run_id="r1")
    looked = after_look(start, 3)
    assert start.looks == 0 and looked.looks == 1 and looked.control_epoch == 3 and looked.used_screen
