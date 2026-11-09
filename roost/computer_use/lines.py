"""The chat's activity lines for the screen tools (C3 design §10): "Clicked 'Apply'", "Typed into 'Search'
(12 characters)", "Pressed Enter", "Scrolled down", "Looked at the screen", "Waiting for the page".

A line names a control by its label as read from the page, cut to ``CU_LABEL_SHOWN_CHARS``, and never holds
what was typed: only how many characters."""

from __future__ import annotations

from typing import Any, Mapping

from roost.computer_use.models import ActResolution
from roost.constants import CU_APP_LABELS, CU_LABEL_SHOWN_CHARS

LOOK_LINE = "Looked at the screen"
WAIT_LINE = "Waiting for the page"
READ_LINE = "Read the page's text"
READ_PDF_LINE = "Read a PDF"
_NO_LABEL = "the page"


def label_of(r: ActResolution | None) -> str:
    """The control's words as the page shows them, one line, cut short; "the page" when it has none."""
    target = r.target if r is not None else None
    words = " ".join((target.visible_text or target.text).split()) if target is not None else ""
    return words[:CU_LABEL_SHOWN_CHARS] or _NO_LABEL


def _quoted(r: ActResolution | None) -> str:
    label = label_of(r)
    return label if label == _NO_LABEL else f"'{label}'"


def _chars(arguments: Mapping[str, Any]) -> int:
    text = arguments.get("text")
    return len(text) if isinstance(text, str) else 0


def act_line(tool: str, r: ActResolution | None, args: Mapping[str, Any]) -> str:
    """The activity line for one screen tool call."""
    if tool == "look":
        return LOOK_LINE
    if tool == "wait_ready":
        return WAIT_LINE
    if tool == "read_text":
        return READ_LINE
    if tool == "read_pdf":
        return READ_PDF_LINE
    if tool == "scroll":
        return f"Scrolled {'up' if args.get('direction') == 'up' else 'down'}"
    if tool == "click":
        return f"Clicked {_quoted(r)}"
    if tool == "type":
        count = _chars(args)
        return f"Typed into {_quoted(r)} ({count} character{'' if count == 1 else 's'})"
    if tool == "press_key":
        return f"Pressed {args.get('key', 'a key')}"
    if tool == "open_app":
        return open_line(str(args.get("app", "")))
    return _tab_line(tool, args)


def _tab_line(tool: str, args: Mapping[str, Any]) -> str:
    """B1: "Listed the tabs", "Switched to tab 2", "Closed tab 3"."""
    index = args.get("index")
    if tool == "list_tabs":
        return "Listed the tabs"
    if tool == "switch_tab" and isinstance(index, int):
        return f"Switched to tab {index}"
    if tool == "close_tab" and isinstance(index, int):
        return f"Closed tab {index}"
    return tool


def open_line(app: str) -> str:
    """"Opened Files", "Opened geany": a fixed app by its name, a package by its own (already validated) name."""
    return f"Opened {CU_APP_LABELS.get(app, app[:CU_LABEL_SHOWN_CHARS])}"


def screen_line(tool: str, args: Mapping[str, Any]) -> str:
    """A screen act's line (no page, so no label): "Clicked the screen", "Typed on the screen (12 characters)"."""
    if tool == "click":
        return "Clicked the screen"
    if tool == "type":
        count = _chars(args)
        return f"Typed on the screen ({count} character{'' if count == 1 else 's'})"
    return act_line(tool, None, args)


SEND_TITLE = "Send message"        # 2026-10-27: not "Click 'ic-send-filled'"


def card_title(tool: str, r: ActResolution | None, args: Mapping[str, Any]) -> str:
    """What an Ask card asks to do: "Click 'Buy now'", "Type into 'Note'", "Press Enter", "Send message"."""
    if tool == "click" and r is not None and r.commit == "send":
        return SEND_TITLE
    if tool == "type":
        return f"Type into {_quoted(r)}"
    if tool == "press_key":
        return f"Press {args.get('key', 'a key')}"
    return f"Click {_quoted(r)}"
