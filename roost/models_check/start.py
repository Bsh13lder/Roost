"""Starting and stopping the daily check with the gateway."""

from __future__ import annotations

import asyncio
import contextlib

from roost.config import RoostConfig
from roost.constants import MODEL_CHECK_FIRST_DELAY_S
from roost.models_check.fetch import FilePageFetcher, HttpPageFetcher, PageFetcher
from roost.models_check.scheduler import ModelCheck
from roost.models_check.store import SeenModelStore


def _fetcher_for(config: RoostConfig) -> PageFetcher | None:
    """The page file in scripted mode (E2E), nothing else in scripted mode (no network in tests), the web otherwise."""
    if config.model_mode == "scripted":
        return FilePageFetcher(config.model_check_file) if config.model_check_file is not None else None
    return HttpPageFetcher()


def start_model_check(config: RoostConfig, store: SeenModelStore) -> "asyncio.Task[None] | None":
    """The loop's task, or ``None`` when the check is off."""
    fetcher = _fetcher_for(config) if config.model_check == "on" else None
    if fetcher is None:
        return None
    # A page file exists only in scripted mode (the E2E): check at once instead of waiting out the first delay.
    first_delay_s = 0 if config.model_check_file is not None else MODEL_CHECK_FIRST_DELAY_S
    return asyncio.create_task(ModelCheck(store, fetcher, first_delay_s=first_delay_s).loop(), name="model-check")


async def stop_model_check(task: "asyncio.Task[None] | None") -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
