"""The bot's page as controls it can click (C3 Task 6): ``PageDriver`` and its CDP implementation.

``targets()`` reads Chromium's own computations, never a page script: ``Accessibility.getFullAXTree`` (roles and
accessible names) → the interactive roles → ``DOM.getBoxModel`` for each, kept when the box is inside the viewport
(``Page.getLayoutMetrics``) → the structural facts from ``DOM.getDocument`` (``roost/desk/page_dom.py``: the form
and its method and default submit, the dialog, a consent banner, a link's host, a cross-origin frame). Boxes are in
viewport CSS pixels (Design meets code 5).

``node_at`` asks ``DOM.getNodeForLocation`` and climbs to the nearest interactive ancestor; ``covering`` says
whether something else (a dialog) sits over a target's centre. **Text-box values are never read**: the AX ``value``
is ignored, the DOM ``value`` attribute is dropped, and a field's text is only its label.
"""

from __future__ import annotations

import base64
import contextlib
import io
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from PIL import Image

from roost.computer_use.commit_words import names_a_search
from roost.computer_use.marks import PageArea
from roost.computer_use.models import Box, PageTarget
from roost.constants import CU_HIDDEN_CONTROL_PX, CU_JPEG_QUALITY, CU_READY_PROBE_H, CU_READY_PROBE_W, CU_TARGET_TEXT_MAX
from roost.desk.saved_login_check import password_filled
from roost.desk import PageText
from roost.desk.cdp import CdpReplyError
from roost.desk.page_dom import DomIndex, DomNode
from roost.desk.card_names import card_part
from roost.desk.secret_names import names_a_code, names_a_login
from roost.desk.page_geometry import CdpSender, WindowGeometry, read_geometry
from roost.desk.blob_fetch import read_blob
from roost.desk import box_text as box
from roost.desk.page_fetch import fetch_through_browser
from roost.desk.page_text import ax_areas, ax_text
from roost.desk.ready import LifecycleView, count_busy_marks, read_lifecycle

_KIND_OF_ROLE: Mapping[str, str] = {
    "button": "button", "link": "link", "tab": "tab", "checkbox": "checkbox", "switch": "checkbox",
    "radio": "radio", "option": "option", "menuitem": "menuitem", "menuitemcheckbox": "menuitem",
    "menuitemradio": "menuitem", "textbox": "field", "searchbox": "field", "combobox": "field",
    "spinbutton": "field", "slider": "field",
}
# A list's entries (WhatsApp's chats are focusable grid cells, 2026-10-25) are clickable rows only when the page
# made them focusable: a plain table's rows and cells are words, not controls.
_ROW_ROLES = frozenset({"row", "gridcell", "treeitem"})
ROW_KIND = "row"
_TYPING_ROLES = frozenset({"textbox", "searchbox", "spinbutton"})
_EDITABLE_TOKENS = frozenset({"plaintext", "richtext"})
_FRAME_ROLE = "Iframe"
FRAME_KIND = "frame"                     # a cross-origin frame (a payment widget): the commit test says unknown
_SECRET_AUTOCOMPLETE = frozenset({"current-password", "new-password", "one-time-code"})
_SIGN_IN_AUTOCOMPLETE = frozenset({"username", "webauthn"})
_TYPING_INPUT_TYPES = frozenset({"", "text", "number", "tel", "email", "password"})
_CODE_MAXLENGTH = range(4, 9)            # inputmode=numeric with maxlength 4-8 in a form that mentions a code
_NO_BOX = Box(x=0, y=0, width=0, height=0)
_SOMETHING = "something"
_FULL_TREE_DEPTH = -1


class PageDriver(Protocol):
    """What a Linux desk (``CdpPageDriver``) and the scripted fake (``roost/desk/fake_cu.py``) expose for C3."""

    async def targets(self) -> tuple[PageTarget, ...]: ...
    async def target_for(self, node_id: int) -> PageTarget | None: ...
    async def areas(self) -> tuple[PageArea, ...]: ...
    async def area_text(self, node_id: int | None) -> str | None: ...
    async def link_url(self, node_id: int) -> str: ...
    async def fetch(self, url: str, max_bytes: int) -> bytes: ...
    async def read_blob(self, url: str, max_bytes: int) -> bytes: ...
    async def find(self, text: str, kind: str, nth: int) -> PageTarget | None: ...
    async def node_at(self, x: int, y: int) -> PageTarget | None: ...
    async def focused(self) -> PageTarget | None: ...
    async def covering(self, target: PageTarget) -> str: ...
    async def screenshot(self, *, probe: bool = False) -> bytes: ...
    async def geometry(self) -> WindowGeometry: ...
    async def url(self) -> str: ...
    async def title(self) -> str: ...
    async def facts(self) -> PageText: ...
    async def lifecycle(self) -> LifecycleView: ...
    async def busy_marks(self) -> int: ...
    async def box_text(self, node_id: int) -> str | None: ...
    async def select_box(self, node_id: int) -> bool: ...
    async def paste_text(self, node_id: int, text: str) -> str: ...
    async def password_filled(self) -> bool: ...


def _prop(node: Mapping[str, Any], name: str) -> Any:
    for prop in node.get("properties") or ():
        if prop.get("name") == name:
            return (prop.get("value") or {}).get("value")
    return None


def _role(node: Mapping[str, Any]) -> str:
    return str((node.get("role") or {}).get("value") or "")


def _name(node: Mapping[str, Any]) -> str:
    """The accessible name (a label), whitespace collapsed. Never the node's ``value``."""
    return " ".join(str((node.get("name") or {}).get("value") or "").split())[:CU_TARGET_TEXT_MAX]


def _kind(node: Mapping[str, Any]) -> str | None:
    role = _role(node)
    if role == _FRAME_ROLE:
        return FRAME_KIND
    kind = _KIND_OF_ROLE.get(role)
    if kind is None and _prop(node, "editable") in _EDITABLE_TOKENS:
        return "field"
    if kind is None and role in _ROW_ROLES and _prop(node, "focusable") is True:
        return ROW_KIND
    return kind


def _editable(node: Mapping[str, Any]) -> bool:
    return _role(node) in _TYPING_ROLES or _prop(node, "editable") in _EDITABLE_TOKENS


def _secret(extra: Mapping[str, Any]) -> bool:
    autocomplete = set(str(extra.get("autocomplete", "")).lower().split())
    if extra.get("input_type") == "password" or autocomplete & _SECRET_AUTOCOMPLETE:
        return True
    maxlength = str(extra.get("maxlength", ""))
    if (str(extra.get("inputmode", "")).lower() == "numeric" and maxlength.isdigit()
            and int(maxlength) in _CODE_MAXLENGTH and bool(extra.get("form_mentions_code"))):
        return True
    return _typing_box(extra) and names_a_code(str(extra.get("field_names", "")))


def _typing_box(extra: Mapping[str, Any]) -> bool:
    return extra.get("tag") in ("input", "textarea") and str(extra.get("input_type", "")) in _TYPING_INPUT_TYPES


def _sign_in_box(extra: Mapping[str, Any]) -> bool:
    """B3: a sign-in page's email or user-name box: autocomplete username/webauthn, a box in a form that also
    holds a password box, or a box whose id, name or label says login or user name. Never a secret box."""
    if not _typing_box(extra) or _secret(extra):
        return False
    autocomplete = set(str(extra.get("autocomplete", "")).lower().split())
    return bool(autocomplete & _SIGN_IN_AUTOCOMPLETE) or bool(extra.get("form_has_password")) or names_a_login(
        str(extra.get("field_names", "")))


def target_from_ax(node: Mapping[str, Any], box: Box, extra: Mapping[str, Any]) -> PageTarget:
    """One ``PageTarget`` from an AX node, its box and the DOM facts (``_extra``). Pure."""
    role, form_method = _role(node), str(extra.get("form_method", ""))
    expanded, popup = _prop(node, "expanded"), _prop(node, "hasPopup")
    return PageTarget(
        node_id=int(node.get("backendDOMNodeId") or 0), kind=_kind(node) or "any", text=_name(node),
        tag=str(extra.get("tag", "")), input_type=str(extra.get("input_type", "")), box=box,
        form_method=form_method, form_submit_text=str(extra.get("form_submit_text", "")),
        is_form_submit=bool(extra.get("is_form_submit")), link_host=str(extra.get("link_host", "")),
        in_dialog=str(extra.get("in_dialog", "")), in_consent=bool(extra.get("in_consent")),
        cross_origin_frame=bool(extra.get("cross_origin_frame")), editable=_editable(node),
        secret_field=_secret(extra) or bool(card_part(extra)), sign_in_box=_sign_in_box(extra),
        searchish=_searchish(role, extra),
        expands=role == "tab" or expanded is not None or popup not in (None, False, "false"),
        visible_text=_own_words(node, extra), focused=_prop(node, "focused") is True,
        search_named=_search_named(node, extra), card_field=card_part(extra),
        form_has_card=bool(extra.get("form_has_card")),
    )


def _searchish(role: str, extra: Mapping[str, Any]) -> bool:
    """A search box by the browser's own facts: role searchbox, type=search, a search landmark, or a form that
    says method="get" itself. A form with no method (most scripted chat forms) is not a search form."""
    explicit_get = extra.get("form_method") == "get" and bool(extra.get("form_method_given"))
    return role == "searchbox" or extra.get("input_type") == "search" or bool(extra.get("in_search")) or explicit_get


_SEARCH_BOX_ROLES = frozenset({"textbox", "searchbox", "combobox"})
_SEARCH_INPUT_TYPES = frozenset({"", "text", "search"})


def _search_named(node: Mapping[str, Any], extra: Mapping[str, Any]) -> bool:
    """Fast pages, slice 4: a one-line box whose own label, placeholder or name says search / buscar / find /
    filter (WhatsApp's "Search or start a new chat" is a plain textbox). Never a textarea, a multi-line area, a
    secret box or an input of another type. Only typing reads this; Enter still needs a structural search box."""
    one_line = _role(node) in _SEARCH_BOX_ROLES or _prop(node, "editable") in _EDITABLE_TOKENS
    if not one_line or extra.get("tag") == "textarea" or _prop(node, "multiline") is True or _secret(extra):
        return False
    if extra.get("tag") == "input" and str(extra.get("input_type", "")) not in _SEARCH_INPUT_TYPES:
        return False
    return names_a_search(f"{_name(node)} {extra.get('field_names', '')}")


def _own_words(node: Mapping[str, Any], extra: Mapping[str, Any]) -> str:
    if _prop(node, "editable") in _EDITABLE_TOKENS:
        return ""                                      # a real editable area: its words are what was typed
    return str(extra.get("own_words", ""))[:CU_TARGET_TEXT_MAX]


def _extra(index: DomIndex, backend: int, labels: Mapping[int, str]) -> dict[str, Any]:
    node = index.node(backend)
    attrs = node.attrs if node else {}
    form = index.form_facts(backend, labels)
    return {
        "tag": node.tag if node else "", "input_type": attrs.get("type", "").strip().lower(),
        "autocomplete": attrs.get("autocomplete", ""), "inputmode": attrs.get("inputmode", ""),
        "maxlength": attrs.get("maxlength", ""), "field_names": _field_names(attrs, labels.get(backend, "")),
        "form_has_password": index.form_has_password(backend), "form_has_card": index.form_has_card(backend),
        "form_method": form.method, "form_submit_text": form.submit_text,
        "is_form_submit": form.is_submit, "form_mentions_code": form.mentions_code,
        "form_method_given": form.method_given, "in_search": index.in_search(backend),
        "own_words": index.own_words(backend),
        "link_host": index.link_host(backend), "in_dialog": index.dialog_title(backend, labels),
        "in_consent": index.in_consent(backend), "cross_origin_frame": index.cross_origin_frame(backend),
    }


def _field_names(attrs: Mapping[str, str], label: str) -> str:
    """What names a box (its id, name, placeholder, aria-label and label): never its value."""
    return " ".join([*(attrs.get(key, "") for key in ("id", "name", "placeholder", "aria-label")), label])


def box_from_quad(quad: list[float]) -> Box:
    xs, ys = quad[0::2], quad[1::2]
    return Box(x=min(xs), y=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))


def visible_part(box: Box, viewport: Box) -> Box | None:
    """The part of ``box`` inside the viewport, or None when nothing of it shows."""
    left, top = max(box.x, viewport.x), max(box.y, viewport.y)
    right = min(box.x + box.width, viewport.x + viewport.width)
    bottom = min(box.y + box.height, viewport.y + viewport.height)
    if right - left <= 0 or bottom - top <= 0:
        return None
    return Box(x=left, y=top, width=right - left, height=bottom - top)


def _hidden(box: Box) -> bool:
    return box.width <= CU_HIDDEN_CONTROL_PX or box.height <= CU_HIDDEN_CONTROL_PX


def same_label(a: str, b: str) -> bool:
    """Exact text, case and spacing aside: "Submit" is not "Submit later"."""
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


@dataclass(frozen=True)
class _Snapshot:
    client: CdpSender
    session_id: str
    by_backend: Mapping[int, Mapping[str, Any]]      # interactive AX nodes, reading order
    labels: Mapping[int, str]                         # every named AX node's label
    index: DomIndex
    viewport: Box
    focused_backend: int | None

    async def box(self, backend: int) -> Box | None:
        return await box_of(self.client, self.session_id, backend)

    async def drawn_box(self, backend: int) -> Box | None:
        """The box a click aims at: a hidden checkbox or radio (an sr-only 1x1 input, not rendered at all) is
        clicked through its label, as a person clicks it; every other control is its own box."""
        own = await self.box(backend)
        if own is not None and not _hidden(own):
            return own
        label = self.index.label_of_toggle(backend)
        shown = await self.box(label) if label is not None else None
        return shown if shown is not None and not _hidden(shown) else own

    def owner(self, node: DomNode) -> int | None:
        """The control a click on ``node`` works: the node itself, or the checkbox or radio a label clicks."""
        if self.ax_for(node.backend_id) is not None:
            return node.backend_id
        toggle = self.index.toggle_of_label(node.backend_id)
        return toggle if toggle is not None and self.ax_for(toggle) is not None else None

    def ax_for(self, backend: int) -> Mapping[str, Any] | None:
        node = self.by_backend.get(backend)
        if node is not None:
            return node
        dom = self.index.node(backend)
        if dom is not None and dom.tag in ("iframe", "frame") and self.index.cross_origin_frame(backend):
            title = dom.attrs.get("title", "") or self.labels.get(backend, "")
            return {"role": {"value": _FRAME_ROLE}, "name": {"value": title}, "backendDOMNodeId": backend}
        return None

    async def target(self, backend: int, *, need_view: bool) -> PageTarget | None:
        node = self.ax_for(backend)
        if node is None:
            return None
        box = await self.drawn_box(backend)
        shown = visible_part(box, self.viewport) if box is not None else None
        if need_view and shown is None:
            return None
        return target_from_ax(node, shown or box or _NO_BOX, _extra(self.index, backend, self.labels))


async def box_of(client: CdpSender, session_id: str, backend: int) -> Box | None:
    """A node's border box in viewport CSS px; None when it is not rendered (display: none, detached)."""
    try:
        reply = await client.send("DOM.getBoxModel", {"backendNodeId": backend}, session_id=session_id)
    except CdpReplyError:
        return None
    quad = ((reply.get("result") or {}).get("model") or {}).get("border")
    return box_from_quad(quad) if isinstance(quad, list) and len(quad) == 8 else None


def _interactive(nodes: list[Mapping[str, Any]]) -> tuple[dict[int, Mapping[str, Any]], dict[int, str], int | None]:
    by_backend: dict[int, Mapping[str, Any]] = {}
    labels: dict[int, str] = {}
    focused: int | None = None
    for node in nodes:
        backend = node.get("backendDOMNodeId")
        if node.get("ignored") or not isinstance(backend, int):
            continue
        if _name(node):
            labels[backend] = _name(node)
        if _kind(node) not in (None, FRAME_KIND):
            by_backend[backend] = node
            if _prop(node, "focused") is True:
                focused = backend
    return by_backend, labels, focused


def _without_browser_parts(by_backend: dict[int, Mapping[str, Any]], focused: int | None,
                           index: DomIndex) -> tuple[dict[int, Mapping[str, Any]], int | None]:
    """Chromium's own parts of a control (an <input>'s inner editor, owner 2026-10-27: WhatsApp's search box
    said "Something moved" on every click) are not controls: the hit test climbs from them to the input."""
    kept = {b: node for b, node in by_backend.items() if not index.browser_part(b)}
    return kept, (index.host_of(focused) if focused is not None else None)


SessionSource = Callable[[], Awaitable[tuple[CdpSender, str]]]
T = TypeVar("T")
# One driver method's CDP work on a client and the bot's tab session.
PageCall = Callable[[CdpSender, str], Awaitable[T]]
# Runs a ``PageCall``. ``KeeperDesk``'s runner re-runs it once on a fresh page when the connection dies mid-method
# (every driver method is a read or idempotent: Page.bringToFront, DOM.disable, a box's select-all), and backend
# node ids outlive a new session.
PageRunner = Callable[[PageCall[Any]], Awaitable[Any]]


@contextlib.asynccontextmanager
async def _snapshot(client: CdpSender, sid: str) -> AsyncIterator[_Snapshot]:
    try:
        tree = await client.send("Accessibility.getFullAXTree", {}, session_id=sid)
        document = await client.send("DOM.getDocument", {"depth": _FULL_TREE_DEPTH, "pierce": True}, session_id=sid)
        metrics = await client.send("Page.getLayoutMetrics", {}, session_id=sid)
        by_backend, labels, focused = _interactive((tree.get("result") or {}).get("nodes") or [])
        index = DomIndex.build((document.get("result") or {}).get("root") or {}, await _page_url(client, sid))
        by_backend, focused = _without_browser_parts(by_backend, focused, index)
        yield _Snapshot(client, sid, by_backend, labels, index, _viewport(metrics), focused)
    finally:
        with contextlib.suppress(CdpReplyError):
            await client.send("DOM.disable", {}, session_id=sid)


async def _ax_nodes(client: CdpSender, sid: str) -> list[Mapping[str, Any]]:
    tree = await client.send("Accessibility.getFullAXTree", {}, session_id=sid)
    return list((tree.get("result") or {}).get("nodes") or [])


async def _areas(client: CdpSender, sid: str) -> tuple[PageArea, ...]:
    nodes = await _ax_nodes(client, sid)
    view = _viewport(await client.send("Page.getLayoutMetrics", {}, session_id=sid))
    found = []
    for area in ax_areas(nodes):
        box = await box_of(client, sid, area.backend)
        found.append(PageArea(node_id=area.backend, role=area.role, name=area.name, chars=area.chars,
                              box=visible_part(box, view) if box is not None else None))
    with contextlib.suppress(CdpReplyError):
        await client.send("DOM.disable", {}, session_id=sid)
    return tuple(found)


async def _targets(snap: _Snapshot) -> tuple[PageTarget, ...]:
    found = [await snap.target(backend, need_view=True) for backend in snap.by_backend]
    frames = [await snap.target(n.backend_id, need_view=True) for n in _frames(snap)]
    return tuple(t for t in (*found, *frames) if t is not None)


async def _owner_at(snap: _Snapshot, x: int, y: int) -> PageTarget | None:
    hit = await _hit(snap, x, y)
    if hit is None:
        return None
    owner = next((found for n in snap.index.ancestors(hit, include_self=True)
                  if (found := snap.owner(n)) is not None), None)
    return await snap.target(owner, need_view=False) if owner is not None else None


async def _focused(snap: _Snapshot) -> PageTarget | None:
    if snap.focused_backend is None:
        return None
    return await snap.target(snap.focused_backend, need_view=False)


async def _covering(snap: _Snapshot, target: PageTarget) -> str:
    x, y = target.box.center()
    hit = await _hit(snap, x, y)
    label = snap.index.label_of_toggle(target.node_id)     # a hidden checkbox's centre is on its label
    if hit is not None and (snap.index.is_inside(hit, target.node_id)
                            or (label is not None and snap.index.is_inside(hit, label))):
        return ""
    if hit is None:
        return _SOMETHING
    return snap.index.dialog_title(hit, snap.labels) or _SOMETHING


async def _screenshot(client: CdpSender, sid: str, probe: bool) -> bytes:
    shot = await client.send("Page.captureScreenshot", {
        "format": "jpeg", "quality": CU_JPEG_QUALITY, "captureBeyondViewport": False}, session_id=sid)
    jpeg = base64.b64decode((shot.get("result") or {}).get("data", ""))
    return shrink_to_probe(jpeg) if probe else jpeg


async def _geometry(client: CdpSender, sid: str) -> WindowGeometry:
    await client.send("Page.bringToFront", {}, session_id=sid)
    return await read_geometry(client, sid)


async def _busy_marks(client: CdpSender, sid: str) -> int:
    view = _viewport(await client.send("Page.getLayoutMetrics", {}, session_id=sid))
    return await count_busy_marks(client, sid, view.width, view.height)


async def _entry(client: CdpSender, sid: str) -> Mapping[str, Any]:
    history = (await client.send("Page.getNavigationHistory", {}, session_id=sid)).get("result") or {}
    entries, current = history.get("entries") or [], history.get("currentIndex")
    if isinstance(current, int) and 0 <= current < len(entries):
        return entries[current]
    return {}


async def _page_url(client: CdpSender, sid: str) -> str:
    return str((await _entry(client, sid)).get("url", ""))


async def _page_title(client: CdpSender, sid: str) -> str:
    return str((await _entry(client, sid)).get("title", ""))


class CdpPageDriver:
    """``PageDriver`` over a desk's CDP page. ``session`` gives the client and the bot's tab session (it may
    start the computer, as any page call does); ``read_facts`` is the desk's ``read_page``. ``run``, when given,
    runs each method's CDP work (``KeeperDesk``: once more on a fresh page when the connection dies)."""

    def __init__(self, session: SessionSource, read_facts: Callable[[], Awaitable[PageText]], *,
                 run: PageRunner | None = None) -> None:
        self._session = session
        self._read_facts = read_facts
        self._run: PageRunner = run or self._on_session

    async def _on_session(self, call: PageCall[Any]) -> Any:
        client, sid = await self._session()
        return await call(client, sid)

    async def _on_snapshot(self, use: Callable[[_Snapshot], Awaitable[T]]) -> T:
        async def call(client: CdpSender, sid: str) -> T:
            async with _snapshot(client, sid) as snap:
                return await use(snap)
        return await self._run(call)

    async def targets(self) -> tuple[PageTarget, ...]:
        """The interactive controls inside the viewport, in reading order."""
        return await self._on_snapshot(_targets)

    async def target_for(self, node_id: int) -> PageTarget | None:
        """The control a look numbered, read again from the live page; None when it is gone or out of view."""
        return await self._on_snapshot(lambda snap: snap.target(node_id, need_view=True))

    async def areas(self) -> tuple[PageArea, ...]:
        """Fast pages: the page's readable areas (``roost/desk/page_text.py``), each with its visible part."""
        return await self._run(_areas)

    async def area_text(self, node_id: int | None) -> str | None:
        """The readable text of the page (None) or of one area, scrolled-out text included; None when it is gone."""
        return ax_text(await self._run(_ax_nodes), node_id)

    async def link_url(self, node_id: int) -> str:
        """The full address a numbered link goes to, read from the DOM ("" when it is no link)."""
        async def use(snap: _Snapshot) -> str:
            return snap.index.link_url(node_id)
        return await self._on_snapshot(use)

    async def fetch(self, url: str, max_bytes: int) -> bytes:
        """Fast pages, slice 5: the bytes at ``url`` as the bot's own browser fetches them (``page_fetch.py``)."""
        return await self._run(lambda client, sid: fetch_through_browser(client, sid, url, max_bytes))

    async def read_blob(self, url: str, max_bytes: int) -> bytes:
        """Fast pages: the bytes of a ``blob:`` file, read inside this tab's page (``blob_fetch.py``)."""
        return await self._run(lambda client, sid: read_blob(client, sid, url, max_bytes))

    async def find(self, text: str, kind: str, nth: int) -> PageTarget | None:
        matches = [t for t in await self.targets()
                   if same_label(t.text, text) and (kind == "any" or t.kind == kind)]
        return matches[nth - 1] if 0 < nth <= len(matches) else None

    async def node_at(self, x: int, y: int) -> PageTarget | None:
        return await self._on_snapshot(lambda snap: _owner_at(snap, x, y))

    async def focused(self) -> PageTarget | None:
        return await self._on_snapshot(_focused)

    async def covering(self, target: PageTarget) -> str:
        """"" when the target's centre hits the target itself; else what covers it: a dialog's title or
        "something". A centre the browser can't place counts as covered."""
        return await self._on_snapshot(lambda snap: _covering(snap, target))

    async def screenshot(self, *, probe: bool = False) -> bytes:
        """The viewport as a JPEG (no desktop, no address bar). A probe is shrunk to the probe size."""
        return await self._run(lambda client, sid: _screenshot(client, sid, probe))

    async def geometry(self) -> WindowGeometry:
        """Brings the tab to the front, restores a minimized window and reads where it is (amendment 2026-10-21)."""
        return await self._run(_geometry)

    async def url(self) -> str:
        return await self._run(_page_url)

    async def facts(self) -> PageText:
        return await self._read_facts()

    async def lifecycle(self) -> LifecycleView:
        return await self._run(read_lifecycle)

    async def busy_marks(self) -> int:
        return await self._run(_busy_marks)

    async def box_text(self, node_id: int) -> str | None:
        """What the text box holds now (``box_text.py``); None when it can't be read."""
        return await self._run(lambda client, sid: box.read_box(client, sid, node_id))

    async def select_box(self, node_id: int) -> bool:
        """Select everything in the text box, so the next typing replaces it (``box_text.py``)."""
        return await self._run(lambda client, sid: box.select_box(client, sid, node_id))

    async def paste_text(self, node_id: int, text: str) -> str:
        """Put the whole text into the focused text box at once (``box_text.paste_text``): pasted, one_line or
        no_paste. The text goes to the browser only."""
        return await self._run(lambda client, sid: box.paste_text(client, sid, node_id, text))

    async def password_filled(self) -> bool:
        """Whether a password box on the page holds anything (``saved_login_check.py``); never its text."""
        return await self._run(password_filled)

    async def title(self) -> str:
        """The current page's title, from Chromium's own history entry (no page script)."""
        return await self._run(_page_title)


def _viewport(metrics: Mapping[str, Any]) -> Box:
    result = metrics.get("result") or {}
    view = result.get("cssLayoutViewport") or result.get("layoutViewport") or {}
    return Box(x=0, y=0, width=float(view.get("clientWidth") or 0), height=float(view.get("clientHeight") or 0))


def _frames(snap: _Snapshot) -> list[DomNode]:
    """Cross-origin frames (a payment widget) count as one control each: the commit test says unknown."""
    return [n for n in snap.index.all_nodes() if n.tag in ("iframe", "frame")
            and snap.index.cross_origin_frame(n.backend_id)]


async def _hit(snap: _Snapshot, x: int, y: int) -> int | None:
    """The node a real click at (x, y) reaches. ``ignorePointerEventsNone`` stays False: a see-through layer
    (``pointer-events: none``) is skipped, as the mouse skips it, so it never "covers" the control under it."""
    try:
        reply = await snap.client.send("DOM.getNodeForLocation", {
            "x": x, "y": y, "includeUserAgentShadowDOM": True, "ignorePointerEventsNone": False,
        }, session_id=snap.session_id)
    except CdpReplyError:
        return None
    backend = (reply.get("result") or {}).get("backendNodeId")
    return backend if isinstance(backend, int) and snap.index.node(backend) is not None else None


def shrink_to_probe(jpeg: bytes) -> bytes:
    """A small greyscale copy for the "page ready" probe (``CU_READY_PROBE_W`` x ``CU_READY_PROBE_H``)."""
    with Image.open(io.BytesIO(jpeg)) as image:
        small = image.convert("L").resize((CU_READY_PROBE_W, CU_READY_PROBE_H))
    out = io.BytesIO()
    small.save(out, format="JPEG", quality=CU_JPEG_QUALITY)
    return out.getvalue()
