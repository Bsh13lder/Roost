"""The room: the cap of three, LRU eviction, the VM memory check and idle sleep."""

from __future__ import annotations

import uuid

import pytest

from roost.constants import COMPUTER_PAUSE_AFTER_S
from roost.keeper.computer_room import (
    ComputerRoom, NoRoom, RoomView, decide, idle_actions, parse_mem_total, parse_mem_usage,
)
from roost.keeper.computers import ComputerHandle
from roost.keeper.workspaces import _RunOutcome

A, B, C, D = (str(uuid.uuid4()) for _ in range(4))
PLENTY = 4000


def _view(running=(), *, last_used=None, held=(), busy=(), free=PLENTY, paused=()):
    return RoomView(running=tuple(running), last_used=last_used or {r: float(i) for i, r in enumerate(running)},
                    held=frozenset(held), busy=frozenset(busy), free_mb=free, paused=tuple(paused))


def test_starts_when_under_the_cap_with_memory():
    assert decide(D, _view([A, B])).kind == "start"


def test_an_already_running_bot_is_a_plain_start():
    assert decide(A, _view([A, B, C], free=1)).kind == "start"


def test_stops_the_least_recently_used_resting_one_at_the_cap():
    view = _view([A, B, C], last_used={A: 30.0, B: 10.0, C: 20.0})
    decision = decide(D, view)
    assert (decision.kind, decision.evict) == ("evict_then_start", B)


def test_never_evicts_one_you_are_watching_or_one_on_it():
    view = _view([A, B, C], last_used={A: 1.0, B: 2.0, C: 3.0}, held=[A], busy=[B])
    assert decide(D, view).evict == C


def test_no_room_when_all_are_busy():
    view = _view([A, B, C], held=[A], busy=[B, C])
    assert decide(D, view).kind == "no_room"


def test_no_room_when_the_vm_is_short_of_memory():
    assert decide(D, _view([A], free=100, held=[A])).kind == "no_room"
    # short of memory under the cap: stopping a resting one frees room
    assert decide(D, _view([A], free=100)).evict == A


def test_a_failed_memory_reading_is_no_room():
    assert decide(D, _view([A], free=None)).kind == "no_room"
    # at the cap a stop is possible and the memory is read again after it
    assert decide(D, _view([A, B, C], free=None)).kind == "evict_then_start"


def test_a_paused_one_is_the_first_to_go_when_memory_is_short():
    view = _view([A], free=100, paused=[B], last_used={A: 1.0, B: 5.0})
    assert decide(D, view).evict == B


def test_parse_docker_memory_figures():
    assert parse_mem_usage("3.83GiB") == 3922
    assert parse_mem_usage("212.4MiB / 1.465GiB\n100MiB / 1GiB") == 312
    assert parse_mem_usage("") == 0
    assert parse_mem_usage("nonsense") is None
    assert parse_mem_total("8218992640\n") == 7838
    assert parse_mem_total("") is None and parse_mem_total("x") is None


def test_idle_pauses_and_a_sleeping_computer_stays_asleep():
    view = _view([A, B], last_used={A: 0.0, B: 900.0})
    now = float(COMPUTER_PAUSE_AFTER_S) + 10
    assert idle_actions(view, frozenset(), now) == ((A, "pause"),)
    long_idle = RoomView(running=(), last_used={A: 0.0}, held=frozenset(), busy=frozenset(), free_mb=1,
                         paused=(A,))
    assert idle_actions(long_idle, frozenset({A}), 7 * 24 * 3600.0) == ()   # owner 2026-10-27: sleep, never stop
    assert idle_actions(long_idle, frozenset({A}), float(COMPUTER_PAUSE_AFTER_S) + 1) == ()


def test_a_held_computer_never_sleeps():
    view = _view([A], last_used={A: 0.0}, held=[A])
    assert idle_actions(view, frozenset(), 99999.0) == ()
    held_paused = RoomView(running=(), last_used={A: 0.0}, held=frozenset({A}), busy=frozenset(), free_mb=1,
                           paused=(A,))
    assert idle_actions(held_paused, frozenset({A}), 99999.0) == ()


# ---- ComputerRoom with a fake manager and runner ----------------------------------------------

class FakeManager:
    def __init__(self, running=(), paused=()):
        self.state_map = {b: "running" for b in running} | {b: "paused" for b in paused}
        self.used = {b: float(i) for i, b in enumerate(self.state_map)}
        self.calls: list[tuple[str, str]] = []

    def states(self):
        return dict(self.state_map)

    def last_used(self, bot_id):
        return self.used.get(bot_id)

    def touch(self, bot_id):
        self.used[bot_id] = 9999.0

    async def start(self, bot_id):
        self.calls.append(("start", bot_id))
        self.state_map[bot_id] = "running"
        return ComputerHandle(bot_id, "c", "v")

    async def stop(self, bot_id):
        self.calls.append(("stop", bot_id))
        self.state_map[bot_id] = "stopped"

    async def pause(self, bot_id):
        self.calls.append(("pause", bot_id))
        self.state_map[bot_id] = "paused"


class MemRunner:
    """Answers `docker info` and `docker stats` from a script of free-memory readings."""

    def __init__(self, *readings_mb: int | None, total_mb: int = 8000):
        self.readings = list(readings_mb)
        self.total = total_mb

    async def __call__(self, argv, timeout_s):
        if argv[1] == "info":
            return _RunOutcome(0, f"{self.total * 1024 * 1024}\n".encode(), b"", False)
        reading = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        if reading is None:
            return _RunOutcome(1, b"", b"down", False)
        return _RunOutcome(0, f"{self.total - reading}MiB / 8GiB\n".encode(), b"", False)


async def test_admit_starts_with_room():
    manager = FakeManager(running=[A])
    room = ComputerRoom(manager, runner=MemRunner(PLENTY))
    handle = await room.admit(D, frozenset())
    assert handle.bot_id == D and manager.calls == [("start", D)]


async def test_admit_evicts_then_rechecks_memory_and_starts():
    manager = FakeManager(running=[A, B, C])
    room = ComputerRoom(manager, runner=MemRunner(PLENTY, PLENTY))
    await room.admit(D, frozenset())
    assert manager.calls == [("stop", A), ("start", D)]


async def test_admit_raises_no_room():
    manager = FakeManager(running=[A, B, C])
    room = ComputerRoom(manager, runner=MemRunner(PLENTY))
    with pytest.raises(NoRoom):
        await room.admit(D, frozenset({A, B, C}))
    assert manager.calls == []
    short = ComputerRoom(FakeManager(running=[A]), runner=MemRunner(50))
    with pytest.raises(NoRoom):
        await short.admit(D, frozenset({A}))


async def test_admit_is_no_room_when_memory_is_still_short_after_the_stop():
    manager = FakeManager(running=[A, B, C])
    room = ComputerRoom(manager, runner=MemRunner(PLENTY, 100))
    with pytest.raises(NoRoom):
        await room.admit(D, frozenset())
    assert manager.calls == [("stop", A)]


async def test_free_mb_is_none_when_docker_does_not_answer():
    room = ComputerRoom(FakeManager(), runner=MemRunner(None))
    assert await room.free_mb() is None


async def test_the_sweeper_pauses_idle_ones_keeps_sleeping_ones_and_skips_held_ones():
    manager = FakeManager(running=[A, B], paused=[C])
    manager.used = {A: 0.0, B: 0.0, C: 0.0}
    now = [24 * 3600.0]
    room = ComputerRoom(manager, runner=MemRunner(PLENTY), clock=lambda: now[0])
    room.hold(B)
    manager.used[B] = 0.0
    await room.sweep()
    assert ("pause", A) in manager.calls and not [c for c in manager.calls if c[0] == "stop"]
    assert not [c for c in manager.calls if c[1] == B]
    room.release(B)
    assert B not in room.held()


async def test_hold_counts_every_socket():
    room = ComputerRoom(FakeManager(), runner=MemRunner(PLENTY))
    room.hold(A)
    room.hold(A)
    room.release(A)
    assert A in room.held()
    room.release(A)
    room.release(A)
    assert A not in room.held()
