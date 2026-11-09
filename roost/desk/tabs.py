"""A bot's browser tabs as it sees them (B1, owner decision 2026-10-23; ``docs/plans/2026-10-23-roost-tabs-signin-flow.md``).

``TabView`` is one page tab: its number (from 1, in ``Target.getTargets`` order), its target id, address and title,
and whether it is the bot's own tab. ``tab_views`` builds them; the desks list, switch and close tabs with them
(``DeskBrowserPage.tab_list`` / ``attach_tab`` / ``close_tab``, and the fake in ``roost/desk/fake_tabs.py``)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from roost.desk.stuck import host_of_url

CloseResult = Literal["closed", "blanked"]
BLANK = "about:blank"


@dataclass(frozen=True)
class TabView:
    index: int
    target_id: str
    url: str
    title: str
    mine: bool

    @property
    def host(self) -> str:
        return host_of_url(self.url)


def tab_views(tabs: Iterable[tuple[str, str, str]], own_target: str | None) -> tuple[TabView, ...]:
    """``(target id, url, title)`` triples, in order, as numbered views; ``own_target`` is the bot's tab."""
    return tuple(TabView(number, target_id, url, title, target_id == own_target)
                 for number, (target_id, url, title) in enumerate(tabs, start=1))


def tab_for_site(tabs: Iterable[TabView], url: str) -> TabView | None:
    """Owner, 2026-10-27 ("be aware which tab he used"): opening a site's front page that a tab already shows
    goes to that tab (the bot's own first), so WhatsApp isn't loaded again. A deeper address always navigates."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = host_of_url(url)
    if not host or parts.path not in ("", "/") or parts.query or parts.fragment:
        return None
    same = [tab for tab in tabs if tab.host == host]
    return next((tab for tab in same if tab.mine), same[0] if same else None)
