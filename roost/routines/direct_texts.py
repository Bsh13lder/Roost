"""What the direct routine tools tell the bot. Kept apart from ``direct_tools.py`` so the tool specs (and the gate,
through the catalog) can name the tainted refusal without importing the handler."""

from __future__ import annotations

from typing import Final

_PROPOSE_WAY: Final = (
    "use propose_routine, propose_routine_change or propose_routine_pause instead: the user's Approve on the card "
    "writes it. In the user's own chat with you, the direct tools just work."
)
TAINTED_TEXT: Final = (
    "Refused: this task read outside content and nobody is here to ask, so I don't change routines directly. "
    "To set one up or change it, " + _PROPOSE_WAY
)
NOT_HERE_TEXT: Final = (
    "Refused: I change routines directly only in the user's own chat, when their message asked for it. Here, "
    + _PROPOSE_WAY
)
NOT_YOURS_TEXT: Final = "Refused: that isn't one of your routines."
BAD_ARGS_TEXT: Final = "Refused: {name} needs valid arguments (see its description)."
NOTHING_TEXT: Final = "Refused: say what to change (name, instructions, schedule or watch)."
WATCH_NOT_NAMED_TEXT: Final = (
    "Refused: I watch only a page the user named in their own messages here (its address, or the site by name), "
    "never a link from a page. Ask them which page to watch."
)

CREATED_TEXT: Final = "Created routine “{name}”. Next run: {next}."
CHANGED_TEXT: Final = "Changed routine “{name}”."
PAUSED_TEXT: Final = "Paused routine “{name}”."
RESUMED_TEXT: Final = "Resumed routine “{name}”."
DELETED_TEXT: Final = "Deleted routine “{name}”."

ACTIVITY: Final = {
    "create_routine": "creating a routine", "update_routine": "changing a routine",
    "pause_routine": "pausing a routine", "resume_routine": "resuming a routine",
    "delete_routine": "deleting a routine",
}
CARD_VERBS: Final = {
    "create_routine": "Create routine", "update_routine": "Change routine", "pause_routine": "Pause routine",
    "resume_routine": "Resume routine", "delete_routine": "Delete routine",
}
