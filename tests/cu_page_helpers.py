"""A fake CDP client that serves one C3 page fixture (``tests/fixtures/cu_ax_*.json``).

A fixture is compact: ``dom`` is a tree of ``{"id", "tag", "attrs", "children"}`` elements and ``{"id", "text"}``
text nodes (an element may carry ``shadow``: ``{"id", "type", "children"}``, its shadow root), ``ax`` a list of ``{"role", "name", "backend", "props", "value", "ignored"}``, ``boxes`` maps a backend
id to ``[x, y, width, height]`` (viewport CSS px) and ``hits`` maps ``"x,y"`` to the backend id under that point.
``FakeCdp`` turns them into the CDP reply shapes Chromium sends."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from roost.desk.cdp import CdpReplyError

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"cu_ax_{name}.json").read_text())


def _dom(node: dict[str, Any]) -> dict[str, Any]:
    if "text" in node:
        return {"backendNodeId": node["id"], "nodeType": 3, "nodeName": "#text", "nodeValue": node["text"]}
    flat = [part for key, value in (node.get("attrs") or {}).items() for part in (key, value)]
    out = {"backendNodeId": node["id"], "nodeType": 1, "nodeName": node["tag"].upper(), "localName": node["tag"],
           "attributes": flat, "children": [_dom(child) for child in node.get("children") or ()]}
    shadow = node.get("shadow")             # {"id", "type": "user-agent" | "open", "children"}
    if shadow:
        out["shadowRoots"] = [{"backendNodeId": shadow["id"], "nodeType": 11, "nodeName": "#document-fragment",
                               "shadowRootType": shadow["type"],
                               "children": [_dom(child) for child in shadow.get("children") or ()]}]
    return out


def _ax(index: int, node: dict[str, Any]) -> dict[str, Any]:
    props = [{"name": key, "value": {"type": "booleanOrUndefined", "value": value}}
             for key, value in (node.get("props") or {}).items()]
    out: dict[str, Any] = {"nodeId": str(index), "role": {"type": "role", "value": node["role"]},
                           "name": {"type": "computedString", "value": node.get("name", "")},
                           "backendDOMNodeId": node["backend"], "properties": props,
                           "ignored": bool(node.get("ignored"))}
    if "value" in node:
        out["value"] = {"type": "string", "value": node["value"]}
    return out


def solid_jpeg(width: int = 64, height: int = 40, colour: tuple[int, int, int] = (20, 120, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="JPEG")
    return out.getvalue()


class FakeCdp:
    """Answers the CDP methods the page driver sends, from one fixture; records every call."""

    is_open = True                        # a live socket (``CdpClient.is_open``)

    def __init__(self, fixture: dict[str, Any], *, jpeg: bytes | None = None) -> None:
        self.fixture = fixture
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.jpeg = jpeg or solid_jpeg()
        self.window_state = "normal"

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params))
        handler = getattr(self, "_" + method.replace(".", "_"), None)
        result = handler(params) if handler else {}
        return {"id": len(self.calls), "result": result}

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]

    def _Accessibility_getFullAXTree(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"nodes": [_ax(i, node) for i, node in enumerate(self.fixture["ax"])]}

    def _DOM_getDocument(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"root": _dom(self.fixture["dom"])}

    def _Page_getLayoutMetrics(self, params: dict[str, Any]) -> dict[str, Any]:
        width, height = self.fixture["viewport"]
        return {"cssLayoutViewport": {"clientWidth": width, "clientHeight": height, "pageX": 0, "pageY": 0}}

    def _Page_getNavigationHistory(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"currentIndex": 0, "entries": [{"id": 1, "url": self.fixture["url"],
                                             "title": self.fixture.get("title", "")}]}

    def _DOM_getBoxModel(self, params: dict[str, Any]) -> dict[str, Any]:
        box = self.fixture["boxes"].get(str(params["backendNodeId"]))
        if box is None:
            raise CdpReplyError("Could not compute box model.")
        x, y, w, h = box
        quad = [x, y, x + w, y, x + w, y + h, x, y + h]
        return {"model": {"border": quad, "content": quad, "width": w, "height": h}}

    def _DOM_getNodeForLocation(self, params: dict[str, Any]) -> dict[str, Any]:
        hit = self.fixture["hits"].get(f"{params['x']},{params['y']}")
        if hit is None:
            raise CdpReplyError("No node found at given location")
        return {"backendNodeId": hit, "frameId": "main"}

    def _Page_captureScreenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"data": base64.b64encode(self.jpeg).decode()}


def session_of(client: FakeCdp, sid: str = "S1"):
    async def session() -> tuple[FakeCdp, str]:
        return client, sid
    return session
