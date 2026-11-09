"""Teach steps as plain lines, and the shapes they are kept in (teach design note)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roost.constants import TEACH_DESCRIPTION_MAX, TEACH_LABEL_MAX, TEACH_PATH_MAX
from roost.teach.models import TeachStep, TeachStopIn, one_line, url_parts
from roost.teach.steps import action_of, numbered, page_of, same_step, step_lines


def test_url_parts_keeps_host_and_path_and_drops_the_query():
    assert url_parts("https://Shop.Example/orders/new?email=a@b.c#top") == ("shop.example", "/orders/new")
    assert url_parts("https://shop.example") == ("shop.example", "/")
    assert url_parts("chrome://newtab/") == ("", "")
    assert url_parts("about:blank") == ("", "")
    assert url_parts("http://[::1") == ("", "")
    long_path = "https://a.example/" + "x" * 500
    assert len(url_parts(long_path)[1]) == TEACH_PATH_MAX


def test_a_step_is_one_line_and_short():
    step = TeachStep(kind="click", host="a.example", role="button", label="Send\n  now " + "y" * 300)
    assert "\n" not in step.label and len(step.label) == TEACH_LABEL_MAX
    assert one_line("  a \t b ", 10) == "a b"
    with pytest.raises(ValidationError):
        TeachStep(kind="click", value="hunter2")          # a step has no place for a typed value
    with pytest.raises(ValidationError):
        TeachStep(kind="key", key="a")


def test_lines_name_the_page_only_when_it_changes():
    steps = (
        TeachStep(kind="click", host="shop.example", path="/", title="Shop", role="link", label="Orders"),
        TeachStep(kind="click", host="shop.example", path="/orders", title="Orders", role="button", label="New"),
        TeachStep(kind="type", host="shop.example", path="/orders", title="Orders", role="field", label="Item"),
        TeachStep(kind="key", host="shop.example", path="/orders", title="Orders", key="Enter"),
    )
    assert step_lines(steps) == (
        "On shop.example/ (“Shop”): click the link “Orders”",
        "On shop.example/orders (“Orders”): click the button “New”",
        "Type into the field “Item”",
        "Press Enter",
    )
    assert numbered(["a", "b"]) == "1. a\n2. b"


def test_every_kind_has_words_and_none_shows_typed_text():
    assert action_of(TeachStep(kind="password", host="a.example")).startswith("a password is needed")
    assert action_of(TeachStep(kind="type")) == "type an address into the browser's address bar"
    assert action_of(TeachStep(kind="type", host="a.example")) == "type into the focused field"
    assert action_of(TeachStep(kind="paste", host="a.example", label="Note")) == "paste into the field “Note”"
    assert action_of(TeachStep(kind="paste", host="a.example")) == "paste into the focused field"
    assert action_of(TeachStep(kind="click", host="a.example")) == "click on the page"
    assert action_of(TeachStep(kind="click", host="a.example", label="Go")) == "click the control “Go”"
    assert action_of(TeachStep(kind="browser")) == "use the browser's address bar or tabs"
    assert action_of(TeachStep(kind="key")) == "press a key"
    assert page_of(TeachStep(kind="browser")) == ""
    assert page_of(TeachStep(kind="click", host="a.example", path="/x")) == "a.example/x"
    assert step_lines((TeachStep(kind="browser"),)) == ("Use the browser's address bar or tabs",)


def test_same_step_spots_a_repeat():
    a = TeachStep(kind="click", host="a.example", label="Go")
    assert same_step(a, TeachStep(kind="click", host="a.example", label="Go"))
    assert not same_step(a, TeachStep(kind="click", host="a.example", label="Stop"))


def test_stop_body_checks_the_description():
    assert TeachStopIn().description is None and TeachStopIn().discard is False
    assert TeachStopIn(description="  Post a weekly update  ").description == "Post a weekly update"
    assert TeachStopIn(description="   ").description is None
    with pytest.raises(ValidationError):
        TeachStopIn(description="x" * (TEACH_DESCRIPTION_MAX + 1))
    with pytest.raises(ValidationError):
        TeachStopIn(description="two\nlines")
    with pytest.raises(ValidationError):
        TeachStopIn(description="ok", extra=1)
