"""Task domain model (M1 D6) — frozen dataclasses. Names and meanings follow
LazyClaw's tasks table so M4 can import the user's tasks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal, Mapping

Priority = Literal["low", "medium", "high", "urgent"]
PRIORITIES: tuple[Priority, ...] = ("low", "medium", "high", "urgent")
# "failed" (projects hub, H11) closes a task the way "done" does: it sets
# completed_at, and a recurring task comes back. The "done" filter leaves it out.
TaskStatus = Literal["todo", "in_progress", "done", "cancelled", "failed"]
TaskFilter = Literal["open", "done", "failed", "all"]


STEP_NOT_FOUND_TEXT = "That task has no such step."


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    done: bool
    created_at: str | None = None
    completed_at: str | None = None
    cascaded: bool = False
    budget: Decimal | None = None          # its own budget (owner, 2026-10-26), in ``budget_currency``
    budget_currency: str | None = None     # the task's currency when it was set; another one reads as none


@dataclass(frozen=True)
class Task:
    id: str
    user_id: str
    title: str
    description: str | None
    category: str | None          # the task's list, LazyClaw's "category"
    priority: Priority
    status: TaskStatus
    owner: str
    due_date: str | None
    reminder_at: str | None
    pre_reminders: tuple[str, ...]
    recurring: str | None         # cron, the install's zone
    recur_until: str | None
    tags: tuple[str, ...]
    steps: tuple[Step, ...]
    created_at: str
    updated_at: str
    completed_at: str | None
    created_by_bot: str | None    # NULL: the user, or a retired bot
    tainted: bool                 # written by a run that read outside content
    project_id: str | None = None               # one of the user's projects (money_projects.id)
    allocated_budget: Decimal | None = None     # its budget slice, in that project's currency
    starred: bool = False
    estimate_minutes: int | None = None         # sealed in the database (AAD tasks:estimate)
    imported_from: str | None = None            # "lazyclaw" for a row an import made (import_links); read-only


@dataclass(frozen=True)
class TaskDraft:
    """A new task with its schedule already resolved (see ``due.build_schedule``)."""

    title: str
    description: str | None = None
    category: str | None = None
    priority: Priority = "medium"
    owner: str = "user"
    due_date: str | None = None
    reminder_at: str | None = None
    pre_reminders: tuple[str, ...] = ()
    recurring: str | None = None
    recur_until: str | None = None
    tags: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()   # checklist titles
    project_id: str | None = None
    allocated_budget: Decimal | None = None   # needs project_id (H11)
    starred: bool = False
    estimate_minutes: int | None = None


@dataclass(frozen=True)
class DueSet:
    """A task's whole schedule: what a bulk move writes and what its Undo writes back."""

    id: str
    due_date: str | None
    reminder_at: str | None
    pre_reminders: tuple[str, ...] = ()


PATCHABLE_FIELDS = frozenset({
    "title", "description", "category", "priority", "status", "due_date", "reminder_at", "pre_reminders",
    "recurring", "recur_until", "tags", "project_id", "allocated_budget", "starred", "estimate_minutes",
})

# These columns are NOT NULL in the database; clearing them would either
# violate that constraint (priority, status) or leave the task unnamed
# (title). ``patch_from_fields`` already turns a cleared title into a plain
# refusal before it reaches here; this guard is the one gate every caller —
# including a direct ``TaskPatch({...})`` from the store's other callers —
# goes through.
_NOT_NULLABLE = frozenset({"title", "priority", "status", "starred"})


@dataclass(frozen=True)
class TaskPatch:
    """Only the fields to change; ``None`` clears one, except ``title``,
    ``priority`` and ``status``, which can never be cleared."""

    changes: Mapping[str, Any]

    def __post_init__(self) -> None:
        unknown = sorted(set(self.changes) - PATCHABLE_FIELDS)
        if unknown:
            raise ValueError(f"Tasks have no field {', '.join(unknown)}.")
        nulled = sorted(name for name in _NOT_NULLABLE if self.changes.get(name, "kept") is None)
        if nulled:
            # No contraction/possessive here: this message passes through
            # html.escape(quote=True) on the tools path, which would turn an
            # apostrophe into "&#x27;" for the model to read.
            raise ValueError(f"The {', '.join(nulled)} of a task cannot be cleared.")
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))
