"""Which topic each write tool belongs to, which tools hit the hard floor, and what a tainted run may relax.

One table, so a new write tool cannot slip past the approval modes unnoticed
(tests/test_gate_approvals.py refuses a write tool with no topic).
"""

from __future__ import annotations

from typing import Mapping

from roost.approvals.models import FloorKind, Topic
from roost.constants import CU_ACT_TOOLS

TOOL_TOPICS: Mapping[str, Topic] = {
    **dict.fromkeys(
        ("add_task", "update_task", "complete_task", "delete_task", "add_step", "update_step", "move_step",
         "delete_step", "add_comment"), "tasks"),
    **dict.fromkeys(
        ("log_expense", "update_expense", "delete_expense", "add_topup", "edit_topup", "undo_topup", "set_budget"),
        "money"),
    **dict.fromkeys(("add_note", "update_note", "append_to_note", "delete_note", "add_day_note"), "notes"),
    **dict.fromkeys(
        ("create_doc", "create_sheet", "append_to_doc", "update_sheet_cells", "delete_document",
         "set_document_project", "make_pdf_from_doc"), "documents"),
    **dict.fromkeys(("create_project", "update_project"), "projects"),
    **dict.fromkeys(("remember", "forget"), "memory"),
    # A bot's own settings: set_my_voice (voice §4) sits with the team's bot settings; its gate rule is its own.
    **dict.fromkeys(("create_bot", "set_bot_model", "set_my_voice"), "team"),
    **dict.fromkeys(
        ("create_routine", "update_routine", "pause_routine", "resume_routine", "delete_routine"), "routines"),
    **dict.fromkeys(("mac_find", "mac_read", "mac_write_new", "mac_edit", "mac_rename", "mac_trash"), "files"),
    # C3: clicks and keys on the bot's own computer; look, wait_ready and scroll are reads with no topic.
    **dict.fromkeys(sorted(CU_ACT_TOOLS), "browsing"),
    # Programs: the bot's own sandbox; read_file and list_files are reads with no topic.
    **dict.fromkeys(("run_program", "write_file"), "programs"),
    # Connectors: a write sends something to another service; "posting" is locked on and on the hard floor.
    "use_connector": "posting",
    # Install an app: software on the bot's own computer, like its programs; always on the hard floor.
    **dict.fromkeys(("install_app", "remove_app"), "programs"),
}

# Tools that always ask, whatever the mode (owner decision 2026-10-22: every app needs the owner's Yes).
FLOOR_TOOLS: Mapping[str, FloorKind] = {"install_app": "install_app", "remove_app": "install_app"}

# The one tool whose tainted-write refusal relaxes, and only in Auto-edit or an accepted plan.
RELAX_TAINTED_TOOLS: frozenset[str] = frozenset({"mac_edit"})

# Tools a tainted run may still ASK for (never do): the card shows exactly what runs and says it is based on
# outside content. A connector write after reading the same API's answer would otherwise never be possible.
# Apps ask in tainted runs too (the owner reads the card, which says it is based on outside content).
ASK_WHEN_TAINTED_TOOLS: frozenset[str] = frozenset({"use_connector", "install_app", "remove_app"})


def topic_of(name: str) -> Topic | None:
    return TOOL_TOPICS.get(name)
