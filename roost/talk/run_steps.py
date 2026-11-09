"""The activity pill's steps (docs/plans/2026-10-23-roost-activity-pill.md).

``RunSteps`` publishes one live-only ``run_step`` frame when a run starts thinking, when each tool starts and ends,
and when its reply starts streaming, in the plain words of ``roost/talk/plain_steps.py``. Each step opens with
``start`` and closes with ``done`` or ``failed`` under the same number. ``RunStepsLog`` is an ``EventHub``
listener that keeps each bot's current run's newest steps (the newest state of each) for the live snapshot, and
drops them once the bot is no longer On it. Frames are never stored.

A note (owner, 2026-11-04: "the steps belong inside that card") is the bot's own words between steps in your
chat ("Search is done. I'm picking the Acme job."): a ``note`` step, done at once, one line of at most
``RUN_NOTE_MAX_CHARS`` without its "On it: …" lead, with ``tainted`` set to the run's taint at that moment so the
pill can wear the Web mark. Blank words and the same words twice in a row add nothing."""

from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from roost.constants import RUN_NOTE_MAX_CHARS, RUN_STEPS_KEPT
from roost.talk.chat_feel import without_on_it
from roost.talk.plain_steps import THINK_LINE, WRITING_LINE, PlainStep, plain_step

RUN_STEP_TYPE = "run_step"
NOTE_KIND = "note"
_ON_IT = "on_it"
_ELLIPSIS = "…"


def note_line(text: str) -> str:
    """The note's one line: no "On it: …" lead, whitespace folded, at most ``RUN_NOTE_MAX_CHARS``."""
    words = " ".join(without_on_it(text).split())
    if len(words) <= RUN_NOTE_MAX_CHARS:
        return words
    return words[:RUN_NOTE_MAX_CHARS - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


class _Publisher(Protocol):
    async def publish(self, user_id: str, event: dict[str, Any]) -> int: ...


class RunSteps:
    """One run's steps, numbered from 1. The open think or message step closes when anything else starts."""

    def __init__(self, events: _Publisher, *, user_id: str, bot_id: str, thread_id: str | None,
                 run_id: str) -> None:
        self._events = events
        self.run_id = run_id
        self._ids = {"bot_id": bot_id, "thread_id": thread_id, "run_id": run_id}
        self._user_id = user_id
        self._count = 0
        self._open: tuple[int, PlainStep] | None = None      # the think or message step still running
        self._tools: Mapping[int, PlainStep] = MappingProxyType({})
        self._last_note = ""

    async def begin(self) -> None:
        """The run started: Thinking, until a tool or the reply begins."""
        await self._open_marker(PlainStep("think", THINK_LINE))

    async def writing(self) -> None:
        """The reply started streaming (a no-op while it already is)."""
        if self._open is None or self._open[1].kind != "message":
            await self._open_marker(PlainStep("message", WRITING_LINE))

    async def tool_start(self, tool: str, arguments: Mapping[str, Any]) -> int:
        await self._close_marker()
        step = plain_step(tool, arguments)
        number = self._next()
        self._tools = MappingProxyType({**self._tools, number: step})
        await self._send(number, step, "start")
        return number

    async def tool_end(self, number: int, *, ok: bool) -> None:
        step = self._tools.get(number)
        if step is None:
            return
        self._tools = MappingProxyType({n: s for n, s in self._tools.items() if n != number})
        await self._send(number, step, "done" if ok else "failed")

    async def note(self, text: str, *, tainted: bool) -> None:
        """The bot's words between steps, as their own done ``note`` step (nothing for blank or repeated words)."""
        line = note_line(text)
        if not line or line == self._last_note:
            return
        self._last_note = line
        await self._close_marker()
        await self._send(self._next(), PlainStep(NOTE_KIND, line), "done", tainted=tainted)

    async def finish(self) -> None:
        """The run ended: whatever is still open is done."""
        await self._close_marker()

    async def _open_marker(self, step: PlainStep) -> None:
        await self._close_marker()
        number = self._next()
        self._open = (number, step)
        await self._send(number, step, "start")

    async def _close_marker(self) -> None:
        if self._open is not None:
            number, step = self._open
            self._open = None
            await self._send(number, step, "done")

    def _next(self) -> int:
        self._count += 1
        return self._count

    async def _send(self, number: int, step: PlainStep, state: str, *, tainted: bool | None = None) -> None:
        frame = {
            "type": RUN_STEP_TYPE, **self._ids, "step": number, "kind": step.kind, "line": step.line,
            "host": step.host, "at": datetime.now(timezone.utc).isoformat(), "state": state,
        }
        await self._events.publish(self._user_id, frame if tainted is None else {**frame, "tainted": tainted})


class RunStepsLog:
    """Each bot's current run's steps, keyed by (user id, bot id), the newest state of each step, in memory."""

    def __init__(self) -> None:
        self._rings: Mapping[tuple[str, str], tuple[dict[str, Any], ...]] = MappingProxyType({})

    def listen(self, user_id: str, frame: dict[str, Any]) -> None:
        kind, bot_id = frame.get("type"), frame.get("bot_id")
        if not isinstance(bot_id, str):
            return
        key = (user_id, bot_id)
        if kind == RUN_STEP_TYPE:
            ring = self._rings.get(key, ())
            if ring and ring[-1].get("run_id") != frame.get("run_id"):
                ring = ()
            kept = {name: value for name, value in frame.items() if name != "seq"}
            others = tuple(f for f in ring if f.get("step") != kept.get("step"))
            ordered = tuple(sorted((*others, kept), key=lambda f: f.get("step", 0)))
            self._set(key, ordered[-RUN_STEPS_KEPT:])
        elif kind == "bot_status" and frame.get("status") != _ON_IT and key in self._rings:
            self._set(key, None)

    def _set(self, key: tuple[str, str], ring: tuple[dict[str, Any], ...] | None) -> None:
        rings = {name: value for name, value in self._rings.items() if name != key}
        if ring:
            rings[key] = ring
        self._rings = MappingProxyType(rings)

    def for_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """The snapshot's ``run_steps``: bot id -> its current run's steps, oldest first."""
        return {bot: [dict(f) for f in ring] for (user, bot), ring in self._rings.items() if user == user_id}
