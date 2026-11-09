"""``preview_call``: the card's title for a record tool call (the tool and its main field); ``with_rows`` adds every argument.

Mac tools write their own titles and diffs (``roost/mac/tools.py``); everything else comes through here."""

from __future__ import annotations

from typing import Any, Mapping

from roost.approvals.models import PendingCall, Topic
from roost.constants import APPROVAL_TITLE_MAX_CHARS

_MAIN_FIELDS = ("title", "name", "task", "text", "note", "project", "query", "content")
_PHRASES: Mapping[str, str] = {
    "add_task": "Add a task", "update_task": "Update a task", "complete_task": "Complete a task",
    "delete_task": "Delete a task", "add_step": "Add a step", "update_step": "Update a step",
    "move_step": "Move a step", "delete_step": "Delete a step", "add_comment": "Comment on a task",
    "log_expense": "Log an expense", "update_expense": "Change an expense", "delete_expense": "Delete an expense",
    "add_topup": "Add a top-up", "edit_topup": "Change a top-up", "undo_topup": "Undo a top-up",
    "set_budget": "Set a budget", "add_note": "Add a note", "update_note": "Change a note",
    "append_to_note": "Add to a note", "delete_note": "Delete a note", "add_day_note": "Add a day note",
    "create_doc": "Create a document", "create_sheet": "Create a sheet", "append_to_doc": "Add to a document",
    "update_sheet_cells": "Change a sheet", "delete_document": "Delete a document",
    "set_document_project": "File a document in a project", "make_pdf_from_doc": "Make a PDF",
    "create_project": "Create a project", "update_project": "Change a project", "remember": "Remember",
    "forget": "Forget", "create_bot": "Create a bot", "set_bot_model": "Change a bot's model",
    "set_my_voice": "Change my voice",
}


def _cap(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def call_phrase(name: str) -> str:
    """What a call of ``name`` does, in the card's words ("Delete a task")."""
    return _PHRASES.get(name) or name.replace("_", " ").capitalize()


def _main_value(arguments: Mapping[str, Any]) -> tuple[str | None, str]:
    for key in _MAIN_FIELDS:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return None, ""


def preview_call(name: str, arguments: Mapping[str, Any], topic: Topic | None) -> PendingCall:
    """A card step for ``name`` called with ``arguments``: it stores the call exactly as the bot made it."""
    _, value = _main_value(arguments)
    phrase = call_phrase(name)
    title = f"{phrase}: “{_cap(value, APPROVAL_TITLE_MAX_CHARS)}”" if value else phrase
    return PendingCall(
        tool=name, arguments=dict(arguments), topic=topic, title=_cap(title, APPROVAL_TITLE_MAX_CHARS),
    )
