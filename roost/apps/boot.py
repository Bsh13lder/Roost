"""``AppReinstaller``: a computer the keeper created fresh gets its owner's approved apps back
(docs/plans/2026-10-22-roost-install-app.md §5).

The desk factory's boot hook calls ``on_fresh`` right after such a start; it schedules one ``ensure`` in the
background and returns at once, so the computer's start never waits for apt. A failure is a log line and an audit
row (``AppService.reinstall``), never a crash. The tasks are kept until they finish, so none is garbage-collected."""

from __future__ import annotations

import asyncio

from roost.apps.service import AppService


class AppReinstaller:
    def __init__(self, service: AppService) -> None:
        self._service = service
        self._tasks: frozenset[asyncio.Task[None]] = frozenset()

    async def on_fresh(self, bot_id: str) -> None:
        task = asyncio.get_running_loop().create_task(self._service.reinstall(bot_id))
        self._tasks = self._tasks | {task}
        task.add_done_callback(self._forget)

    def _forget(self, task: "asyncio.Task[None]") -> None:
        self._tasks = self._tasks - {task}

    async def drain(self) -> None:
        """Wait for every reinstall in flight (shutdown and tests)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
