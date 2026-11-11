"""Routine value objects: frozen dataclasses for rows, pydantic models for what crosses a boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import (
    MAX_TASK_TITLE_LENGTH,
    REMINDER_ANSWERS,
    REMINDER_DUE_MAX,
    REPORT_HEADLINE_MAX,
    REPORT_TEXT_MAX_CHARS,
    ROUTINE_INSTRUCTIONS_MAX,
    ROUTINE_NAME_MAX,
)
from roost.routines.schedule import Schedule
from roost.routines.watch_models import Watch, WatchIn
from roost.standing.models import PermissionIn

Clock = Callable[[], datetime]
RunState = Literal["queued", "running", "done", "missed", "skipped", "held", "expired", "error"]
CreatedBy = Literal["user", "bot"]
ProposalAction = Literal["create", "change", "pause"]
ProposalState = Literal["open", "approved", "declined", "expired"]
ReminderAnswer = Literal[*REMINDER_ANSWERS]
ReportSource = Literal["routine", "reminder", "day_summary", "budget", "system"]
BuiltinRoutine = Literal["day_summary"]

# States a run can be closed in; ``finished_at`` is set when it enters one of them.
FINISHED_STATES: frozenset[str] = frozenset({"done", "missed", "skipped", "held", "expired", "error"})
OPEN_STATES: tuple[str, ...] = ("queued", "running")


@dataclass(frozen=True)
class Routine:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    name: str
    instructions: str
    schedule: Schedule
    builtin: str | None
    enabled: bool
    tainted: bool
    created_by: CreatedBy
    next_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    watch: Watch | None = None      # "Only run when the page changes": checked every few minutes, no model
    model: str | None = None        # its own model (owner, 2026-11-09); None: the bot's
    model_failures: int = 0         # runs that failed in a row on that model; 2 falls back to the bot's
    last_error_kind: str | None = None   # v47: a ROUTINE_ERROR_* word, cleared by the next good check or finished run
    last_error_at: datetime | None = None
    finished_at: datetime | None = None     # v48: the bot finished it in its own run; deleted keep-days later
    finished_reason: str | None = None      # its short reason (sealed); None with finished_at None


@dataclass(frozen=True)
class RoutineDraft:
    bot_id: str
    name: str
    instructions: str
    schedule: Schedule
    created_by: CreatedBy
    tainted: bool = False
    builtin: str | None = None
    enabled: bool = True
    watch: Watch | None = None
    model: str | None = None


@dataclass(frozen=True)
class RoutinePatch:
    """The fields to change: any of ``name``, ``instructions``, ``schedule``, ``tainted``, ``watch`` (a ``Watch``,
    or None for no watch) and ``model`` (a model id, or None for the bot's; a change starts its failure count over)."""
    changes: Mapping


@dataclass(frozen=True)
class RoutineRun:
    id: str
    user_id: str
    routine_id: str
    bot_id: str
    slot_at: datetime
    work_item_id: str | None
    state: RunState
    missed_count: int
    note: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=ROUTINE_NAME_MAX)
    instructions: str = Field(max_length=ROUTINE_INSTRUCTIONS_MAX)
    schedule: Schedule
    permission: PermissionIn | None = None   # a standing permission the bot asks for; stored only on Approve
    watch: WatchIn | None = None             # "Only run when the page changes", checked by parse_watch; None: none


@dataclass(frozen=True)
class Proposal:
    id: str
    user_id: str
    bot_id: str
    routine_id: str | None
    action: ProposalAction
    payload: ProposalPayload | None
    tainted: bool
    from_routine: bool
    state: ProposalState
    thread_id: str
    message_id: str | None
    created_at: datetime
    decided_at: datetime | None


class ReportBody(BaseModel):
    """The JSON body of a ``report`` message."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: ReportSource
    headline: str = Field(min_length=1, max_length=REPORT_HEADLINE_MAX)
    text: str = Field(max_length=REPORT_TEXT_MAX_CHARS)
    routine_id: str | None = None
    run_id: str | None = None
    log_thread_id: str | None = None
    routine_name: str | None = Field(default=None, max_length=ROUTINE_NAME_MAX)   # the chat's quiet footer
    tainted: bool = False
    bot_id: str | None = None       # the bot it is from: set by ``post_report``; an older body has none
    task_id: str | None = None      # a task reminder's task, for the card's Done · Failed · Reschedule · Skip
    task_title: str | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)   # its title, for the model
    answer: ReminderAnswer | None = None    # the card's answer, kept so every screen shows it (reminder_answers.py)
    answer_due: str | None = Field(default=None, max_length=REMINDER_DUE_MAX)   # a Reschedule's new due; None: no date
    answered_at: str | None = None


@dataclass(frozen=True)
class AnswerLine:
    """One of a routine's earlier questions with the user's answer, for its next run's instructions (quoted data)."""
    text: str
    tainted: bool = False


@dataclass(frozen=True)
class RoutineSection:
    """A routine run's "nobody is watching" section, and whether what it quotes carries outside content."""
    text: str
    tainted: bool = False
    model: str | None = None   # the routine's own model, when it has one


class Job(Protocol):
    """A scheduler job that posts Reports with no model run (``system_reports.py``).

    ``run`` is called for every user on every tick; ``builtin`` names the built-in routine the job fires (or is
    ``None``), and ``fire`` posts that routine's Report for one slot."""

    name: str
    builtin: str | None

    async def run(self, user_id: str, now: datetime) -> None: ...

    async def fire(self, user_id: str, routine: Routine, slot: datetime) -> None: ...
