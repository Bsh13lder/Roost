"""The step and comment tool specs and their gate kinds (redesign P3).

Adding a step or a comment creates (``write_create``: a tainted run may, up to
the cap); renaming, ticking, moving or deleting a step changes the user's
task (``write_change``: never from a tainted run); reading comments is
``read``."""

from __future__ import annotations

from roost.constants import MAX_TASK_STEPS
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_TASK = {"type": "string", "description": "The task's id, or its title (or a unique part of it)."}
_STEP = {"type": "string", "description": "The step's id, or its title (or a unique part of it)."}

ADD_STEP_SPEC = ToolSpec(
    name="add_step",
    description="Add a step (a subtask) to the end of one of the user's tasks.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "title": {"type": "string", "description": "The step, e.g. 'Buy a washer'."},
    }, "required": ["task", "title"]},
)
UPDATE_STEP_SPEC = ToolSpec(
    name="update_step",
    description="Rename a task's step, or tick it (done true) or untick it (done false). Name the step exactly.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": _STEP, "title": {"type": "string", "description": "Its new title."},
        "done": {"type": "boolean"},
    }, "required": ["task", "step"]},
)
DELETE_STEP_SPEC = ToolSpec(
    name="delete_step",
    description="Delete a task's step. Money and comments filed under it stay on the task. Name the step exactly.",
    input_schema={"type": "object", "properties": {"task": _TASK, "step": _STEP}, "required": ["task", "step"]},
)
MOVE_STEP_SPEC = ToolSpec(
    name="move_step",
    description="Move a task's step to another place in its list; 1 is the first place.",
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": _STEP,
        "position": {"type": "integer", "minimum": 1, "maximum": MAX_TASK_STEPS, "description": "Its new place."},
    }, "required": ["task", "step", "position"]},
)
ADD_COMMENT_SPEC = ToolSpec(
    name="add_comment",
    description=("Add a comment to one of the user's tasks, or to one of its steps: what you did, found or need. "
                 "The user reads it in the task."),
    input_schema={"type": "object", "properties": {
        "task": _TASK, "step": {**_STEP, "description": "Optional: the step it is about."},
        "text": {"type": "string", "description": "The comment."},
    }, "required": ["task", "text"]},
)
LIST_COMMENTS_SPEC = ToolSpec(
    name="list_comments",
    description="Read a task's comments, oldest first (the newest ones when there are many).",
    input_schema={"type": "object", "properties": {"task": _TASK}, "required": ["task"]},
)

STEP_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_STEP_SPEC, "write_create"),
    ToolDef(UPDATE_STEP_SPEC, "write_change"),
    ToolDef(DELETE_STEP_SPEC, "write_change"),
    ToolDef(MOVE_STEP_SPEC, "write_change"),
)
COMMENT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_COMMENT_SPEC, "write_create"),
    ToolDef(LIST_COMMENTS_SPEC, "read"),
)
