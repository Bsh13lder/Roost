"""Background tasks that nobody awaits (a warm-up, a part being spoken ahead, a memory capture after a call turn),
kept by reference until they end so none is garbage-collected mid-flight, their errors logged, and all of them
cancelled when the app closes. Tests wait on ``wait_idle``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TrackedTasks:
    def __init__(self) -> None:
        self._tasks: frozenset[asyncio.Task[Any]] = frozenset()

    def spawn(self, work: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(work, name=name)
        self._tasks = self._tasks | {task}
        task.add_done_callback(self._forget)
        return task

    def _forget(self, task: asyncio.Task[Any]) -> None:
        self._tasks = self._tasks - {task}
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.warning("background task %s failed: %s", task.get_name(), type(error).__name__)

    @property
    def pending(self) -> int:
        return len(self._tasks)

    async def wait_idle(self) -> None:
        """Wait until every task spawned so far (and any they spawned) has ended."""
        while self._tasks:
            await asyncio.wait(list(self._tasks))

    async def close(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
