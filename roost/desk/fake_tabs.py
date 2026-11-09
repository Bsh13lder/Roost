"""The fake Linux computer's browser tabs (B1), for the tests and the scripted gateway.

The scripted page (``FakeDesk.serve_screen``) is the bot's first tab, ``BOT``; a test adds others with ``add``.
Switching only moves the bot's mark (the scripted page keeps drawing); closing drops a tab, and the last one is
never closed: it is counted as blanked, as the real browser leaves it on about:blank."""

from __future__ import annotations

from roost.desk import DeskUnavailable
from roost.desk.tabs import CloseResult, TabView, tab_views


class FakeTabs:
    BOT = "BOT"

    def __init__(self) -> None:
        self._others: tuple[tuple[str, str, str], ...] = ()
        self._bot_open = True
        self.mine = self.BOT
        self.blanked = 0
        self.switched: tuple[str, ...] = ()

    def add(self, target_id: str, url: str, title: str) -> None:
        self._others = (*self._others, (target_id, url, title))

    def remove(self, target_id: str) -> None:
        """A tab went away by itself (the page closed it)."""
        if target_id == self.BOT:
            self._bot_open = False
        self._others = tuple(tab for tab in self._others if tab[0] != target_id)

    def views(self, own_page: tuple[str, str]) -> tuple[TabView, ...]:
        """Every tab, the bot's scripted page first; ``own_page`` is that page's (url, title)."""
        bot = ((self.BOT, *own_page),) if self._bot_open else ()
        return tab_views((*bot, *self._others), self.mine)

    def switch(self, target_id: str, own_page: tuple[str, str]) -> None:
        self._require(target_id, own_page)
        self.mine = target_id
        self.switched = (*self.switched, target_id)

    def close(self, target_id: str, own_page: tuple[str, str]) -> CloseResult:
        views = self.views(own_page)
        self._require(target_id, own_page)
        if len(views) <= 1:
            self.blanked += 1
            return "blanked"
        self.remove(target_id)
        if target_id == self.mine:
            self.mine = self.views(own_page)[0].target_id
        return "closed"

    def _require(self, target_id: str, own_page: tuple[str, str]) -> None:
        if all(view.target_id != target_id for view in self.views(own_page)):
            raise DeskUnavailable(f"no tab {target_id} in the fake browser")
