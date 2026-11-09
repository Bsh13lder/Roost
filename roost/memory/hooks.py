"""``MemoryHooks``: what the turn runner calls around a run (after-run capture, the prompt section)."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable

from roost.bots.store import BotStore
from roost.config import Config
from roost.events.hub import EventHub
from roost.llm.types import Model
from roost.memory.capture import FinishedRun, capture, capture_eligible
from roost.memory.prompt import MemorySection, render_section
from roost.memory.ranking import pick_for_prompt
from roost.memory.service import MemoryService
from roost.memory.summaries import SummaryStore, summarise_if_due
from roost.memory.store import MemoryStore
from roost.talk.store import TalkStore

logger = logging.getLogger(__name__)


class MemoryHooks:
    def __init__(self, config: Config, talk: TalkStore, events: EventHub, *, worker: Model | None) -> None:
        self._config = config
        self._talk = talk
        self._events = events
        self._worker = worker
        self.service = MemoryService(MemoryStore(config), events)
        self.summaries = SummaryStore(config)

    async def after_run(self, run: FinishedRun) -> None:
        """Never raises (but cancellation): a memory problem must not touch the run that just finished."""
        if self._worker is None:
            return
        if capture_eligible(run):
            await self._guarded("Memory capture", run, self._capture(run))
        await self._guarded("Chat summary", run, self._summarise(run))

    async def _capture(self, run: FinishedRun) -> None:
        await capture(run, service=self.service, worker=self._worker, talk=self._talk, events=self._events)

    async def _summarise(self, run: FinishedRun) -> None:
        bot = await BotStore(self._config).get(run.user_id, run.bot_id)
        if bot is None:
            return   # a retired bot
        await summarise_if_due(run, talk=self._talk, summaries=self.summaries, worker=self._worker,
                               bot_name=bot.name)

    async def _guarded(self, what: str, run: FinishedRun, work: Awaitable[object]) -> None:
        try:
            await work
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Ids and the exception's type only: its message may repeat the user's text.
            logger.warning("%s failed for user %s bot %s thread %s: %s",
                           what, run.user_id, run.bot_id, run.thread_id, type(exc).__name__)

    async def prompt_section(self, user_id: str, bot_id: str, newest_text: str) -> MemorySection:
        """What this bot remembers, for its instructions; the lines shown are stamped as recalled."""
        memories = await self.service.list_for_bot(user_id, bot_id)
        section = render_section(pick_for_prompt(memories, newest_text))
        if section.shown:
            await self.service.touch_recalled(user_id, section.shown)
        return section
