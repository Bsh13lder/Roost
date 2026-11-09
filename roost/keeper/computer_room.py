"""The room: at most ``COMPUTERS_MAX_RUNNING`` computers run, the VM must have memory left, idle ones sleep.

``decide`` and ``idle_actions`` are pure. ``ComputerRoom`` reads the VM's memory (``docker info`` minus
``docker stats``), asks ``decide``, evicts the least recently used resting computer when it has to, and runs
the sweeper that pauses an idle computer. A sleeping computer stays asleep with its tabs (owner, 2026-10-27: "go
sleep not disable"); only another computer that needs the room stops it. A computer a viewer is watching (held) or one whose
bot is working (busy) is never evicted and never put to sleep.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from roost.constants import (
    COMPUTER_DOCKER_CALL_TIMEOUT_S,
    COMPUTER_PAUSE_AFTER_S,
    COMPUTER_START_MIN_FREE_MB,
    COMPUTER_SWEEP_EVERY_S,
    COMPUTERS_MAX_RUNNING,
)
from roost.keeper.computers import ComputerHandle, ComputerState
from roost.keeper.workspaces import Runner, _run_docker

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024
_UNITS = {"b": 1, "kb": 1000, "kib": 1024, "mb": 1000**2, "mib": 1024**2, "gb": 1000**3, "gib": 1024**3,
          "tb": 1000**4, "tib": 1024**4}
_FIGURE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)\s*$")


class NoRoom(RuntimeError):
    """No computer can be started right now."""


@dataclass(frozen=True)
class RoomView:
    running: tuple[str, ...]                 # running, not paused
    last_used: Mapping[str, float]
    held: frozenset[str]                     # a viewer or control socket is open
    busy: frozenset[str]                     # the bot is On it (from the gateway)
    free_mb: int | None                      # None: the reading failed
    paused: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class RoomDecision:
    kind: Literal["start", "evict_then_start", "no_room"]
    evict: str | None = None


def _enough(count: int, free_mb: int | None) -> bool:
    return count < COMPUTERS_MAX_RUNNING and free_mb is not None and free_mb >= COMPUTER_START_MIN_FREE_MB


def _victim(view: RoomView, at_cap: bool) -> str | None:
    """Oldest resting computer; a paused one goes first unless only a running one lowers the count."""
    protected = view.held | view.busy
    pool = [(0, b) for b in view.paused if not at_cap] + [(1, b) for b in view.running]
    pool = [(rank, b) for rank, b in pool if b not in protected]
    if not pool:
        return None
    return min(pool, key=lambda item: (item[0], view.last_used.get(item[1], 0.0)))[1]


def decide(bot_id: str, view: RoomView) -> RoomDecision:
    if bot_id in view.running or _enough(len(view.running), view.free_mb):
        return RoomDecision("start")
    at_cap = len(view.running) >= COMPUTERS_MAX_RUNNING
    if view.free_mb is None and not at_cap:
        return RoomDecision("no_room")
    victim = _victim(view, at_cap)
    if victim is None:
        return RoomDecision("no_room")
    return RoomDecision("evict_then_start", victim)


def idle_actions(
    view: RoomView, paused: frozenset[str], now: float
) -> tuple[tuple[str, Literal["pause", "stop"]], ...]:
    actions: list[tuple[str, Literal["pause", "stop"]]] = []
    for bot_id, last in view.last_used.items():
        if bot_id in view.held:
            continue
        idle = now - last
        if bot_id not in paused and bot_id in view.running and idle > COMPUTER_PAUSE_AFTER_S:
            actions.append((bot_id, "pause"))
    return tuple(actions)


def _to_mb(text: str) -> float | None:
    match = _FIGURE_RE.match(text)
    if match is None:
        return None
    unit = match.group(2).lower() or "b"
    if unit not in _UNITS:
        return None
    return float(match.group(1)) * _UNITS[unit] / _BYTES_PER_MB


def parse_mem_total(stdout: str) -> int | None:
    """``docker info --format '{{.MemTotal}}'``: bytes, as a number."""
    mb = _to_mb(stdout.strip())
    return None if mb is None else int(mb)


def parse_mem_usage(stdout: str) -> int | None:
    """Sum of the used side of every ``used / limit`` line of ``docker stats --format '{{.MemUsage}}'``."""
    total = 0.0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        mb = _to_mb(line.partition("/")[0])
        if mb is None:
            return None
        total += mb
    return round(total)


class _Manager(Protocol):
    def states(self) -> dict[str, ComputerState]: ...
    def last_used(self, bot_id: str) -> float | None: ...
    def touch(self, bot_id: str) -> None: ...
    async def start(self, bot_id: str) -> ComputerHandle: ...
    async def stop(self, bot_id: str) -> None: ...
    async def pause(self, bot_id: str) -> None: ...


class ComputerRoom:
    def __init__(self, manager: _Manager, *, runner: Runner | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._manager = manager
        self._run: Runner = runner if runner is not None else _run_docker
        self._clock = clock
        self._holds: Counter[str] = Counter()
        self._admit_lock = asyncio.Lock()

    def hold(self, bot_id: str) -> None:
        self._holds[bot_id] += 1
        self._manager.touch(bot_id)

    def release(self, bot_id: str) -> None:
        if self._holds[bot_id] > 1:
            self._holds[bot_id] -= 1
        else:
            self._holds.pop(bot_id, None)
        self._manager.touch(bot_id)

    def held(self) -> frozenset[str]:
        return frozenset(self._holds)

    async def free_mb(self) -> int | None:
        total = await self._ask(["docker", "info", "--format", "{{.MemTotal}}"], parse_mem_total)
        used = await self._ask(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}"], parse_mem_usage)
        if total is None or used is None:
            return None
        return total - used

    async def _ask(self, argv: list[str], parse: Callable[[str], int | None]) -> int | None:
        outcome = await self._run(argv, COMPUTER_DOCKER_CALL_TIMEOUT_S)
        if outcome.timed_out or outcome.returncode != 0:
            return None
        return parse(outcome.stdout.decode("utf-8", errors="replace"))

    async def _view(self, busy: frozenset[str], *, memory: bool = True) -> RoomView:
        states = self._manager.states()
        running = tuple(b for b, s in states.items() if s == "running")
        paused = tuple(b for b, s in states.items() if s == "paused")
        last_used = {b: t for b in (*running, *paused) if (t := self._manager.last_used(b)) is not None}
        return RoomView(running, last_used, self.held(), busy, await self.free_mb() if memory else None, paused)

    async def admit(self, bot_id: str, busy: frozenset[str]) -> ComputerHandle:
        """Start (or wake) the bot's computer, stopping the least recently used resting one if it must."""
        async with self._admit_lock:
            decision = decide(bot_id, await self._view(busy))
            if decision.kind == "no_room":
                raise NoRoom("All computers are busy right now.")
            if decision.evict is not None:
                await self._manager.stop(decision.evict)
                again = await self._view(busy)
                if not _enough(len(again.running), again.free_mb):
                    raise NoRoom("All computers are busy right now.")
            return await self._manager.start(bot_id)

    async def sweep(self) -> None:
        """One pass: pause what has been idle a while, stop what has been paused a long while."""
        for bot_id in self._holds:
            self._manager.touch(bot_id)
        view = await self._view(frozenset(), memory=False)
        paused = frozenset(view.paused)
        for bot_id, action in idle_actions(view, paused, self._clock()):
            try:
                await (self._manager.pause(bot_id) if action == "pause" else self._manager.stop(bot_id))
            except Exception:  # one stuck computer must not end the sweeper
                logger.exception("could not %s the computer for bot %s", action, bot_id)

    async def run_sweeper(self) -> None:
        while True:
            await asyncio.sleep(COMPUTER_SWEEP_EVERY_S)
            try:
                await self.sweep()
            except Exception:
                logger.exception("the computer sweeper failed once; it keeps going")
