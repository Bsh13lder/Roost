"""``read_page`` never returns what sits inside a text box (Computers 2.0, C2, Task 12).

A typed password or e-mail address shows up in the accessibility tree as a ``StaticText`` child of the text box."""

from __future__ import annotations

from roost.desk.browser import _build_page_text


def _node(node_id: str, role: str, name: str = "", *, parent: str | None = None, children: tuple[str, ...] = ()):
    node = {"nodeId": node_id, "role": {"value": role}, "name": {"value": name}, "childIds": list(children)}
    if parent:
        node["parentId"] = parent
    return node


def _form(box_role: str = "textbox"):
    return [
        _node("1", "RootWebArea", "Sign in", children=("2", "3", "4", "6", "9")),
        _node("2", "heading", "Welcome back", parent="1"),
        _node("3", "StaticText", "Email address", parent="1"),
        _node("4", box_role, "Email", parent="1", children=("5",)),
        _node("5", "StaticText", "me@example.com", parent="4"),
        _node("6", "textbox", "Password", parent="1", children=("7",)),
        _node("7", "generic", "", parent="6", children=("8",)),
        _node("8", "StaticText", "hunter2-secret", parent="7"),
        _node("9", "button", "Log in", parent="1"),
    ]


def test_values_inside_text_boxes_never_reach_read_page():
    text, _ = _build_page_text(_form())
    assert "me@example.com" not in text
    assert "hunter2-secret" not in text


def test_labels_and_buttons_around_them_still_do():
    text, _ = _build_page_text(_form())
    assert "Welcome back" in text and "Email address" in text and "Log in" in text


def test_a_search_box_and_a_combobox_are_skipped_too():
    for role in ("searchbox", "combobox", "spinbutton"):
        text, _ = _build_page_text(_form(role))
        assert "me@example.com" not in text, role
