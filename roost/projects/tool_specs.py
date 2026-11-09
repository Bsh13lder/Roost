"""The project tool specs and gate kinds (projects hub, design §3 with H3, H4,
H15, H16). ``roost.talk.tool_catalog`` imports this module, so it imports only
``roost.constants``, ``roost.llm.types`` and ``roost.talk.tool_def``.

- Deleting a project is not a tool (design §3): only the Board does it, after
  a confirmation.
- ``add_topup`` is a ``write_change`` (H4): it raises an existing project's
  budget, so a run that read a web page may not do it.
- ``set_budget`` stays a money tool (``roost.money.tool_specs``)."""

from __future__ import annotations

from roost.constants import PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_PROJECT_REF = {"type": "string",
                "description": "The project's name or id. Name it exactly; if two match, ask the user which."}
_AMOUNT = {"type": ["number", "string"], "description": "An amount, e.g. 250 or '250,50'."}
_COLOR = {"type": "string", "enum": list(PROJECT_COLORS)}
_START = {"type": "string", "description": "The day it starts, like 2026-10-01."}
_DUE = {"type": "string", "description": "The day it is due, like 2026-12-31."}
_LEAD = {"type": "string", "description": "The name of the bot that leads it (one of the user's bots)."}
_TOPUP = {"type": "string", "description": "The top-up's id, from get_project."}
_CLEARS = " '' clears it."

LIST_PROJECTS_SPEC = ToolSpec(
    name="list_projects",
    description=("List the user's projects (every bot uses them): for each, its total budget and this month's "
                 "limit with what is spent and left, spending in other currencies apart, and how many tasks are "
                 "done. Archived projects only when asked."),
    input_schema={"type": "object", "properties": {
        "include_archived": {"type": "boolean", "description": "Also list archived projects."},
    }},
)
GET_PROJECT_SPEC = ToolSpec(
    name="get_project",
    description=("Show one project in full: its budgets, lead bot and dates, its tasks, latest expenses, notes "
                 "and documents, and its top-up history with ids."),
    input_schema={"type": "object", "properties": {"project": _PROJECT_REF}, "required": ["project"]},
)
CREATE_PROJECT_SPEC = ToolSpec(
    name="create_project",
    description=("Create a project that holds tasks, money, notes and documents. It may have a total budget, a "
                 "monthly limit, or both, counted in its own currency. Create one when the user asks for it."),
    input_schema={"type": "object", "properties": {
        "name": {"type": "string", "description": "Short name, e.g. 'Renovation'."},
        "currency": {"type": "string", "description": "Three-letter code, default EUR. Budgets count only "
                                                      "spending in it."},
        "budget": {**_AMOUNT, "description": "The total budget, e.g. 500."},
        "monthly_budget": {**_AMOUNT, "description": "The monthly limit, e.g. 100."},
        "color": _COLOR, "start_date": _START, "due_date": _DUE, "lead_bot": _LEAD,
    }, "required": ["name"]},
)
UPDATE_PROJECT_SPEC = ToolSpec(
    name="update_project",
    description=("Change a project: rename it, set its colour, dates, lead bot or monthly limit, archive or "
                 "unarchive it, or change its currency while it has no expenses and no top-ups. The total budget "
                 "changes with set_budget or add_topup. Name the project exactly; if two match, ask the user which."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT_REF, "name": {"type": "string", "description": "Its new name."}, "color": _COLOR,
        "start_date": {**_START, "description": _START["description"] + _CLEARS},
        "due_date": {**_DUE, "description": _DUE["description"] + _CLEARS},
        "lead_bot": {**_LEAD, "description": _LEAD["description"] + _CLEARS},
        "monthly_budget": {**_AMOUNT, "description": "The monthly limit." + _CLEARS},
        "archived": {"type": "boolean", "description": "true archives it; false brings it back."},
        "currency": {"type": "string", "description": "Three-letter code."},
    }, "required": ["project"]},
)
ADD_TOPUP_SPEC = ToolSpec(
    name="add_topup",
    description=("Add money to a project's total budget, such as a gift or a transfer. It shows in the project's "
                 "top-up history and can be changed or undone."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT_REF, "amount": _AMOUNT,
        "source": {"type": "string", "description": f"Where it came from, e.g. 'birthday' (up to "
                                                    f"{TOPUP_SOURCE_MAX_CHARS} characters)."},
    }, "required": ["project", "amount"]},
)
EDIT_TOPUP_SPEC = ToolSpec(
    name="edit_topup",
    description="Change a top-up's amount; the total budget moves by the difference.",
    input_schema={"type": "object", "properties": {
        "topup": _TOPUP, "amount": {**_AMOUNT, "description": "The top-up's new amount."},
    }, "required": ["topup", "amount"]},
)
UNDO_TOPUP_SPEC = ToolSpec(
    name="undo_topup",
    description="Undo a top-up: it and its changes leave the total budget, and the history keeps it, marked undone.",
    input_schema={"type": "object", "properties": {"topup": _TOPUP}, "required": ["topup"]},
)

PROJECT_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_PROJECTS_SPEC, "read"),
    ToolDef(GET_PROJECT_SPEC, "read"),
    ToolDef(CREATE_PROJECT_SPEC, "write_create"),
    ToolDef(UPDATE_PROJECT_SPEC, "write_change"),
    ToolDef(ADD_TOPUP_SPEC, "write_change"),
    ToolDef(EDIT_TOPUP_SPEC, "write_change"),
    ToolDef(UNDO_TOPUP_SPEC, "write_change"),
)
