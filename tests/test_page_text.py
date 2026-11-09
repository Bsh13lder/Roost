"""Fast pages, slice 3: the page's text and areas from the accessibility tree (no page script), scrolled-out text
included, text boxes never read; and the CDP driver's areas() and area_text()."""

from __future__ import annotations

from typing import Any

from roost.constants import CU_AREAS_MAX
from roost.desk import PageText
from roost.desk.page_targets import CdpPageDriver
from roost.desk.page_text import ax_areas, ax_text

from cu_page_helpers import FakeCdp, session_of

TYPED = "my secret draft to Francis"


def _node(node_id: int, role: str, name: str = "", children: tuple[int, ...] = (), backend: int | None = None,
          **extra: Any) -> dict[str, Any]:
    return {"nodeId": str(node_id), "role": {"value": role}, "name": {"value": name},
            "childIds": [str(c) for c in children], "backendDOMNodeId": backend or node_id * 10, **extra}


def _chat_tree() -> list[dict[str, Any]]:
    messages = [_node(30 + i, "StaticText", f"Message {i}: see you at the clinic") for i in range(1, 6)]
    return [
        _node(1, "RootWebArea", "WhatsApp", (2, 3, 4)),
        _node(2, "grid", "Chat list", (21, 22)),
        _node(21, "StaticText", "Francis Dentist"),
        _node(22, "StaticText", "Mum: call me when you can"),
        _node(3, "application", "", tuple(m["nodeId"] for m in messages)),
        *messages,
        _node(4, "textbox", "Type a message", (41,), properties=[{"name": "editable", "value": {"value": "richtext"}}]),
        _node(41, "StaticText", TYPED),
    ]


def test_the_whole_page_text_reads_every_line_but_never_a_text_box():
    text = ax_text(_chat_tree())
    assert "Francis Dentist" in text and "Message 5: see you at the clinic" in text
    assert TYPED not in text


def test_an_area_reads_only_its_own_subtree():
    messages = ax_text(_chat_tree(), backend=30)
    assert messages.splitlines()[0] == "Message 1: see you at the clinic" and "Francis Dentist" not in messages
    assert ax_text(_chat_tree(), backend=999) is None
    assert ax_text(_chat_tree(), backend=40) == ""                     # the composer: nothing typed is read


def test_areas_are_the_parts_with_text_in_reading_order():
    areas = ax_areas(_chat_tree())
    assert [(a.role, a.name, a.backend) for a in areas] == [("grid", "Chat list", 20), ("application", "", 30)]
    assert areas[1].chars > areas[0].chars


def test_a_wrapper_with_the_same_text_is_left_out_and_short_areas_too():
    tree = [
        _node(1, "RootWebArea", "", (2, 5)),
        _node(2, "main", "", (3,)),
        _node(3, "list", "Results", (4,)),
        _node(4, "StaticText", "A long enough result line to count as an area of text"),
        _node(5, "navigation", "Menu", (6,)),
        _node(6, "StaticText", "Home"),
    ]
    assert [(a.role, a.name) for a in ax_areas(tree)] == [("list", "Results")]


def test_only_the_largest_areas_are_kept():
    lists = [_node(10 + i, "list", f"L{i}", (100 + i,)) for i in range(CU_AREAS_MAX + 3)]
    texts = [_node(100 + i, "StaticText", "x" * (50 + i)) for i in range(CU_AREAS_MAX + 3)]
    tree = [_node(1, "RootWebArea", "", tuple(int(n["nodeId"]) for n in lists)), *lists, *texts]
    names = [a.name for a in ax_areas(tree)]
    assert len(names) == CU_AREAS_MAX and "L0" not in names and f"L{CU_AREAS_MAX + 2}" in names


class _TreeCdp(FakeCdp):
    def __init__(self, nodes: list[dict[str, Any]]) -> None:
        super().__init__({"viewport": [1280, 690], "boxes": {"20": [0, 60, 400, 600], "30": [400, 60, 880, 600]},
                          "hits": {}, "url": "https://web.whatsapp.test/", "dom": {"id": 1, "tag": "html"}, "ax": []})
        self.nodes = nodes

    def _Accessibility_getFullAXTree(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"nodes": self.nodes}


async def _no_facts() -> PageText:
    return PageText(url="", title="", text="", truncated=False)


async def test_the_driver_lists_areas_with_their_boxes_and_reads_one():
    client = _TreeCdp(_chat_tree())
    driver = CdpPageDriver(session_of(client), _no_facts)
    areas = await driver.areas()
    assert [(a.name, a.box.x if a.box else None) for a in areas] == [("Chat list", 0), ("", 400)]
    assert "Message 3" in (await driver.area_text(30) or "") and await driver.area_text(999) is None
    assert TYPED not in (await driver.area_text(None) or "")
    assert "Runtime.evaluate" not in client.methods()
