"""The day-note tool spec and its gate kind (Board redesign G7). A bot may only add; it never edits or deletes."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

ADD_DAY_NOTE_SPEC = ToolSpec(
    name="add_day_note",
    description=("Add a short note to one day of the user's calendar (a day plan, a reminder of what happened). "
                 "`day` is a date or words like 'tomorrow' or 'viernes'."),
    input_schema={"type": "object", "properties": {
        "day": {"type": "string", "description": "A date (2026-10-21) or words like 'tomorrow' or 'viernes'."},
        "text": {"type": "string", "description": "The note, up to 500 characters."},
    }, "required": ["day", "text"]},
)

DAY_NOTE_TOOL_DEFS: tuple[ToolDef, ...] = (ToolDef(ADD_DAY_NOTE_SPEC, "write_create"),)
