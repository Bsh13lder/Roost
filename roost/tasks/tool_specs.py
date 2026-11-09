"""The tasks tool specs and gate kinds (M1 D3, D6; projects hub H11)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.records.paging import OFFSET_PROPERTY
from roost.tags.rules import TOPIC_TAGS_SCHEMA
from roost.talk.tool_def import ToolDef
from roost.tasks.models import PRIORITIES

_TASK_REF = {"type": "string", "description": "The task's id, or its title (or a unique part of it)."}
_DUE = {"type": "string", "description": "When it is due, as the user said it: 'tomorrow at 9', 'next Monday', "
                                         "'2026-10-20' or an ISO date and time (local time). '' clears it."}
_PROJECT = {"type": "string", "description": ("One of the user's projects, by name or id. Name it exactly; make "
                                              "a new one with create_project.")}
_BUDGET = {"type": ["number", "string"], "description": "The task's budget slice in its project's currency, e.g. "
                                                        "300 (needs a project)."}

ADD_TASK_SPEC = ToolSpec(
    name="add_task",
    description=("Add a task to the user's task list (the user's own list; every bot uses it). A due time is "
                 "also the reminder; advance reminders default to 30 minutes before. "
                 "Pass dates as the user said them, like \"tomorrow at 9\"."),
    input_schema={"type": "object", "properties": {
        "title": {"type": "string", "description": "Short title, e.g. 'Call the dentist'."},
        "description": {"type": "string", "description": "Optional notes."},
        "category": {"type": "string", "description": "Optional list, e.g. 'Home'."},
        "priority": {"type": "string", "enum": list(PRIORITIES)},
        "due_date": _DUE,
        "reminder_at": {"type": "string", "description": "Optional reminder time if not the due time, e.g. 'tomorrow 8:00'."},
        "pre_reminders": {"type": "array", "items": {"type": "string"},
                          "description": "Advance reminders as offsets like '-30m' or '-2h'; [] for none."},
        "recurring": {"type": "string", "description": "Optional cron for a repeating task, e.g. '0 9 * * 1' (Mondays 09:00)."},
        "recur_until": {"type": "string", "description": "Optional last day of a repeating task, YYYY-MM-DD."},
        "steps": {"type": "array", "items": {"type": "string"}, "description": "Optional checklist items."},
        "tags": TOPIC_TAGS_SCHEMA,
        "project": _PROJECT, "budget": _BUDGET,
    }, "required": ["title"]},
)
LIST_TASKS_SPEC = ToolSpec(
    name="list_tasks",
    description=("List the user's tasks: open ones by default, by priority then due date. A long list ends "
                 "with how to get the rest."),
    input_schema={"type": "object", "properties": {
        "status": {"type": "string", "enum": ["open", "done", "failed", "all"]},
        "category": {"type": "string", "description": "Only this list."},
        "project": {"type": "string", "description": "Only this project's tasks, by name or id."},
        "offset": dict(OFFSET_PROPERTY),
    }},
)
UPDATE_TASK_SPEC = ToolSpec(
    name="update_task",
    description=("Change an open task's title, notes, list, project, budget, priority, status, due date or "
                 "reminder; status failed closes it as failed (a repeating task comes back). "
                 "Name the task exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "task": _TASK_REF, "title": {"type": "string"}, "description": {"type": "string"},
        "category": {"type": "string"}, "priority": {"type": "string", "enum": list(PRIORITIES)},
        "status": {"type": "string", "enum": ["todo", "in_progress", "cancelled", "failed"]}, "due_date": _DUE,
        "reminder_at": {"type": "string", "description": "When to remind the user (their phone shows it), e.g. "
                        "'tomorrow 8:50'; '' clears the reminder."},
        "pre_reminders": {"type": "array", "items": {"type": "string"},
                          "description": "With reminder_at: advance reminders like '-1h'; [] for only the "
                                         "reminder itself."},
        "project": {**_PROJECT, "description": _PROJECT["description"] + " '' takes it out of its project."},
        "budget": {**_BUDGET, "description": _BUDGET["description"] + " '' clears it."},
    }, "required": ["task"]},
)
COMPLETE_TASK_SPEC = ToolSpec(
    name="complete_task",
    description="Mark an open task done. A repeating task comes back for its next time. "
                "Name the task exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"task": _TASK_REF}, "required": ["task"]},
)
DELETE_TASK_SPEC = ToolSpec(
    name="delete_task",
    description="Delete an open task. Name the task exactly; if two match, ask the user which.",
    input_schema={"type": "object", "properties": {"task": _TASK_REF}, "required": ["task"]},
)

TASK_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(ADD_TASK_SPEC, "write_create"),
    ToolDef(LIST_TASKS_SPEC, "read"),
    ToolDef(UPDATE_TASK_SPEC, "write_change"),
    ToolDef(COMPLETE_TASK_SPEC, "write_change"),
    ToolDef(DELETE_TASK_SPEC, "write_change"),
)
