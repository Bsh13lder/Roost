"""The page's readable text and its areas, from Chromium's accessibility tree (fast pages, slice 3).

Pure functions over ``Accessibility.getFullAXTree`` nodes: no page script ever runs (the same rule as
``roost/desk/browser.py``). The tree holds every node the DOM holds, scrolled out of view or not, so a chat's
older messages that the page keeps in its DOM are read without scrolling.

- ``ax_text`` reads the lines ``read_page`` reads (headings, links, text, paragraphs, list items, cells, buttons),
  in tree order with repeats collapsed, for the whole page or for one area's subtree. **Nothing inside a text box is
  read** (what a person types sits there as the box's child text).
- ``ax_areas`` names the parts of a page worth reading on their own: lists, grids, feeds, logs, dialogs, the main
  region, an application pane (WhatsApp's messages), each with how much text it holds. An area that only wraps
  another listed area with the same text is left out (the inner one stays), and only the largest ``CU_AREAS_MAX``
  are kept.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from roost.constants import CU_AREA_MIN_CHARS, CU_AREAS_MAX, CU_TARGET_TEXT_MAX

READABLE_ROLES = frozenset({"heading", "link", "StaticText", "paragraph", "listitem", "cell", "button"})
TEXT_BOX_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})
AREA_ROLES = frozenset({
    "main", "region", "navigation", "complementary", "grid", "treegrid", "list", "listbox", "tree", "feed", "log",
    "application", "dialog", "alertdialog", "article", "document", "table", "tabpanel", "form", "search",
})
_EDITABLE_TOKENS = frozenset({"plaintext", "richtext"})

AxNode = Mapping[str, Any]


@dataclass(frozen=True)
class AxArea:
    backend: int
    role: str
    name: str
    chars: int


def _role(node: AxNode) -> str:
    return str((node.get("role") or {}).get("value") or "")


def _name(node: AxNode) -> str:
    return str((node.get("name") or {}).get("value") or "")


def _editable(node: AxNode) -> bool:
    return any(p.get("name") == "editable" and (p.get("value") or {}).get("value") in _EDITABLE_TOKENS
               for p in node.get("properties") or ())


def _children(nodes: Sequence[AxNode]) -> dict[str, list[str]]:
    """nodeId -> child ids, from ``childIds`` and, for nodes that only name their parent, ``parentId``."""
    children: dict[str, list[str]] = {}
    for node in nodes:
        node_id = str(node.get("nodeId"))
        for child in node.get("childIds") or ():
            children.setdefault(node_id, []).append(str(child))
    for node in nodes:
        parent = node.get("parentId")
        node_id = str(node.get("nodeId"))
        if parent is not None and node_id not in children.get(str(parent), ()):
            children.setdefault(str(parent), []).append(node_id)
    return children


def _below(children: Mapping[str, list[str]], roots: Iterable[str]) -> set[str]:
    """Every id under ``roots`` (not the roots themselves)."""
    found: set[str] = set()
    pending = list(roots)
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _hidden(nodes: Sequence[AxNode], children: Mapping[str, list[str]]) -> set[str]:
    boxes = [str(n.get("nodeId")) for n in nodes if _role(n) in TEXT_BOX_ROLES or _editable(n)]
    return _below(children, boxes)


def _line(node: AxNode, hidden: set[str]) -> str:
    if node.get("ignored") or str(node.get("nodeId")) in hidden or _role(node) not in READABLE_ROLES:
        return ""
    return " ".join(_name(node).split())


def _collapsed(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line and (not out or out[-1] != line):
            out.append(line)
    return out


def ax_text(nodes: Sequence[AxNode], backend: int | None = None) -> str | None:
    """The readable text of the page (``backend`` None) or of the node with that backend id and everything under
    it; None when no such node is in the tree."""
    children = _children(nodes)
    hidden = _hidden(nodes, children)
    if backend is None:
        return "\n".join(_collapsed(_line(n, hidden) for n in nodes))
    root = next((n for n in nodes if n.get("backendDOMNodeId") == backend and not n.get("ignored")), None)
    if root is None:
        return None
    root_id = str(root.get("nodeId"))
    inside = _below(children, [root_id]) | {root_id}
    return "\n".join(_collapsed(_line(n, hidden) for n in nodes if str(n.get("nodeId")) in inside))


def _sizes(nodes: Sequence[AxNode], children: Mapping[str, list[str]], hidden: set[str]) -> dict[str, int]:
    """nodeId -> characters of readable text in it and under it (one pass, children before parents)."""
    own = {str(n.get("nodeId")): len(_line(n, hidden)) for n in nodes}
    order: list[str] = []
    seen: set[str] = set()
    for start in own:
        stack = [(start, False)]
        while stack:
            node_id, done = stack.pop()
            if done:
                order.append(node_id)
                continue
            if node_id in seen:
                continue
            seen.add(node_id)
            stack.append((node_id, True))
            stack.extend((child, False) for child in children.get(node_id, ()) if child not in seen)
    total: dict[str, int] = {}
    for node_id in order:
        total[node_id] = own.get(node_id, 0) + sum(total.get(c, 0) for c in children.get(node_id, ()))
    return total


def ax_areas(nodes: Sequence[AxNode]) -> tuple[AxArea, ...]:
    """The readable areas, in reading order, at most ``CU_AREAS_MAX`` (the largest kept)."""
    children = _children(nodes)
    sizes = _sizes(nodes, children, _hidden(nodes, children))
    parent = {child: node_id for node_id, kids in children.items() for child in kids}
    found: list[tuple[str, AxArea]] = []
    for node in nodes:
        node_id, backend = str(node.get("nodeId")), node.get("backendDOMNodeId")
        if node.get("ignored") or _role(node) not in AREA_ROLES or not isinstance(backend, int):
            continue
        chars = sizes.get(node_id, 0)
        if chars < CU_AREA_MIN_CHARS:
            continue
        name = " ".join(_name(node).split())[:CU_TARGET_TEXT_MAX]
        found.append((node_id, AxArea(backend=backend, role=_role(node), name=name, chars=chars)))
    kept = _without_wrappers(found, parent)
    largest = sorted(kept, key=lambda pair: -pair[1].chars)[:CU_AREAS_MAX]
    chosen = {node_id for node_id, _ in largest}
    return tuple(area for node_id, area in kept if node_id in chosen)


def _without_wrappers(found: list[tuple[str, AxArea]], parent: Mapping[str, str]) -> list[tuple[str, AxArea]]:
    """Drop an area that only wraps another listed area holding exactly the same text (a region around a grid):
    the inner one is the more specific."""
    listed = dict(found)
    wrappers = set()
    for node_id, area in found:
        up = _nearest(parent, node_id, listed)
        if up is not None and listed[up].chars == area.chars:
            wrappers.add(up)
    return [(node_id, area) for node_id, area in found if node_id not in wrappers]


def _nearest(parent: Mapping[str, str], node_id: str, listed: Mapping[str, AxArea]) -> str | None:
    up = parent.get(node_id)
    while up is not None and up not in listed:
        up = parent.get(up)
    return up
