"""``FakeDesk`` — the in-memory stand-in ``DeskFactory`` hands out when
``config.desk_mode == "fake"``, which is every test (``tests/conftest.py``
forces ``ROOST_DESK=fake`` session-wide) and local dev without a running
keeper.

Never spawns a browser, a container, or a network connection. Every
method just updates small in-memory state and records exactly what it
was called with — so a test can assert on a call's shape (``exec_calls``
below) the same way it would against a real ``KeeperDesk`` talking to the
keeper, without needing one.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from roost.constants import EXEC_TIMEOUT_S, WEB_SEARCH_HOST
from roost.desk.fake_tabs import FakeTabs
from roost.desk.tabs import CloseResult, TabView
from roost.desk import (
    ComputerKind, DeskAsleep, DeskBusy, DeskStatus, DeskUnavailable, ExecResult, FrontWindow, InputRefusedByComputer,
    PageText, ScreenInput, ScreenStream, build_shell_argv,
)
from roost.desk.fake_cu import FAKE_GEOMETRY, FakeComputerPage, FakeScreenState
from roost.desk.fake_pages import FAKE_COOKIE_DOMAINS, FAKE_PAGES
from roost.research.fake_results import FAKE_SEARCH_HTML
from roost.research.results import SearchPage
from roost.desk.fake_screen import FakeScreen
from roost.desk.fake_shop import FAKE_SCREENS
from roost.desk.site_data import SignInSignals, SiteCleared, cookie_belongs, cookie_covers, origins_for, valid_host
from roost.desk.url_policy import check_url

# Full computer: the scripted page's Brave window, as `front` and `browsers` report it.
FAKE_BROWSER_RECT = FAKE_GEOMETRY.window_rect

# A real 4×3 green JPEG (631 bytes), so the web's <img> renders in fake mode.
FAKE_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxO"
    "UlNSMj5aYVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09P"
    "T09PT09PT0//wAARCAADAAQDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwAooopnyJ//2Q=="
)


# C3 E2E: a ``ROOST_DESK=fake`` gateway started with ``ROOST_FAKE_SCREEN=shop`` gives each Linux computer the
# "Fake shop" page (``roost/desk/fake_shop.py``). Unset (every test), no page is served until ``serve_screen``.
FAKE_SCREEN_ENV = "ROOST_FAKE_SCREEN"


def fake_screen_from_env() -> Mapping[str, FakeScreenState] | None:
    """The screen script ``ROOST_FAKE_SCREEN`` names, or None when unset. An unknown name is a mistake: it fails."""
    name = os.environ.get(FAKE_SCREEN_ENV, "").strip()
    if not name:
        return None
    if name not in FAKE_SCREENS:
        raise ValueError(f"{FAKE_SCREEN_ENV} names no fake screen: {name!r} (known: {', '.join(sorted(FAKE_SCREENS))})")
    return FAKE_SCREENS[name]


def _page_key(url: str) -> str:
    """The key a served page is kept under: the checked URL, with an empty path
    read as "/" the way a browser reads it (``https://login.example`` finds
    ``https://login.example/``'s pages). Raises ``UrlBlocked`` like ``check_url``."""
    parts = urlsplit(check_url(url))
    return urlunsplit(parts._replace(path=parts.path or "/"))


def _scripts(pages: Mapping[str, Sequence[PageText]]) -> dict[str, tuple[PageText, ...]]:
    """``pages`` keyed for lookup, each URL's pages as a tuple. A URL the bot may
    not open (``UrlBlocked``) or one with no page (``ValueError``) is a mistake
    in the script, so it fails here, not on the first open."""
    scripts = {_page_key(url): tuple(script) for url, script in pages.items()}
    for url, script in scripts.items():
        if not script:
            raise ValueError(f"a served address needs at least one page: {url}")
    return scripts


class FakeDesk:
    """One per bot id (cached by ``DeskFactory``, same as the real thing).

    ``force_unavailable`` makes every method raise ``DeskUnavailable`` —
    used by ``tests/test_desk_api.py`` to exercise the gateway desk
    routes' "keeper down -> 503" path without needing a real keeper to
    actually be down.

    ``pages`` scripts what a URL shows (the stuck flow). Each
    ``open_page``/``read_page`` of a served URL returns its next page,
    and the last one repeats. ``open_page`` keeps the page's ``status``;
    ``read_page`` drops it, as the real browser does. ``pages=None``
    serves ``FAKE_PAGES`` (``roost/desk/fake_pages.py``), so a
    ``ROOST_DESK=fake`` gateway (the E2E) can show a sign-in wall. Every
    other URL gets the plain "Fake Page", exactly as before.
    """

    def __init__(
        self,
        bot_id: str,
        computer: ComputerKind = "mac_brave",
        *,
        force_unavailable: bool = False,
        pages: Mapping[str, Sequence[PageText]] | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.computer: ComputerKind = computer
        self.force_unavailable = force_unavailable
        self.force_busy = False         # every browser call finds no free computer (``DeskBusy``)
        self._browser: Literal["running", "stopped"] = "stopped"
        self._workspace: Literal["running", "stopped", "absent"] = "absent"
        self.exec_calls: list[tuple[list[str], int]] = []
        self.exec_replies: tuple[ExecResult, ...] = ()     # Programs: what the next exec calls answer
        self.open_page_calls: list[str] = []
        self.retired = False
        self.screens: tuple[FakeScreen, ...] = ()      # every screen opened, newest last
        self._pages: dict[str, tuple[PageText, ...]] = _scripts(FAKE_PAGES if pages is None else pages)
        self._page_reads: dict[str, int] = {}
        self.inputs: tuple[tuple[str, int, int], ...] = ()     # (verb, x, y) of every screen input, never the text
        self.typed_lengths: tuple[int, ...] = ()               # how long each typed text was
        self._screen_page: FakeComputerPage | None = None      # C3's scripted page (``serve_screen``)
        self.guards_armed = False                               # C3: the browser guards of a screen loop
        self.guard_fences: tuple[Any, ...] = ()                 # every fence they were armed with, newest last
        self.fake_guards = FakeGuards()
        # the Sign-in card: the jar's cookie domains (the default pages' own cookies, A1)
        self.cookie_domains: tuple[str, ...] = FAKE_COOKIE_DOMAINS if pages is None else ()
        self.cleared_hosts: tuple[str, ...] = ()                # every site cleared, oldest first
        self.front_script: tuple[FrontWindow, ...] = ()         # full computer: the next `front` answers
        self.opened_apps: tuple[str, ...] = ()                  # every open_app, oldest first
        self.screen_inputs = 0                                  # how many inputs were screen acts
        self.visible_browsers: tuple[tuple[int, int, int, int], ...] | None = None   # None: the page's window
        self.no_window_apps: tuple[str, ...] = ()               # packages roost-input answers no_window for
        self.workspace_internet = False                         # A4: the workspace's network switch
        self.fake_tabs = FakeTabs()                             # B1: the browser's tabs (the page is the first)
        served = fake_screen_from_env() if computer == "linux" else None
        if served is not None:
            self.serve_screen(served)

    def _require_available(self) -> None:
        if self.force_unavailable:
            raise DeskUnavailable(f"desk unavailable for bot {self.bot_id}")

    @property
    def browser_state(self) -> Literal["running", "stopped"]:
        return self._browser

    def _require_room(self) -> None:
        if self.force_busy:
            raise DeskBusy(f"no free computer for bot {self.bot_id}")

    def serve(self, url: str, *pages: PageText) -> None:
        """Script what ``url`` shows from now on: each ``open_page``/``read_page``
        of it returns the next of ``pages``, and the last one repeats. Serving a
        URL again starts its pages over. The tables are replaced, never mutated."""
        key = _page_key(url)
        self._pages = {**self._pages, **_scripts({url: pages})}
        self._page_reads = {served: reads for served, reads in self._page_reads.items() if served != key}

    def _next_page(self, url: str) -> PageText | None:
        """The next scripted page for ``url`` (the last one repeats), or None when ``url`` is not served."""
        key = _page_key(url)
        script = self._pages.get(key)
        if script is None:
            return None
        reads = self._page_reads.get(key, 0)
        self._page_reads = {**self._page_reads, key: reads + 1}
        return script[min(reads, len(script) - 1)]

    async def status(self) -> DeskStatus:
        self._require_available()
        if self.computer == "mac_brave":
            return DeskStatus(browser=self._browser, workspace=self._workspace)
        state = "running" if self._browser == "running" else "stopped"
        return DeskStatus(browser=self._browser, workspace=self._workspace, computer=self.computer, state=state)

    async def start_browser(self) -> DeskStatus:
        self._require_available()
        self._require_room()
        self._browser = "running"
        return await self.status()

    async def wake_if_room(self) -> bool:
        self._require_available()
        if self.force_busy:
            return False
        self._browser = "running"
        return True

    async def stop_browser(self) -> DeskStatus:
        self._require_available()
        self._browser = "stopped"
        return await self.status()

    async def open_page(self, url: str) -> PageText:
        self._require_available()
        self._require_room()
        checked_url = check_url(url)
        self.open_page_calls.append(checked_url)
        served = self._next_page(checked_url)
        if served is not None:
            return served
        return PageText(
            url=checked_url, title="Fake Page", text=f"Fake content for {checked_url}", truncated=False
        )

    async def read_page(self) -> PageText:
        self._require_available()
        self._require_room()
        if not self.open_page_calls:
            return PageText(url="about:blank", title="Fake Page", text="Fake content", truncated=False)
        url = self.open_page_calls[-1]
        served = self._next_page(url)
        if served is not None:
            return replace(served, status=None)
        return PageText(url=url, title="Fake Page", text="Fake content", truncated=False)

    async def exec(self, command: str, timeout_s: int = EXEC_TIMEOUT_S) -> ExecResult:
        self._require_available()
        self.exec_calls.append((build_shell_argv(command), timeout_s))
        if self._workspace == "absent":
            self._workspace = "running"
        if self.exec_replies:      # a test's scripted answers, oldest first
            reply, self.exec_replies = self.exec_replies[0], self.exec_replies[1:]
            return reply
        return ExecResult(exit_code=0, stdout="", stderr="", timed_out=False, truncated=False)

    async def retire(self) -> None:
        self._require_available()
        self.retired = True
        self._browser = "stopped"
        self._workspace = "absent"

    async def screenshot(self) -> bytes:
        self._require_available()
        if self._browser != "running":
            raise DeskAsleep(f"the browser of bot {self.bot_id} is closed")
        return FAKE_JPEG

    async def current_url(self) -> str:
        """The last address opened ("" before any). Never wakes anything."""
        return self.open_page_calls[-1] if self.open_page_calls else ""

    async def open_screen(self) -> ScreenStream:
        """A fresh fake screen while the computer runs. Never wakes it; Mac Brave has no screen."""
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there is no screen to watch")
        if self._browser != "running":
            raise DeskAsleep(f"the computer of bot {self.bot_id} is asleep")
        screen = FakeScreen()
        self.screens = (*self.screens, screen)
        return screen

    async def send_input(self, action: ScreenInput, *, held: bool = False) -> None:
        """Record one screen input as (verb, x, y), and a typed text's length only. Never wakes the computer;
        Mac Brave has no screen."""
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there is no screen to send input to")
        if self._browser != "running":
            raise DeskAsleep(f"the computer of bot {self.bot_id} is asleep")
        if not action.screen:
            action.require_window()
        if held:
            raise InputRefusedByComputer("held")
        if action.screen and action.verb in ("click", "move", "scroll") and self._on_a_browser(action.x, action.y):
            raise InputRefusedByComputer("in_browser")
        self.inputs = (*self.inputs, (action.verb, action.x, action.y))
        self.screen_inputs += int(action.screen)
        if action.verb == "type":
            self.typed_lengths = (*self.typed_lengths, len(action.text))
        if self._screen_page is not None and not action.screen:
            await self._screen_page.apply(action)

    def _require_screen(self) -> None:
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there is no screen")
        if self._browser != "running":
            raise DeskAsleep(f"the computer of bot {self.bot_id} is asleep")

    def script_front(self, *answers: FrontWindow) -> None:
        """The next ``front_window`` calls answer these, one each; then the page decides again."""
        self.front_script = (*self.front_script, *answers)

    def _page_rect(self) -> tuple[int, int, int, int] | None:
        return FAKE_BROWSER_RECT if self._screen_page is not None else None

    def _browsers(self) -> tuple[tuple[int, int, int, int], ...]:
        if self.visible_browsers is not None:
            return self.visible_browsers
        rect = self._page_rect()
        return (rect,) if rect is not None else ()

    def _on_a_browser(self, x: int, y: int) -> bool:
        """roost-input --screen's own check: a point inside a visible Brave window is ``in_browser``."""
        return any(left <= x < left + w and top <= y < top + h for left, top, w, h in self._browsers())

    async def front_window(self) -> FrontWindow:
        """A scripted answer first; else Brave when a page is served, else another window."""
        self._require_screen()
        if self.front_script:
            answer, self.front_script = self.front_script[0], self.front_script[1:]
            return answer
        rect = self._page_rect()
        return FrontWindow("brave", rect) if rect is not None else FrontWindow("other")

    async def browser_windows(self) -> tuple[tuple[int, int, int, int], ...]:
        self._require_screen()
        return self._browsers()

    async def open_app(self, app: str, *, held: bool = False) -> None:
        self._require_screen()
        if held:
            raise InputRefusedByComputer("held")
        if app in self.no_window_apps:
            raise InputRefusedByComputer("no_window")
        self.opened_apps = (*self.opened_apps, app)
        # The E2E's scripted step: an app other than the browser is in front for the next answer only; the
        # browser comes back to the front at once.
        self.front_script = () if app == "browser" else (FrontWindow("other"),)

    def serve_screen(self, states: Mapping[str, FakeScreenState], *, minimized: bool = False) -> FakeComputerPage:
        """Script the Linux computer's page for C3 (``roost/desk/fake_cu.py``): ``page()`` returns it from now on,
        and ``send_input`` drives it. Mac Brave has no screen."""
        if self.computer != "linux":
            raise ValueError("only a Linux computer has a screen to script")
        self._screen_page = FakeComputerPage(states, minimized=minimized)
        return self._screen_page

    def page(self) -> Any:
        """C3's page driver: the scripted page once ``serve_screen`` was called, else None."""
        return self._screen_page

    # -- B1: tabs ---------------------------------------------------------------------------------------------

    def _own_page(self) -> tuple[str, str]:
        page = self._screen_page
        return (page.state.url, page.state.title) if page is not None else ("about:blank", "")

    async def tabs(self) -> tuple[TabView, ...]:
        self._require_screen()
        return self.fake_tabs.views(self._own_page())

    async def switch_tab(self, target_id: str) -> None:
        self._require_screen()
        self.fake_tabs.switch(target_id, self._own_page())

    async def close_tab(self, target_id: str) -> CloseResult:
        self._require_screen()
        return self.fake_tabs.close(target_id, self._own_page())

    async def arm_guards(self, fence: Any) -> None:
        """C3: record the fence the browser guards would hold. Mac Brave has no guards."""
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there are no browser guards")
        self.guards_armed = True
        self.guard_fences = (*self.guard_fences, fence)

    async def disarm_guards(self) -> None:
        self.guards_armed = False

    def guards(self) -> "FakeGuards | None":
        return self.fake_guards if self.guards_armed else None

    async def clear_site_data(self, host: str) -> SiteCleared:
        """The Sign-in card: drop the host's cookies (and its subdomains') from the fake jar. Linux only; the
        host is validated first (``BadHost``), as the real desk does."""
        site = valid_host(host)
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there is no computer browser to clear")
        gone = tuple(d for d in self.cookie_domains if cookie_belongs(d, site))
        self.cookie_domains = tuple(d for d in self.cookie_domains if not cookie_belongs(d, site))
        self.cleared_hosts = (*self.cleared_hosts, site)
        return SiteCleared(host=site, cookies=len(gone), origins=origins_for(site, gone))


    async def set_workspace_internet(self, on: bool) -> None:
        """A4: record the switch; a workspace that exists is recreated (it reads as absent until the next exec)."""
        self._require_available()
        if on != self.workspace_internet and self._workspace != "absent":
            self._workspace = "absent"
        self.workspace_internet = on

    async def search_page(self, url: str) -> SearchPage:
        """web_search (A3): the scripted results page for the search host, no HTML for any other address."""
        page = await self.open_page(url)
        html = FAKE_SEARCH_HTML if urlsplit(page.url).hostname == WEB_SEARCH_HOST else ""
        return SearchPage(page=page, html=html)

    async def sign_in_signals(self, host: str) -> SignInSignals:
        """The Sign-in card's I'm done: the page in front and how many jar domains cover the host. Linux only."""
        site = valid_host(host)
        self._require_available()
        if self.computer == "mac_brave":
            raise DeskUnavailable(f"bot {self.bot_id} works in Mac Brave: there is no computer browser to read")
        cookies = sum(1 for d in self.cookie_domains if cookie_covers(d, site))
        return SignInSignals(page=await self.read_page(), cookies=cookies)


class FakeGuards:
    """What the guards saw, set by a test: a blocked host, popups closed, a file picker asked for."""

    def __init__(self) -> None:
        self.blocked = ""
        self.closed: tuple[str, ...] = ()
        self.kept: tuple[str, ...] = ()
        self.chooser = False

    def blocked_last(self) -> str:
        return self.blocked

    def closed_targets(self) -> tuple[str, ...]:
        return self.closed

    def chooser_opened(self) -> bool:
        return self.chooser

    def kept_targets(self) -> tuple[str, ...]:
        return self.kept
