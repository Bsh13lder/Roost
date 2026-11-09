"""The money tool specs and gate kinds (M1 D3, D7; projects hub H1, H3, H5–H7, H11)."""

from __future__ import annotations

from roost.llm.types import ToolSpec
from roost.records.paging import OFFSET_PROPERTY
from roost.tags.rules import TOPIC_TAGS_SCHEMA
from roost.talk.tool_def import ToolDef

_AMOUNT = {"type": ["number", "string"], "description": "The amount, e.g. 12.50 or '12,50'."}
_NEW_OR_KNOWN_PROJECT = {"type": "string", "description": (
    "Project, by name (e.g. 'food') or id; a new name makes a new project. Omit for the task's project, "
    "or General.")}
_PROJECT = {"type": "string", "description": "The project's name or id. Name it exactly."}
_MONTH = {"type": "string", "description": "A month like 2026-10. Default: this month (local time)."}
_EXPENSE = {"type": "string", "description": "The expense's id, from list_expenses."}
_TASK = {"type": "string", "description": "The task it was spent on: its id or title (open or closed)."}
_STEP = {"type": "string", "description": "One of that task's steps: its title or id."}
_STARRED = {"type": "boolean", "description": "Star it; a project shows its starred total."}

LOG_EXPENSE_SPEC = ToolSpec(
    name="log_expense",
    description=("Log money the user spent, in a project (General when none is named). Amounts are in the "
                 "project's currency unless a currency is given. Log an expense as soon as the user mentions one. "
                 "Never invent amounts; you cannot buy or pay anything."),
    input_schema={"type": "object", "properties": {
        "amount": _AMOUNT, "project": _NEW_OR_KNOWN_PROJECT,
        "note": {"type": "string", "description": "What it was for, e.g. 'lunch'."},
        "vendor": {"type": "string", "description": "Optional shop or payee."},
        "currency": {"type": "string", "description": "Three-letter code. Default: the project's currency."},
        "spent_at": {"type": "string", "description": "The day: 'yesterday', '2026-10-12'. Default: today."},
        "task": _TASK, "step": _STEP, "starred": _STARRED, "tags": TOPIC_TAGS_SCHEMA,
        "income": {"type": "boolean", "description": (
            "True for money the user RECEIVED (salary, a refund): logged as money in, never as spending.")},
    }, "required": ["amount"]},
)
LIST_EXPENSES_SPEC = ToolSpec(
    name="list_expenses",
    description=("List the user's expenses for a month, newest first, with their ids; void ones are marked. A "
                 "long list ends with how to get the rest."),
    input_schema={"type": "object", "properties": {
        "month": _MONTH, "project": {**_PROJECT, "description": "Only this project's: its name or id."},
        "offset": dict(OFFSET_PROPERTY),
    }},
)
MONEY_SUMMARY_SPEC = ToolSpec(
    name="money_summary",
    description="Totals for a month: overall and by project, each in its own currency and against its monthly limit.",
    input_schema={"type": "object", "properties": {"month": _MONTH}},
)
UPDATE_EXPENSE_SPEC = ToolSpec(
    name="update_expense",
    description=("Correct an expense: its amount, project, note, day, task or step; star it; or void it (a void "
                 "expense stays listed but counts nowhere)."),
    input_schema={"type": "object", "properties": {
        "expense": _EXPENSE, "amount": _AMOUNT,
        "project": {**_PROJECT, "description": "The project to move it to: its name or id, exactly."},
        "note": {"type": "string"}, "spent_at": {"type": "string"},
        "task": {**_TASK, "description": _TASK["description"] + " '' unlinks it from its task."},
        "step": {**_STEP, "description": _STEP["description"] + " '' unlinks the step."},
        "starred": {"type": "boolean"},
        "void": {"type": "boolean", "description": "true voids it; false counts it again."},
    }, "required": ["expense"]},
)
DELETE_EXPENSE_SPEC = ToolSpec(
    name="delete_expense",
    description="Delete an expense.",
    input_schema={"type": "object", "properties": {"expense": _EXPENSE}, "required": ["expense"]},
)
SET_BUDGET_SPEC = ToolSpec(
    name="set_budget",
    description=("Set a project's total budget (top-ups included). Name the project exactly; a new project needs "
                 "create_project. An amount of '' clears the budget."),
    input_schema={"type": "object", "properties": {
        "project": _PROJECT, "amount": {**_AMOUNT, "description": "The total budget, e.g. 500; '' clears it."},
    }, "required": ["project", "amount"]},
)

MONEY_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LOG_EXPENSE_SPEC, "write_create"),
    ToolDef(LIST_EXPENSES_SPEC, "read"),
    ToolDef(MONEY_SUMMARY_SPEC, "read"),
    ToolDef(UPDATE_EXPENSE_SPEC, "write_change"),
    ToolDef(DELETE_EXPENSE_SPEC, "write_change"),
    ToolDef(SET_BUDGET_SPEC, "write_change"),
)
