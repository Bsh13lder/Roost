"""``roost/desk/box_text.py``: a text box is read and selected in the isolated world ``roost-box``, on the one element
named by its backend node id; a gone element, another frame or a page error reads as None / False."""

from __future__ import annotations

from typing import Any

from roost.desk.box_text import BOX_WORLD, read_box, select_box
from roost.desk.cdp import CdpReplyError


class _Cdp:
    def __init__(self, value: Any = "hola", *, gone: bool = False, threw: bool = False) -> None:
        self.value, self.gone, self.threw = value, gone, threw
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
            if self.threw:
                return {"result": {"exceptionDetails": {"text": "boom"}}}
            return {"result": {"result": {"value": self.value}}}
        return {"result": {}}

    def params(self, method: str) -> dict[str, Any]:
        return next(p for m, p in self.calls if m == method)


async def test_reads_the_box_in_its_own_world_on_that_element():
    cdp = _Cdp("Здравствуйте")
    assert await read_box(cdp, "S1", 42) == "Здравствуйте"
    assert cdp.params("Page.createIsolatedWorld")["worldName"] == BOX_WORLD
    assert cdp.params("DOM.resolveNode") == {"backendNodeId": 42, "executionContextId": 7}
    call = cdp.params("Runtime.callFunctionOn")
    assert call["objectId"] == "obj-1" and call["returnByValue"] is True and "innerText" in call["functionDeclaration"]
    assert ("Runtime.releaseObject", {"objectId": "obj-1"}) in cdp.calls


async def test_no_text_box_gone_or_error_reads_as_none():
    assert await read_box(_Cdp(None), "S1", 1) is None
    assert await read_box(_Cdp(gone=True), "S1", 1) is None
    assert await read_box(_Cdp(threw=True), "S1", 1) is None


async def test_select_is_true_only_when_the_page_said_so():
    cdp = _Cdp(True)
    assert await select_box(cdp, "S1", 5) is True
    assert "addRange" in cdp.params("Runtime.callFunctionOn")["functionDeclaration"]
    assert await select_box(_Cdp(False), "S1", 5) is False
    assert await select_box(_Cdp(gone=True), "S1", 5) is False
