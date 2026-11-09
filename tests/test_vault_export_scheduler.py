"""The debounced export job and the EventHub listener that pokes it."""

from __future__ import annotations

import asyncio

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.vault_export.plan import conflict_path, decide, text_sha
from roost.vault_export.scheduler import ExportScheduler
from roost.vault_export.store import ExportResult


class _Runs:
    def __init__(self, *codes: str, hold: float = 0.0) -> None:
        self.codes = list(codes)
        self.calls: list[str] = []
        self.hold = hold

    async def __call__(self, user_id: str) -> ExportResult:
        self.calls.append(user_id)
        await asyncio.sleep(self.hold)
        return ExportResult(self.codes.pop(0) if self.codes else "ok")


async def _settle(scheduler: ExportScheduler, user_id: str) -> None:
    async with asyncio.timeout(2):
        while scheduler.pending(user_id):
            await asyncio.sleep(0.005)


def test_decide_follows_the_never_overwrite_rule():
    sha = text_sha("new")
    assert decide("new", None, None).action == "create"
    assert decide("new", "old-sha", sha).action == "same"
    assert (decide("new", "old-sha", "old-sha").action, decide("new", "old-sha", "old-sha").expected) == (
        "write", "old-sha")
    assert decide("new", "old-sha", "edited-sha").action == "conflict"
    assert decide("new", None, "someone-elses").action == "conflict"
    assert conflict_path("Roost/a/Dig.md") == "Roost/a/Dig.conflict.md"


async def test_a_burst_of_pokes_is_one_pass():
    runs = _Runs()
    scheduler = ExportScheduler(runs, delay=0.02)
    scheduler.start()
    for _ in range(5):
        scheduler.poke("u")
    await _settle(scheduler, "u")
    assert runs.calls == ["u"]
    await scheduler.stop()


async def test_nothing_runs_before_start_or_after_stop():
    runs = _Runs()
    scheduler = ExportScheduler(runs, delay=0.01)
    scheduler.poke("u")
    assert not scheduler.pending("u")
    scheduler.start()
    scheduler.poke("u")
    await scheduler.stop()
    await asyncio.sleep(0.03)
    assert runs.calls == []


async def test_a_partial_pass_is_tried_again():
    runs = _Runs("partial", "ok")
    scheduler = ExportScheduler(runs, delay=0.01, retry=0.01)
    scheduler.start()
    scheduler.poke("u")
    async with asyncio.timeout(2):
        while len(runs.calls) < 2 or scheduler.pending("u"):
            await asyncio.sleep(0.005)
    assert runs.calls == ["u", "u"]
    await scheduler.stop()


async def test_a_poke_during_a_pass_never_cuts_it_and_one_more_follows():
    runs = _Runs(hold=0.05)
    scheduler = ExportScheduler(runs, delay=0.01)
    scheduler.start()
    scheduler.poke("u")
    await asyncio.sleep(0.03)      # the pass is writing now
    scheduler.poke("u")
    async with asyncio.timeout(2):
        while len(runs.calls) < 2 or scheduler.pending("u"):
            await asyncio.sleep(0.005)
    assert runs.calls == ["u", "u"]
    await scheduler.stop()


async def test_a_failing_pass_is_logged_and_the_scheduler_lives_on(caplog):
    async def boom(user_id: str) -> ExportResult:
        raise RuntimeError("disk")
    scheduler = ExportScheduler(boom, delay=0.01)
    scheduler.start()
    scheduler.poke("u")
    await _settle(scheduler, "u")
    assert "a vault export pass failed: RuntimeError" in caplog.text
    await scheduler.stop()


async def test_the_hub_listener_pokes_only_for_export_changes():
    await init_db(load_config())
    runs = _Runs()
    scheduler = ExportScheduler(runs, delay=0.01)
    scheduler.start()
    hub = EventHub(load_config())
    hub.add_listener(scheduler.listener)
    hub.add_listener(lambda user_id, frame: 1 / 0)   # a broken listener never breaks a publish
    from roost.gateway.auth import register_user
    user_id = (await register_user(load_config(), "alice", "pw-123456")).id
    await hub.publish(user_id, {"type": "bot_status", "bot_id": "b"})
    assert not scheduler.pending(user_id)
    await hub.publish(user_id, {"type": "tasks_changed", "change": "created"})
    await _settle(scheduler, user_id)
    assert runs.calls == [user_id]
    await scheduler.stop()
