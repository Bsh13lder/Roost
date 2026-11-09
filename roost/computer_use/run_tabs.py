"""D5 (owner decision 2026-10-23, "spamming tabs and not closing"): a run's tabs don't pile up.

``snapshot`` notes the tabs open when the run first reaches the browser (they are never closed: yours, or ones an
earlier run kept). ``trim`` runs after a screen act: past ``CU_RUN_TABS_MAX`` tabs it closes the oldest tab this
run opened that is not the bot's own. ``cleanup`` at the run's end closes every tab the run opened except the
bot's own. While you hold the computer nothing is closed. A browser that went away is never an error here: these
are tidy-ups, logged and dropped."""

from __future__ import annotations

import logging
from typing import Any, Callable

from roost.constants import CU_RUN_TABS_MAX
from roost.desk.tabs import TabView

logger = logging.getLogger(__name__)


class RunTabs:
    def __init__(self, desk: Any, *, held: Callable[[], bool]) -> None:
        self._desk = desk
        self._held = held
        self._before: frozenset[str] | None = None
        self._opened: tuple[str, ...] = ()        # the run's own tabs, oldest first

    async def snapshot(self) -> None:
        if self._before is not None:
            return
        views = await self._views()
        if views is not None:
            self._before = frozenset(view.target_id for view in views)

    async def trim(self) -> None:
        views = await self._open_views()
        if views is None or len(views) <= CU_RUN_TABS_MAX:
            return
        spare = [target for target in self._opened if target in self._closable(views)]
        for target in spare[: len(views) - CU_RUN_TABS_MAX]:
            await self._close(target)

    async def cleanup(self) -> None:
        views = await self._open_views()
        if views is None:
            return
        for target in self._closable(views):
            await self._close(target)

    async def _open_views(self) -> tuple[TabView, ...] | None:
        """The tabs now, the run's new ones noted in order; None when nothing may or can be closed."""
        if self._before is None or self._held():
            return None
        views = await self._views()
        if views is None:
            return None
        seen = set(self._opened)
        fresh = tuple(v.target_id for v in views if v.target_id not in self._before and v.target_id not in seen)
        self._opened = (*self._opened, *fresh)
        return views

    def _closable(self, views: tuple[TabView, ...]) -> list[str]:
        before = self._before or frozenset()
        return [v.target_id for v in views if v.target_id not in before and not v.mine]

    async def _views(self) -> tuple[TabView, ...] | None:
        """The tabs, or None. With no Brave window it lists nothing: a listing speaks DevTools, which would
        start a Brave the bot closed."""
        try:
            if not await self._desk.browser_windows():
                return None
            return tuple(await self._desk.tabs())
        except Exception:
            logger.info("the run's tabs could not be listed", exc_info=True)
            return None

    async def _close(self, target_id: str) -> None:
        try:
            await self._desk.close_tab(target_id)
        except Exception:
            logger.info("a tab the run opened could not be closed", exc_info=True)
