"""What a text box holds, and selecting all of it (owner, 2026-10-27: Gela's Russian text went in after the old
Spanish draft, and one letter was lost on the way).

Before ``type`` the runner selects everything already in the box, so the typed text replaces it; after, it reads the
box back and compares. Both run in an **isolated world** named ``roost-box`` (the page's own script cannot redefine
``value``, ``innerText`` or the selection calls in it), on the one element the resolver found, by its backend node
id. Nothing is typed or clicked here: input still goes through ``roost-input`` alone. The text read back stays in
memory: it is never logged, audited or put in an event.

Paste (owner, 2026-11-01, "make it smooth like Grok"): ``paste_text`` puts the whole text into the box at once with
CDP ``Input.insertText`` on the bot's own page, after checking in ``roost-box`` that the box the resolver found is the
focused one. ``insertText`` commits text as an input method does, with no key events, so a line break inside it is a
line break in a ``<textarea>`` or a content-editable box and can never act as Enter (no keydown, no implicit
submission). A one-line ``<input>`` would drop it silently, so text with a line break is refused there
(``ONE_LINE``) and nothing goes in. The text goes to the browser only, never to a log."""

from __future__ import annotations

import contextlib
import unicodedata
from typing import Any

from roost.constants import CU_BOX_TEXT_MAX_CHARS
from roost.desk.cdp import CdpReplyError
from roost.desk.page_geometry import CdpSender

BOX_WORLD = "roost-box"
PASTED, ONE_LINE, NO_PASTE = "pasted", "one_line", "no_paste"
_LINE_BREAKS = ("\n", "\r")
_MULTI_LINE_BOX, _ONE_LINE_BOX = "lines", "line"

# Page-side, run on the element itself. An <input> or <textarea> gives its value; a content-editable box (WhatsApp's
# message box) its rendered text. Anything else is no text box: null.
_READ = """function (max) {
  const tag = this.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return String(this.value).slice(0, max);
  if (this.isContentEditable) return String(this.innerText).slice(0, max);
  return null;
}"""

_SELECT = """function () {
  const tag = this.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") { this.select(); return true; }
  if (!this.isContentEditable) return false;
  const doc = this.ownerDocument;
  const range = doc.createRange();
  range.selectNodeContents(this);
  const selection = doc.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}"""

# Page-side: "line" for a focused one-line <input>, "lines" for a focused <textarea> or content-editable box (or a
# part of one), else null. Focus is followed into open shadow roots.
_PASTE_KIND = """function () {
  let active = this.ownerDocument.activeElement;
  while (active && active.shadowRoot && active.shadowRoot.activeElement) active = active.shadowRoot.activeElement;
  if (!active) return null;
  const tag = this.tagName;
  if (active === this && tag === "TEXTAREA") return "lines";
  if (active === this && tag === "INPUT") return "line";
  const editing = this.isContentEditable && (active === this || this.contains(active));
  if (editing || (active.isContentEditable && active.contains(this))) return "lines";
  return null;
}"""


def has_line_breaks(text: str) -> bool:
    return any(mark in text for mark in _LINE_BREAKS)


def same_text(held: str, meant: str) -> bool:
    """The box holds what was meant: the same letters in the same order. Unicode forms, no-break spaces and runs of
    white space (a content-editable box adds line breaks of its own) don't count. When the meant text has line
    breaks (a cover letter's paragraphs), each must still be a break, and only there; how many in a row and in which
    form (``\\r\\n``, an editor's extra blank line) doesn't count."""
    if not has_line_breaks(meant):
        return _plain(held) == _plain(meant)
    return _lines(held) == _lines(meant)


def _lines(text: str) -> tuple[str, ...]:
    """The text's non-blank lines, each with its spacing made plain."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return tuple(line for line in map(_plain, lines) if line)


def _plain(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).replace(" ", " ").split())


async def _object_id(client: CdpSender, session_id: str, backend_id: int) -> str | None:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = (((tree.get("result") or {}).get("frameTree") or {}).get("frame") or {}).get("id")
    if not isinstance(frame_id, str) or not frame_id:
        return None
    world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": BOX_WORLD},
                              session_id=session_id)
    context_id = (world.get("result") or {}).get("executionContextId")
    if not isinstance(context_id, int):
        return None
    node = await client.send("DOM.resolveNode", {"backendNodeId": backend_id, "executionContextId": context_id},
                             session_id=session_id)
    object_id = ((node.get("result") or {}).get("object") or {}).get("objectId")
    return object_id if isinstance(object_id, str) else None


async def _call(client: CdpSender, session_id: str, backend_id: int, function: str,
                arguments: list[dict[str, Any]]) -> Any:
    """The function's value on that element, or None when the element is gone, in another frame, or threw."""
    try:
        object_id = await _object_id(client, session_id, backend_id)
        if object_id is None:
            return None
        reply = await client.send("Runtime.callFunctionOn", {
            "functionDeclaration": function, "objectId": object_id, "arguments": arguments, "returnByValue": True,
        }, session_id=session_id)
    except CdpReplyError:
        return None
    with contextlib.suppress(CdpReplyError):
        await client.send("Runtime.releaseObject", {"objectId": object_id}, session_id=session_id)
    result = reply.get("result") or {}
    if result.get("exceptionDetails"):
        return None
    return (result.get("result") or {}).get("value")


async def read_box(client: CdpSender, session_id: str, backend_id: int) -> str | None:
    """The text the box holds now (at most ``CU_BOX_TEXT_MAX_CHARS``), or None when it can't be read."""
    value = await _call(client, session_id, backend_id, _READ, [{"value": CU_BOX_TEXT_MAX_CHARS}])
    return value if isinstance(value, str) else None


async def select_box(client: CdpSender, session_id: str, backend_id: int) -> bool:
    """Select everything in the box, so the next typing replaces it. False when it is no text box or is gone."""
    return await _call(client, session_id, backend_id, _SELECT, []) is True


async def paste_text(client: CdpSender, session_id: str, backend_id: int, text: str) -> str:
    """Put ``text`` into the focused box at once (``Input.insertText``). ``PASTED``; ``ONE_LINE`` when the box is a
    one-line ``<input>`` and the text has a line break (nothing is sent); ``NO_PASTE`` when the box is not the
    focused one, is gone, sits in another frame, or the browser refused the insert."""
    kind = await _call(client, session_id, backend_id, _PASTE_KIND, [])
    if kind not in (_MULTI_LINE_BOX, _ONE_LINE_BOX):
        return NO_PASTE
    if kind == _ONE_LINE_BOX and has_line_breaks(text):
        return ONE_LINE
    try:
        await client.send("Input.insertText", {"text": text}, session_id=session_id)
    except CdpReplyError:
        return NO_PASTE
    return PASTED
