"""Steer (docs/plans/2026-10-22-roost-steer.md): one running run's handle for the messages you send while it works,
and for Stop.

``TurnRunner`` makes one ``RunSteer`` per claimed batch and keeps it while the run lives. The step loop asks it at
each boundary (never in the middle of a tool call): ``take()`` claims your new messages for this thread under the
run's own id, so a message is a durable work item that this run consumes and nobody answers twice. While the run
has done nothing yet (no write or act call completed) the loop restarts instead (``RunRestart``); after Stop it
ends (``RunStopped``). ``ToolRunner`` reports every completed call through ``note_done``: the Stopped line lists
the writes, and any side effect rules a restart out.
"""

from __future__ import annotations

import asyncio
from types import MappingProxyType
from typing import Awaitable, Callable, Mapping

from roost.constants import STEER_MAX_RESTARTS, STEER_TURN_PREFIX
from roost.llm.types import ChatTurn
from roost.work.models import WorkItem

TakeMessages = Callable[[], Awaitable[tuple[WorkItem, ...]]]

# The past tense of every verb the gateway announces; the same table as ``PAST`` in web/src/lib/toolLines.ts
# (tests/test_steer_unit.py keeps the two equal).
PAST: Mapping[str, str] = MappingProxyType({
    "adding": "added", "asking": "asked", "changing": "changed", "checking": "checked", "completing": "completed",
    "correcting": "corrected", "creating": "created", "deleting": "deleted", "editing": "edited", "filing": "filed",
    "forgetting": "forgot", "logging": "logged", "looking": "looked", "making": "made", "moving": "moved",
    "opening": "opened", "reading": "read", "renaming": "renamed", "saving": "saved", "searching": "searched",
    "sending": "sent", "setting": "set", "switching": "switched", "undoing": "undid", "updating": "updated",
    "waiting": "waited", "writing": "wrote",
})


def past_line(activity: str) -> str:
    """"adding a task" -> "Added a task"; an activity with an unknown verb is only capitalised."""
    words = activity.strip().split(" ")
    past = PAST.get(words[0].lower())
    text = " ".join([past, *words[1:]]) if past else " ".join(words)
    return text[:1].upper() + text[1:]


def _name_line(name: str) -> str:
    text = name.replace("_", " ")
    return text[:1].upper() + text[1:]


def steer_turn(item: WorkItem) -> ChatTurn:
    """Your message as the model sees it mid-run: a user turn, marked as sent while it worked."""
    return ChatTurn("user", STEER_TURN_PREFIX + item.body)


class RunRestart(Exception):
    """The run did nothing yet and new messages came: run again, the same run id, with ``items`` added."""

    def __init__(self, items: tuple[WorkItem, ...]) -> None:
        super().__init__("restart with new messages")
        self.items = items


class RunStopped(Exception):
    """You pressed Stop: the run ends at this boundary and keeps what it said."""


class RunSteer:
    """One run's steer handle. ``steerable`` is False for routine runs, handoffs and room posts: they take
    nothing and a message for them waits in the queue."""

    def __init__(self, *, take: TakeMessages | None, steerable: bool, max_restarts: int = STEER_MAX_RESTARTS) -> None:
        self._take = take
        self.steerable = steerable and take is not None
        self._max_restarts = max_restarts
        self._restarts = 0
        self._stop = asyncio.Event()
        self._side_effects = False
        self._done: tuple[str, ...] = ()
        self._taken: tuple[WorkItem, ...] = ()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    @property
    def taken(self) -> tuple[WorkItem, ...]:
        """Every message this run took mid-work, oldest first."""
        return self._taken

    @property
    def done_lines(self) -> tuple[str, ...]:
        """What the run did, as the chat's step lines read once done ("Added a task")."""
        return self._done

    def request_stop(self) -> None:
        self._stop.set()

    async def wait_stop(self) -> None:
        await self._stop.wait()

    async def take(self) -> tuple[WorkItem, ...]:
        """Claim your new messages for this run's chat (none once Stop was pressed, none when not steerable)."""
        if not self.steerable or self.stopping or self._take is None:
            return ()
        items = await self._take()
        self._taken = (*self._taken, *items)
        return items

    def note_done(self, name: str, activity: str | None, *, side_effect: bool = True) -> None:
        """A call completed. A side effect is listed in the Stopped line and rules a restart out."""
        if not side_effect:
            return
        self._side_effects = True
        self._done = (*self._done, past_line(activity) if activity else _name_line(name))

    def may_restart(self) -> bool:
        return not self._side_effects and self._restarts < self._max_restarts

    def restarted(self) -> None:
        self._restarts += 1
