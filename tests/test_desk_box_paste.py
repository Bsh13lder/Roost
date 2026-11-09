"""``roost/desk/box_text.py`` paste (owner, 2026-11-01): the whole text goes into the box with CDP
``Input.insertText`` (no key events, so a line break can never press Enter), only when the box the resolver found
is the focused one. A one-line ``<input>`` refuses text with line breaks; a box that is not focused, gone, in
another frame or an ``Input.insertText`` error is "no paste" (the runner may type it instead). Line breaks count the
same in the read-back check whatever form they take."""

from __future__ import annotations

from typing import Any

import pytest

from roost.desk.box_text import BOX_WORLD, NO_PASTE, ONE_LINE, PASTED, has_line_breaks, paste_text, same_text
from roost.desk.cdp import CdpReplyError


class _Cdp:
    def __init__(self, kind: Any = "lines", *, gone: bool = False, insert_fails: bool = False) -> None:
        self.kind, self.gone, self.insert_fails = kind, gone, insert_fails
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params))
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "F1"}}}}
        if method == "Page.createIsolatedWorld":
            return {"result": {"executionContextId": 7}}
        if method == "DOM.resolveNode":
            if self.gone:
                raise CdpReplyError("No node with given id found")
            return {"result": {"object": {"objectId": "obj-1"}}}
        if method == "Runtime.callFunctionOn":
            return {"result": {"result": {"value": self.kind}}}
        if method == "Input.insertText" and self.insert_fails:
            raise CdpReplyError("Input.insertText failed")
        return {"result": {}}

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


_LETTER = "Hello,\n\nI can start Monday.\n\tGela"


async def test_a_focused_textarea_takes_the_whole_text_in_one_insert():
    cdp = _Cdp("lines")
    assert await paste_text(cdp, "S1", 42, _LETTER) == PASTED
    assert ("Input.insertText", {"text": _LETTER}) in cdp.calls
    assert [m for m in cdp.methods() if m.startswith("Input.")] == ["Input.insertText"]   # never a key event
    assert next(p for m, p in cdp.calls if m == "Page.createIsolatedWorld")["worldName"] == BOX_WORLD
    check = next(p for m, p in cdp.calls if m == "Runtime.callFunctionOn")["functionDeclaration"]
    assert "activeElement" in check and "TEXTAREA" in check


async def test_a_one_line_box_refuses_line_breaks_before_anything_goes_in():
    cdp = _Cdp("line")
    assert await paste_text(cdp, "S1", 42, "45 per hour\nfixed") == ONE_LINE
    assert "Input.insertText" not in cdp.methods()
    assert await paste_text(_Cdp("line"), "S1", 42, "45 per hour") == PASTED


async def test_a_tab_is_fine_in_a_one_line_box():
    cdp = _Cdp("line")
    assert await paste_text(cdp, "S1", 42, "a\tb") == PASTED


@pytest.mark.parametrize("cdp", [_Cdp(None), _Cdp("other"), _Cdp(gone=True), _Cdp(insert_fails=True)])
async def test_an_unfocused_gone_or_failing_box_is_no_paste(cdp):
    assert await paste_text(cdp, "S1", 42, "hola") == NO_PASTE


async def test_an_unfocused_box_is_never_inserted_into():
    cdp = _Cdp(None)
    await paste_text(cdp, "S1", 42, "hola")
    assert "Input.insertText" not in cdp.methods()


def test_line_breaks_are_newlines_and_carriage_returns_only():
    assert has_line_breaks("a\nb") and has_line_breaks("a\rb")
    assert not has_line_breaks("a\tb") and not has_line_breaks("one line")


def test_same_text_keeps_line_breaks_for_multi_line_text():
    assert same_text("Hello,\n\nI can start.\n", "Hello,\n\nI can start.")
    assert same_text("Hello,\r\n\r\nI can start.", "Hello,\n\nI can start.")
    assert same_text("Hello,\n\n\nI can start.", "Hello,\n\nI can start.")     # an editor's own blank line
    assert same_text("Best regards,\n    Gela", "Best regards,\n\tGela")
    assert not same_text("Hello, I can start.", "Hello,\n\nI can start.")       # the paragraphs were lost
    assert not same_text("Hello,\nI can\nstart.", "Hello,\nI can start.")       # a break where none was meant


def test_same_text_for_one_line_text_is_unchanged():
    assert same_text("hola  que\ntal\n", "hola que tal")
    assert not same_text("Каие дни", "Какие дни")
