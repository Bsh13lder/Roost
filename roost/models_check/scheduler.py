"""The daily check: fetch the page, remember any new model, change nothing on a failure."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from roost.constants import MODEL_CHECK_FIRST_DELAY_S, MODEL_CHECK_INTERVAL_S
from roost.models_check.fetch import PageFetcher
from roost.models_check.page import is_news, label_for, parse_model_ids
from roost.models_check.store import SeenModelStore

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


class ModelCheck:
    def __init__(
        self, store: SeenModelStore, fetcher: PageFetcher, *, sleep: Sleep = asyncio.sleep,
        interval_s: float = MODEL_CHECK_INTERVAL_S, first_delay_s: float = MODEL_CHECK_FIRST_DELAY_S,
    ) -> None:
        self._store = store
        self._fetcher = fetcher
        self._sleep = sleep
        self._interval_s = interval_s
        self._first_delay_s = first_delay_s

    async def run_once(self) -> tuple[str, ...]:
        """The ids stored as new this time. A failed or empty page stores nothing and logs only the error's type."""
        try:
            ids = parse_model_ids(await self._fetcher.fetch())
            return await self._store.add_new({model_id: label_for(model_id) for model_id in ids if is_news(model_id)})
        except Exception as exc:   # the check is best-effort; the gateway must go on
            logger.warning("The new-model check failed: %s", type(exc).__name__)
            return ()

    async def loop(self) -> None:
        """The first check after ``first_delay_s``, then one every ``interval_s``, until cancelled."""
        await self._sleep(self._first_delay_s)
        while True:
            await self.run_once()
            await self._sleep(self._interval_s)
