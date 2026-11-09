"""Your own chat (owner, 2026-11-03: "the bot just does what you ask").

In a run your own message started in your 1:1 chat, one that can show a card and is no routine run, the bot changes
what you ask for even after the chat read web content: your records, its memories, its routines, a bot's model and
its own instructions. The approval mode still decides (an Ask card, Auto-edit or a plan step), exactly as in a clean
run; no model check stands in front of it. A routine, a handoff, a room or a helper keeps D3's refusal. A Mac file
keeps its own rule (``mac_edit``'s relaxation), and ``create_bot`` the create check."""

from __future__ import annotations

from typing import Final

from roost.talk.verdict import GateContext

OWNER_CHAT_REASON: Final = "owner_chat_change"

# Owner, 2026-11-05 ("only pay needs confirmation, like Grok"): in your own chat a committing click, typing details
# you gave and the bot's own programs just run; only these commit classes keep their card (a button Roost can't
# read may still be paying, so it keeps the reviewer or its card).
OWNER_CHAT_ACT_REASON: Final = "owner_chat_act"
OWNER_CHAT_STILL_ASKS: frozenset[str] = frozenset({"spend", "unknown"})

# Changes to your own records (tasks, steps, money, notes, documents, projects, memories).
OWNER_CHAT_RECORD_TOOLS: frozenset[str] = frozenset({
    "update_task", "complete_task", "delete_task",
    "update_step", "delete_step", "move_step",
    "update_expense", "delete_expense", "set_budget", "add_topup", "edit_topup", "undo_topup",
    "append_to_note", "update_note", "delete_note",
    "append_to_doc", "update_sheet_cells", "delete_document", "set_document_project",
    "update_project", "forget",
})

# The bot's own things. Their handlers refuse a tainted run themselves, so these run with a clean record context
# (each keeps its Undo or activity line).
OWNER_CHAT_OWN_TOOLS: frozenset[str] = frozenset({
    "remember", "set_bot_model", "update_my_instructions",
    "create_routine", "update_routine", "pause_routine", "resume_routine", "delete_routine",
})

OWNER_CHAT_TOOLS: frozenset[str] = OWNER_CHAT_RECORD_TOOLS | OWNER_CHAT_OWN_TOOLS


def owner_chat_run(ctx: GateContext) -> bool:
    """A run of your own 1:1 chat that can show a card (never a routine, handoff, room or helper)."""
    state = ctx.approval
    return bool(ctx.owner_chat and state is not None and state.cards and state.standing is None)
