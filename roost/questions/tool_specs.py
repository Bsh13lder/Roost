"""``note_question``: a non-urgent question the bot answers with a safe default and carries on."""

from __future__ import annotations

from roost.constants import QUESTION_MAX_CHARS
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

NOTE_QUESTION_SPEC = ToolSpec(
    name="note_question",
    description=("Note a question that is NOT urgent in the user's question book, with the safe default you carry on "
                 "with now, instead of asking and waiting. The user may answer later; their answer comes back as their own message. Never use it "
                 "for anything that sends, pays, deletes or can't be undone."),
    input_schema={"type": "object", "properties": {
        "question": {"type": "string", "description": f"The question, up to {QUESTION_MAX_CHARS} characters."},
        "default_choice": {"type": "string", "description": "The safe default you carry on with."},
        "why": {"type": "string", "description": "Why it matters (optional)."},
    }, "required": ["question", "default_choice"]},
)

# No Ask card in front of it: the user answers the book when they like, and nothing waits on that.
QUESTION_TOOL_DEFS: tuple[ToolDef, ...] = (ToolDef(NOTE_QUESTION_SPEC, "write_create", no_ask=True),)
