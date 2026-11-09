"""The page's DOM as a read-only index for C3's page targets (``roost/desk/page_targets.py``).

``DomIndex.build`` takes the tree ``DOM.getDocument(depth=-1, pierce=true)`` returns (Chromium's own parse, no page
script runs) and answers the structural questions the commit test needs: the closest form and its method and default
submit control, the dialog a control sits in, a cookie or consent container, a link's host, a cross-origin frame.

**Text-box values are never read** (C2's rule): the ``value`` attribute is dropped when the index is built, and the
text inside a ``textarea`` (its typed or default content) is never kept. Text nodes are kept only to tell whether a
form mentions a code (one-time-code fields count as secret).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urljoin, urlsplit

from roost.computer_use.commit_words import CONSENT_CONTAINER_MARKS, normalise

_ELEMENT = 1
_TEXT = 3
_DROPPED_ATTRS = frozenset({"value"})                # a field's value is never read
_SILENT_TAGS = frozenset({"textarea", "script", "style", "noscript", "template"})
_USER_AGENT_SHADOW = "user-agent"              # CDP's shadowRootType for Chromium's own control parts
_DIALOG_ROLES = frozenset({"dialog", "alertdialog"})
_SUBMIT_BUTTON_TYPES = frozenset({"", "submit"})
_SUBMIT_INPUT_TYPES = frozenset({"submit", "image"})
_TOGGLE_INPUT_TYPES = frozenset({"checkbox", "radio"})
_SAME_ORIGIN_FRAME_SRC = ("", "about:blank", "about:srcdoc")
# Consent banners by their container's id or class; the marks shared with the commit test plus common CMP names.
_CONSENT_MARKS = (*CONSENT_CONTAINER_MARKS, "onetrust", "cookiebot", "didomi", "usercentrics", "quantcast")
# Words that say a form asks for a code (English and Spanish, normalised).
_CODE_WORDS = ("code", "codigo", "otp", "one time", "passcode", "verification", "verificacion", "2fa", "pin", "token")
_CONSENT_ATTRS = ("id", "class", "aria-label", "data-testid")
_DIALOG_FALLBACK = "dialog"


@dataclass(frozen=True)
class DomNode:
    backend_id: int
    tag: str                                  # lowercase local name; "#text" for text
    attrs: Mapping[str, str]                  # never holds "value"
    parent: int | None
    children: tuple[int, ...]
    text: str = ""                            # text nodes outside textarea/script/style only
    browser_part: bool = False                # inside a user-agent shadow root (an <input>'s inner editor)


@dataclass(frozen=True)
class FormFacts:
    method: str                               # "get", "post" or "dialog"; "" when not in a form
    submit_text: str                          # the default submit control's label
    is_submit: bool                           # the node is one of its form's submit controls
    mentions_code: bool
    method_given: bool = False                # the form says its method itself (a scripted form usually doesn't)


_NO_FORM = FormFacts(method="", submit_text="", is_submit=False, mentions_code=False)


def _attrs(flat: list[Any] | None) -> Mapping[str, str]:
    items = list(flat or ())
    pairs = zip(items[0::2], items[1::2])
    return MappingProxyType({str(k).lower(): str(v) for k, v in pairs if str(k).lower() not in _DROPPED_ATTRS})


def _tag(raw: Mapping[str, Any]) -> str:
    return str(raw.get("localName") or raw.get("nodeName") or "").lower()


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


def _has_word(text: str, word: str) -> bool:
    return f" {word} " in f" {text} "


class DomIndex:
    """Every element and text node by backend node id, built once per snapshot; never changed after."""

    def __init__(self, nodes: Mapping[int, DomNode], page_url: str) -> None:
        self._nodes = MappingProxyType(dict(nodes))
        self._page_url = page_url

    @classmethod
    def build(cls, root: Mapping[str, Any], page_url: str) -> "DomIndex":
        nodes: dict[int, DomNode] = {}
        pending: list[tuple[Mapping[str, Any], int | None, bool, bool]] = [(root, None, False, False)]
        while pending:
            raw, parent, silent, inner = pending.pop()
            backend = raw.get("backendNodeId")
            if not isinstance(backend, int):
                continue
            kids = [*(raw.get("children") or ()), *([raw["contentDocument"]] if raw.get("contentDocument") else ()),
                    *(raw.get("shadowRoots") or ())]
            inner = inner or raw.get("shadowRootType") == _USER_AGENT_SHADOW
            tag = _tag(raw)
            is_text = raw.get("nodeType") == _TEXT
            text = "" if (silent or not is_text) else str(raw.get("nodeValue") or "")
            child_ids = tuple(k["backendNodeId"] for k in kids if isinstance(k.get("backendNodeId"), int))
            nodes[backend] = DomNode(backend_id=backend, tag="#text" if is_text else tag, attrs=_attrs(
                raw.get("attributes")), parent=parent, children=child_ids, text=text, browser_part=inner)
            child_silent = silent or tag in _SILENT_TAGS
            # a ::before/::after is where a click lands on a drawn radio or tick (Wizz Air, 2026-11-04): it is
            # indexed under the element it draws, for the hit test only, never as a child (no text, no control)
            pseudo = [(kid, backend, True, inner) for kid in reversed(raw.get("pseudoElements") or ())]
            pending.extend([*pseudo, *((kid, backend, child_silent, inner) for kid in reversed(kids))])
        return cls(nodes, page_url)

    def node(self, backend_id: int) -> DomNode | None:
        return self._nodes.get(backend_id)

    def browser_part(self, backend_id: int) -> bool:
        """True for Chromium's own parts of a control (an <input>'s inner editor): the control is its host."""
        node = self._nodes.get(backend_id)
        return node is not None and node.browser_part

    def host_of(self, backend_id: int) -> int:
        """The node itself, or for a browser part the first ancestor outside the user-agent shadow root."""
        return next((n.backend_id for n in self.ancestors(backend_id, include_self=True) if not n.browser_part),
                    backend_id)

    def all_nodes(self) -> tuple[DomNode, ...]:
        return tuple(self._nodes.values())

    def ancestors(self, backend_id: int, *, include_self: bool = False) -> Iterator[DomNode]:
        node = self._nodes.get(backend_id)
        if node is not None and include_self:
            yield node
        while node is not None and node.parent is not None:
            node = self._nodes.get(node.parent)
            if node is not None:
                yield node

    def is_inside(self, backend_id: int, ancestor_id: int) -> bool:
        """True when ``backend_id`` is ``ancestor_id`` or below it."""
        return any(n.backend_id == ancestor_id for n in self.ancestors(backend_id, include_self=True))

    def descendants(self, backend_id: int) -> Iterator[DomNode]:
        """Document order, the node itself excluded."""
        start = self._nodes.get(backend_id)
        stack = list(reversed(start.children)) if start else []
        while stack:
            node = self._nodes.get(stack.pop())
            if node is not None:
                yield node
                stack.extend(reversed(node.children))

    def text_under(self, backend_id: int) -> str:
        return " ".join(n.text for n in self.descendants(backend_id) if n.text)

    # -- the facts the commit test reads ------------------------------------------------------------------

    def dialog_of(self, backend_id: int) -> DomNode | None:
        return next((n for n in self.ancestors(backend_id, include_self=True) if _is_dialog(n)), None)

    def in_consent(self, backend_id: int) -> bool:
        for node in self.ancestors(backend_id, include_self=True):
            marks = " ".join(node.attrs.get(name, "") for name in _CONSENT_ATTRS).lower()
            if any(mark in marks for mark in _CONSENT_MARKS):
                return True
        return False

    def link_host(self, backend_id: int) -> str:
        url = self.link_url(backend_id)
        return (urlsplit(url).hostname or "").lower() if url else ""

    def link_url(self, backend_id: int) -> str:
        """The full address the nearest link around the node goes to ("" for none, a ``#`` or a script link)."""
        node = next((n for n in self.ancestors(backend_id, include_self=True) if n.tag == "a"), None)
        href = node.attrs.get("href", "").strip() if node else ""
        if not href or href.startswith(("#", "javascript:")):
            return ""
        return urljoin(self._page_url, href)

    def cross_origin_frame(self, backend_id: int) -> bool:
        """True when the node is (or sits in) an iframe whose address is another origin than the page's."""
        for node in self.ancestors(backend_id, include_self=True):
            if node.tag in ("iframe", "frame"):
                src = node.attrs.get("src", "").strip()
                if src in _SAME_ORIGIN_FRAME_SRC:
                    continue
                if _origin(urljoin(self._page_url, src)) != _origin(self._page_url):
                    return True
        return False

    def form_facts(self, backend_id: int, labels: Mapping[int, str]) -> FormFacts:
        form = next((n for n in self.ancestors(backend_id) if n.tag == "form"), None)
        if form is None:
            return _NO_FORM
        given = form.attrs.get("method", "").strip().lower()
        submits = [n.backend_id for n in self.descendants(form.backend_id) if _is_submit(n)]
        submit_text = labels.get(submits[0], "") if submits else ""
        return FormFacts(method=given or "get", submit_text=submit_text, is_submit=backend_id in submits,
                         mentions_code=self._mentions_code(form, backend_id, labels), method_given=bool(given))

    def form_has_password(self, backend_id: int) -> bool:
        """B3: the box's form also holds a password box (a sign-in form)."""
        form = next((n for n in self.ancestors(backend_id) if n.tag == "form"), None)
        return form is not None and any(n.tag == "input" and n.attrs.get("type", "").strip().lower() == "password"
                                        for n in self.descendants(form.backend_id))

    def form_has_card(self, backend_id: int) -> bool:
        """The Pay card: the control's form also holds a card box (a "Continue" there pays)."""
        from roost.desk.card_names import card_part      # here: card_names builds on commit_words
        form = next((n for n in self.ancestors(backend_id) if n.tag == "form"), None)
        if form is None:
            return False
        return any(card_part({"tag": n.tag, "input_type": n.attrs.get("type", "").strip().lower(),
                              "autocomplete": n.attrs.get("autocomplete", ""),
                              "field_names": " ".join(n.attrs.get(k, "") for k in ("id", "name", "placeholder",
                                                                                     "aria-label"))})
                   for n in self.descendants(form.backend_id) if n.tag in ("input", "select"))

    def in_search(self, backend_id: int) -> bool:
        """True inside a search landmark: ``role="search"`` or a ``<search>`` element."""
        return any(n.tag == "search" or n.attrs.get("role", "").strip().lower() == "search"
                   for n in self.ancestors(backend_id))

    def own_words(self, backend_id: int) -> str:
        """The words inside a control that an ``aria-label`` or ``aria-labelledby`` names otherwise; "" when
        its name already comes from them. Text boxes keep no words (their text is what was typed)."""
        node = self._nodes.get(backend_id)
        if node is None or not ({"aria-label", "aria-labelledby"} & set(node.attrs)):
            return ""
        if node.tag in ("input", "textarea") or node.attrs.get("contenteditable", "").strip().lower() not in (
                "", "false"):
            return ""
        return " ".join(self.text_under(backend_id).split())

    def _mentions_code(self, form: DomNode, backend_id: int, labels: Mapping[int, str]) -> bool:
        field = self._nodes.get(backend_id)
        parts = [self.text_under(form.backend_id), labels.get(backend_id, ""),
                 *(form.attrs.get(k, "") for k in ("id", "name", "class", "aria-label", "action"))]
        if field is not None:
            parts.extend(field.attrs.get(k, "") for k in ("id", "name", "placeholder", "aria-label"))
        words = normalise(" ".join(parts))
        return any(_has_word(words, word) for word in _CODE_WORDS)

    # -- a checkbox or radio drawn by its label (owner, 2026-11-04: Upwork's sr-only "Yes, I understand.") ------

    def label_of_toggle(self, backend_id: int) -> int | None:
        """The ``<label>`` of a checkbox or radio input: the one around it, or one whose ``for`` names its id."""
        node = self._nodes.get(backend_id)
        if node is None or not _is_toggle(node):
            return None
        around = next((n.backend_id for n in self.ancestors(backend_id) if n.tag == "label"), None)
        if around is not None:
            return around
        own_id = node.attrs.get("id", "")
        return next((n.backend_id for n in self._nodes.values()
                     if own_id and n.tag == "label" and n.attrs.get("for", "") == own_id), None)

    def toggle_of_label(self, backend_id: int) -> int | None:
        """The checkbox or radio a ``<label>`` clicks: the one its ``for`` names, else the first one inside it."""
        node = self._nodes.get(backend_id)
        if node is None or node.tag != "label":
            return None
        named = node.attrs.get("for", "")
        if named:
            return next((n.backend_id for n in self._nodes.values() if n.attrs.get("id", "") == named
                         and _is_toggle(n)), None)
        return next((n.backend_id for n in self.descendants(backend_id) if _is_toggle(n)), None)

    def dialog_title(self, backend_id: int, labels: Mapping[int, str]) -> str:
        dialog = self.dialog_of(backend_id)
        if dialog is None:
            return ""
        return labels.get(dialog.backend_id) or dialog.attrs.get("aria-label", "") or _DIALOG_FALLBACK


def _is_dialog(node: DomNode) -> bool:
    return (node.tag == "dialog" or node.attrs.get("role", "").lower() in _DIALOG_ROLES
            or node.attrs.get("aria-modal", "").lower() == "true")


def _is_toggle(node: DomNode) -> bool:
    return node.tag == "input" and node.attrs.get("type", "").strip().lower() in _TOGGLE_INPUT_TYPES


def _is_submit(node: DomNode) -> bool:
    kind = node.attrs.get("type", "").strip().lower()
    if node.tag == "button":
        return kind in _SUBMIT_BUTTON_TYPES
    return node.tag == "input" and kind in _SUBMIT_INPUT_TYPES
