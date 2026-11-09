"""Frozen shapes for the LazyClaw importer: what is read, what is mapped, what is noted."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

Row = Mapping[str, object]


@dataclass(frozen=True)
class LazyData:
    """One LazyClaw user's rows, already decrypted (text fields are plain strings)."""

    tasks: tuple[Row, ...] = ()
    projects: tuple[Row, ...] = ()
    expenses: tuple[Row, ...] = ()
    topups: tuple[Row, ...] = ()
    recurring: tuple[Row, ...] = ()
    settings_timezone: str | None = None


@dataclass(frozen=True)
class RoostContext:
    """What the mapping needs to know about the target account."""

    user_id: str
    import_day: date
    imported_at: str                      # ISO UTC, stamped on paused rules
    general_project_id: str | None = None  # Roost's existing General (H2); None: not known yet
    main_bot_id: str | None = None         # author of LazyClaw 'agent' comments
    general_currency: str = "EUR"          # Roost's General project currency


@dataclass(frozen=True)
class Anomaly:
    """Something to show the user. ``ref`` is an id, never user text."""

    kind: str
    ref: str
    detail: str
    blocking: bool = False


@dataclass(frozen=True)
class ImportedProject:
    id: str                    # LazyClaw id
    target_id: str             # Roost id (the same, except General which maps to Roost's)
    name: str
    description: str | None
    budget: Decimal | None
    currency: str
    status: str
    start_date: str | None
    due_date: str | None
    color: str
    created_at: str
    updated_at: str
    is_general: bool = False


@dataclass(frozen=True)
class ImportedTask:
    id: str
    title: str
    description: str | None
    project_id: str | None     # Roost project id
    category: str | None       # the list, when no project matched
    priority: str
    status: str
    owner: str
    due_date: str | None
    reminder_at: str | None
    pre_reminders: str | None
    recurring: str | None
    recur_until: str | None
    tags: str | None
    steps: tuple[Mapping[str, object], ...]
    allocated_budget: Decimal | None
    created_at: str
    updated_at: str
    completed_at: str | None
    tainted: int = 0
    starred: int = 0
    estimate: None = None
    created_by_bot: None = None


@dataclass(frozen=True)
class ImportedComment:
    id: str
    task_id: str
    step_id: str | None
    author: str                # 'user', or the main bot's id
    body: str
    created_at: str
    tainted: int = 0


@dataclass(frozen=True)
class ImportedTopup:
    id: str
    project_id: str
    amount: Decimal            # signed
    currency: str
    source: str | None
    kind: str
    created_at: str
    updated_at: str
    deleted_at: str | None
    opening: bool = False      # the synthetic "Opening budget" row (H4)
    tainted: int = 0


@dataclass(frozen=True)
class ImportedExpense:
    id: str
    project_id: str
    task_id: str | None
    step_id: str | None
    amount: Decimal
    currency: str
    description: str | None
    vendor: str | None
    notes: str | None
    spent_at: str
    status: str
    is_favorite: int
    recurring_id: str | None
    occurrence: str | None
    created_at: str
    updated_at: str
    tainted: int = 0


@dataclass(frozen=True)
class ImportedRecurring:
    id: str
    project_id: str
    amount: Decimal
    currency: str
    description: str | None
    vendor: str | None
    cadence: str
    anchor_day: str
    next_due: str
    created_at: str
    updated_at: str
    deleted_at: str | None
    tainted: int = 0


@dataclass(frozen=True)
class Mapped:
    """Everything the importer would write, plus what it skipped, lost or flagged."""

    projects: tuple[ImportedProject, ...] = ()
    tasks: tuple[ImportedTask, ...] = ()
    comments: tuple[ImportedComment, ...] = ()
    topups: tuple[ImportedTopup, ...] = ()
    expenses: tuple[ImportedExpense, ...] = ()
    recurring: tuple[ImportedRecurring, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()
    skipped: Mapping[str, int] = field(default_factory=dict)
    lost: Mapping[str, int] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(a.blocking for a in self.anomalies)
