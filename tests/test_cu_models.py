"""C3 Task 1: the computer-use tool inputs and the frozen resolution."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roost.computer_use.models import (
    ActResolution,
    Box,
    ClickIn,
    PageTarget,
    PressKeyIn,
    ScrollIn,
    TargetIn,
    TypeIn,
    WaitReadyIn,
    resolution_from_json,
    resolution_to_json,
    same_target,
)
from roost.constants import CU_KEYS


def _target(text: str = "Apply", box: Box = Box(100, 200, 80, 30), **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=box, form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False,
    )
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _resolution(target: PageTarget | None, **over: object) -> ActResolution:
    fields: dict[str, object] = dict(
        tool="click", url="https://example.com/jobs", host="example.com", target=target,
        point=target.box.center() if target else None, covered_by="", nav_host="", commit="submit",
    )
    fields.update(over)
    return ActResolution(**fields)  # type: ignore[arg-type]


def test_click_in_needs_exactly_one_of_target_or_point() -> None:
    assert ClickIn(target=TargetIn(text="Apply"), expect="a form opens").target is not None
    assert ClickIn(x=10, y=20, expect="a menu opens").x == 10
    with pytest.raises(ValidationError):
        ClickIn(expect="nothing")
    with pytest.raises(ValidationError):
        ClickIn(target=TargetIn(text="Apply"), x=1, y=2, expect="both")
    with pytest.raises(ValidationError):
        ClickIn(x=10, expect="half a point")
    with pytest.raises(ValidationError):
        ClickIn(x=5000, y=10, expect="off the screen")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ClickIn.model_validate({"x": 1, "y": 2, "expect": "x", "resolution": {"commit": "browsing"}})
    with pytest.raises(ValidationError):
        TypeIn.model_validate({"text": "hi", "source": {"from": "message"}, "expect": "x", "text_ok": True})
    with pytest.raises(ValidationError):
        TargetIn.model_validate({"text": "Buy", "commit": "browsing"})


def test_target_kind_is_from_the_list() -> None:
    assert TargetIn(text="Apply", kind="button").kind == "button"
    with pytest.raises(ValidationError):
        TargetIn(text="Apply", kind="role")


def test_type_in_takes_its_source_from_the_from_word() -> None:
    typed = TypeIn.model_validate({"text": "hello", "source": {"from": "note", "id": "n1"}, "expect": "filled"})
    assert typed.source.kind == "note" and typed.source.id == "n1"
    with pytest.raises(ValidationError):
        TypeIn.model_validate({"text": "hello", "source": {"from": "page"}, "expect": "filled"})


def test_press_key_outside_the_list_is_rejected() -> None:
    assert PressKeyIn(key="Enter", expect="search runs").key == "Enter"
    for key in ("Ctrl+L", "F12", "Alt+F4"):
        with pytest.raises(ValidationError):
            PressKeyIn(key=key, expect="x")
    assert all(PressKeyIn(key=key, expect="x") for key in CU_KEYS)


def test_scroll_and_wait_ready_bounds() -> None:
    assert ScrollIn(direction="down").amount == 5      # fast pages: five notches by default
    assert ScrollIn(direction="up", at={"x": 10, "y": 20}).at == {"x": 10, "y": 20}
    with pytest.raises(ValidationError):
        ScrollIn(direction="down", amount=50)
    with pytest.raises(ValidationError):
        ScrollIn(direction="down", at={"x": 10})
    with pytest.raises(ValidationError):
        ScrollIn(direction="down", at={"x": 10, "y": 9000})
    with pytest.raises(ValidationError):
        WaitReadyIn(timeout_s=60)


def test_box_center_is_whole_pixels() -> None:
    assert Box(10.4, 20.2, 41, 10).center() == (31, 25)


def test_same_target_tolerates_8px_but_not_a_new_label() -> None:
    before = _resolution(_target())
    nudged = _resolution(_target(box=Box(106, 205, 80, 30)), point=(146, 220))
    moved = _resolution(_target(box=Box(130, 200, 80, 30)), point=(170, 215))
    relabelled = _resolution(_target(text="Buy now"))
    assert same_target(before, nudged)
    assert not same_target(before, moved)
    assert not same_target(before, relabelled)
    assert not same_target(before, _resolution(_target(), commit="spend"))
    assert not same_target(before, _resolution(_target(), host="evil.io"))
    assert not same_target(_resolution(None, commit="unknown"), _resolution(None, commit="unknown"))


def test_resolution_round_trips_without_the_crop() -> None:
    original = _resolution(_target(), crop=b"\xff\xd8jpeg", text_flags=frozenset({"contact", "secret"}), text_ok=True)
    data = resolution_to_json(original)
    assert "crop" not in data
    assert data["text_flags"] == ["contact", "secret"]
    back = resolution_from_json(data)
    assert back.crop == b""
    assert back == _resolution(_target(), text_flags=frozenset({"contact", "secret"}), text_ok=True)
    assert resolution_from_json(resolution_to_json(_resolution(None))).target is None


def test_resolution_from_json_refuses_unknown_or_bad_fields() -> None:
    data = resolution_to_json(_resolution(_target()))
    with pytest.raises(ValueError):
        resolution_from_json({**data, "extra": 1})
    with pytest.raises(ValueError):
        resolution_from_json({**data, "commit": "maybe"})
    with pytest.raises(ValueError):
        resolution_from_json({**data, "target": {**data["target"], "sneaky": True}})


def test_same_target_needs_the_same_page_address() -> None:
    # Security review (a): a Yes for "Pay" on /cart/1 is not a Yes for the same-placed "Pay" on /cart/999.
    cart_1 = _resolution(_target(), url="https://example.com/cart/1")
    cart_999 = _resolution(_target(), url="https://example.com/cart/999")
    assert not same_target(cart_1, cart_999)
    assert not same_target(cart_1, _resolution(_target(), url="https://example.com/cart/1?item=9"))
    assert same_target(cart_1, _resolution(_target(), url="https://example.com/cart/1#reviews"))
    assert not same_target(_resolution(_target(visible_text="Pay"), url=cart_1.url),
                           _resolution(_target(visible_text="Pay twice"), url=cart_1.url))


def test_a_send_button_whose_count_changed_is_the_same_control() -> None:
    # Owner, 2026-11-03: Upwork relabels "Send for 14 Connects" to "Send for 12 Connects" while the card waits.
    before = _resolution(_target("Send for 14 Connects", visible_text="Send for 14 Connects"), commit="send")
    after = _resolution(_target("Send for 12 Connects", visible_text="Send for 12 Connects"), commit="send")
    assert same_target(before, after)
    submit = _resolution(_target("Submit 3 proposals", form_submit_text="Submit 3"), commit="submit")
    assert same_target(submit, _resolution(_target("Submit 4 proposals", form_submit_text="Submit 4"),
                                           commit="submit"))
    assert not same_target(before, _resolution(_target("Send for Connects"), commit="send"))
    assert not same_target(before, _resolution(_target("Delete 12 Connects"), commit="send"))
    assert not same_target(before, _resolution(_target("Send for 12 Connects", visible_text="Send for 12 Connects"),
                                               commit="spend"))


def test_a_price_on_a_pay_button_must_not_change() -> None:
    pay = _resolution(_target("Pay $14"), commit="spend")
    assert same_target(pay, _resolution(_target("Pay $14"), commit="spend"))
    assert not same_target(pay, _resolution(_target("Pay $12"), commit="spend"))
    browse = _resolution(_target("Page 2"), commit="browsing")
    assert not same_target(browse, _resolution(_target("Page 3"), commit="browsing"))
