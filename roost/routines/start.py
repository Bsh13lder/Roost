"""Starting and stopping the routine scheduler with the gateway (the ``models_check/start.py`` pattern)."""

from __future__ import annotations

import asyncio
import contextlib

from roost.routines.launcher import RoutineLauncher
from roost.routines.runs import RoutineRunStore, utc_now
from roost.routines.scheduler import RoutineScheduler
from roost.routines.store import RoutineStore
from roost.routines.system_reports import jobs_for


def build_scheduler(state) -> RoutineScheduler:
    """The scheduler over ``app.state``'s stores. One per gateway."""
    runs: RoutineRunStore = state.routine_runs
    routines: RoutineStore = state.routine_store
    launcher = RoutineLauncher(state.talk, state.turns, runs, state.events)

    async def waiting(user_id: str, bot_id: str) -> bool:
        return await state.approvals.open_for_bot(user_id, bot_id) is not None

    return RoutineScheduler(
        state.config, clock=utc_now, launcher=launcher, runs=runs, routines=routines, turns=state.turns,
        bots=state.bots, waiting=waiting, hooks=state.routine_hooks,
        jobs=jobs_for(state), watch=getattr(state, "watch_checker", None),
    )


def start_scheduler(state) -> "asyncio.Task[None]":
    """The loop's task: ``app.state.scheduler_task``."""
    return asyncio.create_task(build_scheduler(state).loop(), name="routine-scheduler")


async def stop_scheduler(task: "asyncio.Task[None] | None") -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
