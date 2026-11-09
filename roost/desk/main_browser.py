"""Open in your main Brave: the gateway's seam (stuck flow, Task 6; design §3, R8).

The gateway never runs ``open`` itself. ``make_main_browser`` builds what Task 7
puts on ``app.state.main_browser``, chosen by ``config.desk_mode`` the way
``DeskFactory`` chooses a desk:

- ``KeeperMainBrowser`` (keeper mode) sends the keeper's signed
  ``POST /desks/{bot_id}/main-browser/open`` through ``KeeperClient``. A refused
  address raises ``UrlBlocked``, and a down keeper or a failed open raises
  ``DeskUnavailable``.
- ``FakeMainBrowser`` (fake mode: every test and E2E run) never reaches a keeper
  or a browser. It checks the address the way the keeper does and records
  ``(bot_id, checked_url)``.

Both refuse an address longer than ``MAIN_BROWSER_URL_MAX_CHARS`` as ``UrlBlocked``
first. The keeper answers such a body 422, and ``KeeperClient`` turns every non-2xx
except a 400 into ``DeskUnavailable``, which the user would see as a 503.
"""

from __future__ import annotations

from typing import Protocol

from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.desk.url_policy import UrlBlocked, check_url


class MainBrowser(Protocol):
    async def open(self, bot_id: str, url: str) -> None: ...


def _refuse_overlong(url: str) -> None:
    """The keeper's body limit, applied before the request so it stays a refusal (400), not a 503."""
    if len(url) > MAIN_BROWSER_URL_MAX_CHARS:
        raise UrlBlocked(f"the address is longer than {MAIN_BROWSER_URL_MAX_CHARS} characters")


class KeeperMainBrowser:
    """The real seam: ``KeeperClient(config).open_in_main_browser``. Tests pass a ``client``
    built on an ``httpx`` transport that reaches the keeper app in process."""

    def __init__(self, config: RoostConfig, *, client: KeeperClient | None = None) -> None:
        self._client = client if client is not None else KeeperClient(config)

    async def open(self, bot_id: str, url: str) -> None:
        _refuse_overlong(url)
        await self._client.open_in_main_browser(bot_id, url)


class FakeMainBrowser:
    """Records every open, and opens nothing.

    ``opened`` is a tuple of ``(bot_id, checked_url)``. It is reassigned on every
    open and never mutated, so a reference taken earlier keeps its old value.
    ``fail`` makes every open raise ``DeskUnavailable``. Tests set it either as the
    keyword or as the attribute, which they flip through ``app.state`` the way
    they flip ``FakeDesk.force_unavailable``."""

    def __init__(self, *, fail: bool = False) -> None:
        self.opened: tuple[tuple[str, str], ...] = ()
        self.fail = fail

    async def open(self, bot_id: str, url: str) -> None:
        if self.fail:
            raise DeskUnavailable(f"the main browser is unavailable for bot {bot_id}")
        _refuse_overlong(url)
        checked_url = check_url(url)
        self.opened = (*self.opened, (bot_id, checked_url))


def make_main_browser(config: RoostConfig) -> MainBrowser:
    """``app.state.main_browser`` (wired by Task 7): the fake in fake mode, the keeper otherwise."""
    if config.desk_mode == "fake":
        return FakeMainBrowser()
    return KeeperMainBrowser(config)
