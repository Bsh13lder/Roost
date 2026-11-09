"""``LockedDesk``: helpers share their bot's one computer, so they take turns on it."""

from __future__ import annotations

import asyncio
from typing import Any

from roost.desk import Desk, PageText


class LockedDesk:
    """Wraps a ``Desk`` so a page load holds one lock: two helpers' ``open_page`` never overlap.

    Only helper runners get this wrapper. The parent waits on ``send_helpers``
    meanwhile, so it never competes for the tab."""

    def __init__(self, inner: Desk, lock: asyncio.Lock | None = None) -> None:
        self._inner = inner
        self._lock = lock if lock is not None else asyncio.Lock()

    async def open_page(self, url: str) -> PageText:
        async with self._lock:
            return await self._inner.open_page(url)

    async def read_page(self) -> PageText:
        async with self._lock:
            return await self._inner.read_page()

    async def search_page(self, url: str) -> Any:
        """web_search: the results page opens and is read under one turn of the lock."""
        async with self._lock:
            return await self._inner.search_page(url)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
