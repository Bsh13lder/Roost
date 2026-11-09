"""Fast pages, slice 2: look numbers its controls, an act may aim by that number, the runner still resolves the
number on the live page (same resolution, same gate), and an act's result ends with a text-only glance."""

from __future__ import annotations

import html
from dataclasses import replace

import pytest
from pydantic import ValidationError

from roost.approvals.texts import PARKED_TEXT
from roost.computer_use.marks import PageMarks, same_mark
from roost.computer_use.models import ClickIn, PressKeyIn, TypeIn
from roost.computer_use.runner import FOCUS_MOVED_TEXT, NO_MARK_TEXT, STALE_MARK_TEXT
from roost.computer_use.session import LOOK_FIRST_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.fake_cu import fake_target
from roost.llm.types import SCREENSHOT_SHOWN

from cu_run_helpers import make_cu_rig, run_step, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


# -- the inputs ------------------------------------------------------------------------------------------------


def test_click_takes_exactly_one_aim_target_point_or_index():
    assert ClickIn.model_validate({"index": 3, "expect": "x"}).index == 3
    for bad in ({"index": 3, "x": 1, "y": 2, "expect": "x"}, {"index": 3, "target": {"text": "a"}, "expect": "x"},
                {"index": 0, "expect": "x"}, {"expect": "x"}):
        with pytest.raises(ValidationError):
            ClickIn.model_validate(bad)


def test_type_and_press_key_take_an_optional_index():
    assert TypeIn.model_validate({"text": "socks", "index": 2, "expect": "x"}).index == 2
    assert TypeIn.model_validate({"text": "socks", "expect": "x"}).source is None
    assert PressKeyIn.model_validate({"key": "Enter", "index": 1, "expect": "x"}).index == 1


# -- the marks -------------------------------------------------------------------------------------------------


def test_marks_number_from_one_and_refuse_anything_else():
    a, b = fake_target("link", "Jobs", 1, 1), fake_target("button", "Buy now", 1, 50)
    marks = PageMarks(url="https://shop.example/", controls=(a, b))
    assert marks.control(1) == a and marks.control(2) == b
    assert marks.control(0) is None and marks.control(3) is None
    assert PageMarks.empty().control(1) is None


def test_same_mark_needs_the_same_control_not_just_the_same_node():
    a = fake_target("link", "Jobs", 1, 1, tag="a", link_host="shop.example")
    assert same_mark(a, replace(a, box=replace(a.box, y=300)))          # it moved: still the same control
    assert not same_mark(a, replace(a, text="Delete account"))
    assert not same_mark(a, replace(a, link_host="evil.example"))
    assert not same_mark(a, replace(a, node_id=a.node_id + 1))
    assert not same_mark(a, replace(a, in_dialog="Confirm"))


# -- look ------------------------------------------------------------------------------------------------------


async def test_look_numbers_the_controls_and_marks_the_focused_one(rig):
    cu = rig.computer()
    looked = await step(cu, "look")
    text = html.unescape(looked.text)
    assert '[1] field "Note"' in text and '[3] button "Buy now"' in text
    assert "· commits" in text and "· focused" not in text
    await step(cu, "click", index=1, expect="the note box is focused")
    again = await step(cu, "look")
    assert '[1] field "Note" at (250, 118) · focused' in html.unescape(again.text)


async def test_a_text_only_look_has_no_picture(rig):
    cu = rig.computer()
    await step(cu, "look")
    assert cu.newest_image()
    text_only = await step(cu, "look", picture=False)
    assert SCREENSHOT_SHOWN not in text_only.text and text_only.looked
    assert cu.newest_image() is None and '[1] field "Note"' in html.unescape(text_only.text)


# -- acts by number --------------------------------------------------------------------------------------------


async def test_a_click_by_number_lands_on_that_control(rig):
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "click", index=2, expect="the jobs list shows")
    assert rig.page.state_name == "jobs" and "Clicked 'Jobs'" in rig.lines
    assert "Address: https://shop.example/jobs" in done.text


async def test_a_number_before_any_look_is_refused(rig):
    cu = rig.computer()
    assert (await step(cu, "click", index=2, expect="jobs")).text == LOOK_FIRST_TEXT
    assert rig.desk.inputs == ()


async def test_a_number_the_newest_look_did_not_give_is_refused(rig):
    cu = rig.computer()
    await step(cu, "look")
    assert (await step(cu, "click", index=40, expect="x")).text == NO_MARK_TEXT.format(index=40)
    assert rig.desk.inputs == ()


async def test_a_number_whose_control_changed_is_refused_and_asks_for_a_look(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    original = rig.page.target_for

    async def swapped(node_id: int):
        live = await original(node_id)
        return replace(live, text="Delete account") if live is not None else None

    monkeypatch.setattr(rig.page, "target_for", swapped)
    assert (await step(cu, "click", index=2, expect="x")).text == STALE_MARK_TEXT.format(index=2)
    assert rig.desk.inputs == ()
    assert (await step(cu, "click", target={"text": "Jobs"}, expect="x")).text == LOOK_FIRST_TEXT


async def test_a_number_on_a_committing_button_still_asks(rig):
    runner = rig.tool_runner()
    await run_step(runner, "look")
    assert await run_step(runner, "click", index=3, expect="ordered") == PARKED_TEXT
    assert rig.page.state_name == "shop" and rig.desk.inputs == ()
    assert runner.parked is not None and runner.parked.title == "Click 'Buy now'"


async def test_a_number_on_a_password_box_is_never_typed_into(rig):
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "type", index=5, text="blue wool socks size 42", source={"from": "message"}, expect="x")
    assert "password" in done.text.lower() and rig.desk._screen_page.pasted_lengths == ()


async def test_type_by_number_focuses_the_box_then_types(rig):
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "type", index=1, text="blue wool socks size 42", source={"from": "message"},
                      expect="note saved")
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click"]   # then a paste
    assert rig.desk._screen_page.pasted_lengths == (23,) and rig.page.state_name == "noted"
    assert "Typed into 'Note' (23 characters)" in rig.lines and "blue wool" not in done.text


async def test_press_key_by_number_needs_a_text_box(rig):
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "press_key", index=2, key="Enter", expect="x")
    assert "text box" in done.text and rig.desk.inputs == ()


# -- the glance ------------------------------------------------------------------------------------------------


async def test_an_act_ends_with_a_glance_so_the_next_act_needs_no_look(rig):
    cu = rig.computer()
    await step(cu, "look")
    clicked = await step(cu, "click", index=1, expect="the note box is focused")
    assert clicked.looked and '[1] field "Note"' in html.unescape(clicked.text) and "· focused" in clicked.text
    assert "<untrusted_page" in clicked.text and SCREENSHOT_SHOWN not in clicked.text
    assert cu.newest_image() is None                         # the old picture is stale now
    jobs = await step(cu, "click", index=2, expect="jobs")   # no look between: the glance was the check
    assert rig.page.state_name == "jobs" and "No jobs today" in jobs.text


async def test_a_focus_click_that_does_not_land_types_nothing_and_asks_for_a_look(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")

    async def nothing_focused():
        return None

    monkeypatch.setattr(rig.page, "focused", nothing_focused)
    done = await step(cu, "type", index=1, text="blue wool socks size 42", source={"from": "message"}, expect="x")
    assert done.text == FOCUS_MOVED_TEXT and rig.desk._screen_page.pasted_lengths == ()
    assert (await step(cu, "click", index=2, expect="jobs")).text == LOOK_FIRST_TEXT
