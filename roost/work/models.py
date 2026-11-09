"""Work queue domain model (spec §4.2 "Work queue", §11 step 5) — frozen
dataclasses only. A ``WorkItem`` is one durable unit a bot must handle:
your message, another bot's handoff, a room post, or a continue item after
you clear a Stuck card (trigger is reserved for a later step), or a routine's scheduled run
(its origin is ``routine_origin``; the routine's instructions are a ``routine`` message in its run-log thread)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from roost.bots.models import Bot


class WorkKind(str, Enum):
    MESSAGE = "message"
    ROUTINE = "routine"
    TRIGGER = "trigger"
    HANDOFF = "handoff"
    CARD_ANSWER = "card_answer"
    ROOM_POST = "room_post"


class WorkState(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    DONE = "done"
    DROPPED = "dropped"


# Origin labels: where a run came from, quoted in its instructions (§6.1).
ORIGIN_YOU = "you, in your chat"
# Stuck flow R6: the continue item queued when you clear a Stuck card (Give it back / Try again).
ORIGIN_CARD = "you, after a Stuck card"


def handoff_origin(asker_name: str) -> str:
    return f"from {asker_name}"


def room_origin(room_name: str) -> str:
    return f"room {room_name}"


def routine_origin(routine_name: str) -> str:
    return f"routine {routine_name}"


RunOutcome = Literal["done", "stopped", "step_cap", "time_cap", "error", "interrupted"]


def _first_per_run(items: tuple["WorkItem", ...]) -> tuple["WorkItem", ...]:
    """Keep only the first item of each run (by ``run_id``, in order).
    ``WorkQueue.set_inflight`` writes the SAME note to every item of a
    claimed batch, so without this an interrupted run of N items would
    surface -- in a report, a notice, or an API count -- N times instead
    of once. Shared by ``DropReport.interrupted`` (Stop) and
    ``WorkQueue.recover_on_boot`` (boot recovery; fix round 1, finding 2)."""
    seen: set[str] = set()
    kept: list["WorkItem"] = []
    for item in items:
        if item.run_id not in seen:
            seen.add(item.run_id)
            kept.append(item)
    return tuple(kept)


@dataclass(frozen=True)
class WorkDraft:
    bot_id: str
    thread_id: str
    kind: WorkKind
    origin: str
    body: str
    tainted: bool = False
    depth: int = 0
    parent_item_id: str | None = None
    message_id: str | None = None
    link_scope: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkItem:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    kind: WorkKind
    origin: str
    body: str
    tainted: bool
    depth: int
    parent_item_id: str | None
    message_id: str | None
    state: WorkState
    run_id: str | None
    inflight: str | None
    result: str | None
    result_tainted: bool
    created_at: str
    updated_at: str
    link_scope: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimedBatch:
    """Items in a row for one thread, claimed together for one turn."""

    run_id: str
    bot: Bot
    thread_id: str
    items: tuple[WorkItem, ...]


@dataclass(frozen=True)
class DropReport:
    """What a Stop (or a stop cascade) dropped, each item with the state it had just before, and (steer
    design) what the stopped run did, as the chat's step lines read ("Added a task")."""

    dropped: tuple[WorkItem, ...] = ()
    done: tuple[str, ...] = ()

    @property
    def waiting(self) -> tuple[WorkItem, ...]:
        return tuple(i for i in self.dropped if i.state is WorkState.QUEUED)

    @property
    def running(self) -> tuple[WorkItem, ...]:
        return tuple(i for i in self.dropped if i.state is WorkState.CLAIMED)

    @property
    def interrupted(self) -> tuple[WorkItem, ...]:
        """Fix round 1, finding 1: dedupe by run_id -- a Stop landing on a
        multi-item batch must not report (or notice) the one mid-flight
        call once per item in that batch."""
        return _first_per_run(tuple(i for i in self.running if i.inflight))

    @property
    def run_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(i.run_id for i in self.running if i.run_id))


@dataclass(frozen=True)
class RecoveryReport:
    """Boot recovery: handoffs whose asker died with the old process, and
    re-queued items that had a call in flight."""

    dropped_handoffs: tuple[WorkItem, ...] = ()
    interrupted: tuple[WorkItem, ...] = ()


HandoffStatus = Literal["done", "failed", "dropped", "timeout", "refused"]  # refused: the target waits on the asker


@dataclass(frozen=True)
class HandoffResult:
    """What an asking run gets back from ``TurnRunner.hand_off``."""

    status: HandoffStatus
    text: str = ""
    tainted: bool = False
    link_scope: tuple[str, ...] = ()
