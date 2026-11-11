"""A run's steps in plain words, for the activity pill (docs/plans/2026-10-23-roost-activity-pill.md).

One table says what each tool is doing in words the owner reads ("Searched the web for …", "Ran a program",
"Added a task: …"). Only three arguments ever reach a line: a web search's query, a new task's title and the
teammate an ``ask_bot`` goes to; a page or a fetch adds its host name alone. Never a command, typed text, a file's
contents, a path or a URL's path or query."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from roost.computer_use.steps import step_host
from roost.constants import COMPUTER_STEP_LINE_MAX, CU_APP_LABELS

PLAIN_KINDS = frozenset({
    "think", "search", "read", "computer", "program", "file", "tasks", "notes", "money", "calendar", "bots",
    "memory", "message", "other",
})
FALLBACK_LINE = "Worked on it"
THINK_LINE = "Thinking"
WRITING_LINE = "Writing the reply"
_QUOTED_MAX = 60
_FETCH = re.compile(r"^\s*(?:curl|wget)\b[^\n]*?\bhttps?://([^/\s'\"|;&`$()<>]+)")


@dataclass(frozen=True)
class PlainStep:
    kind: str
    line: str
    host: str | None = None


def _clip(text: Any, limit: int = _QUOTED_MAX) -> str | None:
    if not isinstance(text, str):
        return None
    words = " ".join(text.split())
    if not words:
        return None
    return words if len(words) <= limit else words[: limit - 1].rstrip() + "…"


_WORDS: Mapping[str, tuple[str, str]] = MappingProxyType({
    # reading and the screen
    "read_page": ("read", "Read the page"),
    "look": ("computer", "Looked at the screen"), "wait_ready": ("computer", "Waited for the page"),
    "scroll": ("computer", "Scrolled"), "click": ("computer", "Clicked on the screen"),
    "read_text": ("computer", "Read the page's text"), "read_pdf": ("computer", "Read a PDF"),
    "use_saved_login": ("computer", "Filled a saved login"),
    "use_vault_password": ("computer", "Signed in with a saved password"),
    "send_screenshot": ("computer", "Sent you its screen"),
    "type": ("computer", "Typed in a box"), "press_key": ("computer", "Pressed a key"),
    "list_tabs": ("computer", "Checked the open tabs"), "switch_tab": ("computer", "Switched tabs"),
    "close_tab": ("computer", "Closed a tab"), "install_app": ("computer", "Installed an app"),
    "remove_app": ("computer", "Removed an app"), "list_apps": ("computer", "Checked its apps"),
    # its workspace and your Mac
    "write_file": ("file", "Wrote a file"), "read_file": ("file", "Read a file"),
    "list_files": ("file", "Looked through its files"), "mac_find": ("file", "Looked in your Mac folders"),
    "mac_read": ("file", "Read a file on your Mac"), "mac_write_new": ("file", "Saved a new file on your Mac"),
    "mac_edit": ("file", "Changed a file on your Mac"), "mac_rename": ("file", "Renamed a file on your Mac"),
    "mac_trash": ("file", "Moved a file on your Mac to the trash"),
    # tasks
    "update_task": ("tasks", "Updated a task"), "complete_task": ("tasks", "Finished a task"),
    "delete_task": ("tasks", "Deleted a task"), "list_tasks": ("tasks", "Checked your tasks"),
    "add_step": ("tasks", "Added a step to a task"), "update_step": ("tasks", "Updated a task's step"),
    "delete_step": ("tasks", "Removed a task's step"), "move_step": ("tasks", "Moved a task's step"),
    "add_comment": ("tasks", "Commented on a task"), "list_comments": ("tasks", "Read a task's comments"),
    # notes, documents, its plan and journal
    "add_note": ("notes", "Wrote a note"), "append_to_note": ("notes", "Added to a note"),
    "update_note": ("notes", "Updated a note"), "delete_note": ("notes", "Deleted a note"),
    "read_note": ("notes", "Read a note"), "find_notes": ("notes", "Searched your notes"),
    "create_doc": ("notes", "Started a document"), "create_sheet": ("notes", "Started a sheet"),
    "append_to_doc": ("notes", "Added to a document"), "update_sheet_cells": ("notes", "Edited a sheet"),
    "read_document": ("notes", "Read a document"), "list_documents": ("notes", "Looked through documents"),
    "delete_document": ("notes", "Deleted a document"), "make_pdf_from_doc": ("notes", "Made a PDF"),
    "set_document_project": ("notes", "Filed a document in a project"),
    "journal_append": ("notes", "Wrote in its journal"), "journal_read": ("notes", "Read its journal"),
    "add_day_note": ("notes", "Added a day note"), "plan_add": ("notes", "Added to its plan"),
    "plan_update": ("notes", "Updated its plan"), "plan_complete": ("notes", "Ticked off a plan item"),
    "plan_read": ("notes", "Read its plan"),
    # money and projects
    "log_expense": ("money", "Logged an expense"), "update_expense": ("money", "Updated an expense"),
    "delete_expense": ("money", "Deleted an expense"), "list_expenses": ("money", "Checked the expenses"),
    "money_summary": ("money", "Checked the money"), "set_budget": ("money", "Set a budget"),
    "add_topup": ("money", "Added a top-up"), "edit_topup": ("money", "Changed a top-up"),
    "undo_topup": ("money", "Undid a top-up"), "create_project": ("money", "Created a project"),
    "update_project": ("money", "Updated a project"), "get_project": ("money", "Checked a project"),
    "list_projects": ("money", "Checked the projects"),
    # time and routines
    "get_time": ("calendar", "Checked the time"), "create_routine": ("calendar", "Set up a routine"),
    "load_tools": ("other", "Got more tools ready"),
    "update_routine": ("calendar", "Changed a routine"), "pause_routine": ("calendar", "Paused a routine"),
    "resume_routine": ("calendar", "Resumed a routine"), "delete_routine": ("calendar", "Deleted a routine"),
    "list_routines": ("calendar", "Checked its routines"), "propose_routine": ("calendar", "Suggested a routine"),
    "propose_routine_change": ("calendar", "Suggested a routine change"),
    "propose_routine_pause": ("calendar", "Suggested pausing a routine"),
    "finish_routine": ("calendar", "Finished this routine"),
    # the team
    "list_bots": ("bots", "Checked the team"), "create_bot": ("bots", "Made a new bot"),
    "suggest_bot": ("bots", "Suggested a new bot"), "suggest_model": ("bots", "Suggested a model"),
    "set_bot_model": ("bots", "Changed a bot's model"), "set_my_voice": ("bots", "Changed my voice"),
    # memory, skills and instructions
    "remember": ("memory", "Remembered something"), "recall": ("memory", "Looked in its memory"),
    "forget": ("memory", "Forgot something"), "search_chat": ("memory", "Searched earlier chats"),
    "update_my_instructions": ("memory", "Updated its instructions"),
    "propose_instructions_update": ("memory", "Suggested new instructions"),
    "list_skills": ("memory", "Checked the skills"), "read_skill": ("memory", "Read a skill"),
    "search_skills": ("memory", "Searched the skills"),
    "propose_skill": ("memory", "Suggested a skill"), "propose_skill_change": ("memory", "Suggested a skill change"),
    # asking you
    "ask_choice": ("message", "Asked you to choose"), "ask_for_help": ("message", "Asked you for help"),
    "request_sign_in": ("message", "Asked you to sign in"), "ask_secret_field": ("message", "Asked you to type a code"),
    "note_question": ("message", "Noted a question for you"),
    # services
    "use_connector": ("other", "Used a connected service"), "list_connectors": ("other", "Checked the services"),
    "request_connector": ("other", "Asked for a service key"),
})


# The table's own words, which never hold an argument (lessons read only these: roost/lessons/steps.py).
FIXED_LINES = frozenset(line for _, line in _WORDS.values()) | {FALLBACK_LINE}


def _search(args: Mapping[str, Any]) -> PlainStep:
    query = _clip(args.get("query"))
    return PlainStep("search", f"Searched the web for “{query}”" if query else "Searched the web")


def _open_page(args: Mapping[str, Any]) -> PlainStep:
    host = step_host(str(args.get("url", "")))
    return PlainStep("read", f"Opened {host}" if host else "Opened a page", host)


def _program(args: Mapping[str, Any]) -> PlainStep:
    found = _FETCH.match(str(args.get("command", "")))
    host = step_host(f"https://{found.group(1)}") if found else None
    return PlainStep("program", f"Checked that {host} answers", host) if host else PlainStep("program", "Ran a program")


def _add_task(args: Mapping[str, Any]) -> PlainStep:
    title = _clip(args.get("title"))
    return PlainStep("tasks", f"Added a task: {title}" if title else "Added a task")


def _ask_bot(args: Mapping[str, Any]) -> PlainStep:
    name = _clip(args.get("bot"), 40)
    return PlainStep("bots", f"Asked {name}" if name else "Asked a teammate")


def _helpers(args: Mapping[str, Any]) -> PlainStep:
    helpers = args.get("helpers")
    count = len(helpers) if isinstance(helpers, list) else 0
    words = {0: "Sent helpers", 1: "Sent a helper"}.get(count, f"Sent {count} helpers")
    return PlainStep("bots", words)


def _open_app(args: Mapping[str, Any]) -> PlainStep:
    label = CU_APP_LABELS.get(str(args.get("app", "")))
    return PlainStep("computer", f"Opened {label}" if label else "Opened an app")


_SPECIAL: Mapping[str, Callable[[Mapping[str, Any]], PlainStep]] = MappingProxyType({
    "web_search": _search, "open_page": _open_page, "run_program": _program, "add_task": _add_task,
    "ask_bot": _ask_bot, "open_app": _open_app, "send_helpers": _helpers,
})


def plain_step(tool: str, arguments: Mapping[str, Any]) -> PlainStep:
    """The step's kind, its plain words (at most ``COMPUTER_STEP_LINE_MAX`` characters) and its host, if any."""
    special = _SPECIAL.get(tool)
    if special is not None:
        step = special(arguments if isinstance(arguments, Mapping) else {})
    else:
        kind, line = _WORDS.get(tool, ("other", FALLBACK_LINE))
        step = PlainStep(kind, line)
    return PlainStep(step.kind, step.line[:COMPUTER_STEP_LINE_MAX], step.host)
