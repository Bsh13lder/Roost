"""The notes tool specs and gate kinds (M2 D1; projects hub H12). Argument names and
meanings follow LazyClaw's LazyBrain note skills (save / update / delete a
note, title + markdown content + tags); the descriptions are ours."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.tags.rules import TOPIC_TAGS_SCHEMA
from roost.talk.tool_def import ToolDef

_NOTE_REF = {"type": "string", "description": "The note's id, or its title (or a unique part of it)."}
_TAGS = TOPIC_TAGS_SCHEMA
_PROJECT = {"type": "string", "description": "One of the user's projects, by name or id. Name it exactly."}

ADD_NOTE_SPEC = ToolSpec(
    name="add_note",
    description=("Save a note for the user (the user's own notes; every bot uses them): markdown text, an optional "
                 "title (otherwise its first line) and tags. Link other notes with [[Their Title]]; "
                 "#hashtags in the text become tags. Save what the user asks you to note right away."),
    input_schema={"type": "object", "properties": {
        "content": {"type": "string", "description": "The note, in markdown."},
        "title": {"type": "string", "description": "Short title, e.g. 'Ana'."},
        "tags": _TAGS,
        "project": {**_PROJECT, "description": "Optional: the project it belongs to, by name or id."},
    }, "required": ["content"]},
)
FIND_NOTES_SPEC = ToolSpec(
    name="find_notes",
    description=("Search the user's notes: every word must appear in a note's title, tags or text (case and "
                 "accents don't matter). Best matches first; an empty query lists the newest notes. "
                 "Search before you answer from memory."),
    input_schema={"type": "object", "properties": {
        "query": {"type": "string", "description": "Words to look for, e.g. 'orchids'."},
        "tag": {"type": "string", "description": "Only notes with this tag."},
        "project": {**_PROJECT, "description": "Only notes in this project, by name or id."},
    }},
)
READ_NOTE_SPEC = ToolSpec(
    name="read_note",
    description="Read one note in full: its text, tags and the notes it links to.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)
APPEND_TO_NOTE_SPEC = ToolSpec(
    name="append_to_note",
    description="Add markdown text to the end of a note. Name the note exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "text": {"type": "string", "description": "What to add."},
    }, "required": ["note", "text"]},
)
UPDATE_NOTE_SPEC = ToolSpec(
    name="update_note",
    description=("Replace a note's title, text or tags, or move it to another project. Name the note exactly; if "
                 "two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "note": _NOTE_REF, "title": {"type": "string"},
        "content": {"type": "string", "description": "The whole new text, in markdown."}, "tags": _TAGS,
        "project": {**_PROJECT, "description": "The project to move it to; '' takes it out of its project."},
    }, "required": ["note"]},
)
DELETE_NOTE_SPEC = ToolSpec(
    name="delete_note",
    description="Delete a note. Name the note exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"note": _NOTE_REF}, "required": ["note"]},
)

NOTE_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_NOTE_SPEC, "write_create"),
    ToolDef(FIND_NOTES_SPEC, "read"),
    ToolDef(READ_NOTE_SPEC, "read"),
    ToolDef(APPEND_TO_NOTE_SPEC, "write_change"),
    ToolDef(UPDATE_NOTE_SPEC, "write_change"),
    ToolDef(DELETE_NOTE_SPEC, "write_change"),
)
