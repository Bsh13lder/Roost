"""The bot's one CDP page, kept healthy (``KeeperDesk`` in ``roost/desk/client.py`` mixes this in).

The keeper's relay allows one CDP connection per bot and closes an older one (4409) when a new one comes. On
2026-10-27 the owner's Yes on a Send card met such a superseded socket: the page driver was handed it, sent outside
any retry, and the bot said "My browser didn't answer"; disarming the guards then failed too. So:

- **One connection at a time.** Page creation runs under one lock per desk: two first users connect once.
- **Every page call heals the same way** (``_run_on_page``): a dead connection (the base ``CdpClientError``, never a
  ``CdpReplyError``; or ``ConnectionClosed``) drops the page and runs the call once more on a fresh one. A reply that
  says the tab's session is gone (``session_gone``) forgets the session and runs the call again on the same
  connection, which attaches the tab in front. Any other failed command is that command's failure only: it is
  raised, and nothing shared is closed under the other users of the connection.
- **C3's page driver** runs each method's CDP work through ``_on_page_session``: the same healing, mid-method.
- **A hung browser restarts its computer** (owner, 2026-11-06): a command that times out on a tab that is not merely
  crashed has the browser probed (``browser_answers``); a browser that does not answer, or a page that keeps crashing,
  has the desk restart its computer (``_restart_hung``: Linux only, never while you hold it, once per cooldown) and
  the call runs once more on the fresh browser, its result saying so.
- **Armed guards follow the page.** The armed fence is remembered; a replacement page made while it is armed is
  guarded with the same fence before the call runs on it, and the old guards are let go (``disarm`` never raises on
  a closed connection).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, Awaitable, Callable, TypeVar

import websockets

from roost.constants import BROWSER_RESTARTED_TEXT, CRASHED_TAB_RECOVERED_TEXT
from roost.desk import DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpClientError, CdpReplyError, session_gone
from roost.desk.control import ControlMark
from roost.desk.crash import PageKeepsCrashing

logger = logging.getLogger(__name__)

# A page call is tried on the page there is (or a fresh one), then once more on a brand new page if that one turns
# out to be dead. Never more: a desk that is really unavailable surfaces as DeskUnavailable quickly.
_MAX_PAGE_ATTEMPTS = 2
# What a dead connection raises (a CdpReplyError is one of these by class, and is told apart by ``dead_connection``).
DEAD_CONNECTION_ERRORS = (CdpClientError, websockets.ConnectionClosed)

T = TypeVar("T")
PageCall = Callable[[DeskBrowserPage], Awaitable[T]]


def dead_connection(exc: BaseException) -> bool:
    """The socket is gone (closed, superseded, never connected), not one command's error reply or timeout."""
    if isinstance(exc, websockets.ConnectionClosed):
        return True
    return isinstance(exc, CdpClientError) and not isinstance(exc, CdpReplyError)


def with_notice(result: T, notice: str) -> T:
    """A page read after a recovery carries the notice the tool result starts with; other results are as they are."""
    if isinstance(result, PageText):
        return replace(result, notice=notice)   # type: ignore[return-value]
    return result


def with_crash_notice(result: T) -> T:
    return with_notice(result, CRASHED_TAB_RECOVERED_TEXT)


async def _with_session(page: DeskBrowserPage, call: Callable[[Any, str], Awaitable[T]]) -> T:
    client, session_id = await page.page_session()
    return await call(client, session_id)


class PageKeeping:
    """Mixed into ``KeeperDesk``: every attribute it reads is the desk's."""

    _bot_id: str
    _page: DeskBrowserPage | None
    _page_lock: asyncio.Lock
    _guards: Any                         # C3: BrowserGuards while a screen loop holds the lease
    _guarded: Any                        # the page those guards are on
    _fence: Any                          # the armed fence (None: the guards are off)
    _seen_mark: ControlMark
    _connect_page: Callable[[str, str], Awaitable[DeskBrowserPage]]
    _control_mark: Callable[[], ControlMark]

    async def _connect_once(self, relay_url: str, token: str) -> DeskBrowserPage:
        """The page, connected by one caller only: whoever comes while it connects gets the same page."""
        async with self._page_lock:
            if self._page is None:
                self._page = await self._connect_page(relay_url, token)
                self._seen_mark = self._control_mark()       # a fresh page starts on the tab in front anyway
            return self._page

    async def _drop_page(self, page: Any) -> None:
        """Close a dead page; it stops being the desk's page only if no one has replaced it meanwhile."""
        await page.close()
        if self._page is page:
            self._page = None

    async def _ensure_page(self) -> DeskBrowserPage:
        raise NotImplementedError        # KeeperDesk's: it may start the computer

    async def _call_with_reconnect(self, call: PageCall[T]) -> T:
        """A Desk call on the bot's page (``_run_on_page``). A failed command is ``DeskUnavailable``, as every
        caller of a desk expects, and closes nothing."""
        try:
            return await self._run_on_page(call)
        except CdpReplyError as exc:
            raise DeskUnavailable(f"the browser of bot {self._bot_id} did not answer: {exc}") from exc

    async def _restart_hung(self) -> bool:
        """Restart the computer of a hung browser; False when this desk may not (KeeperDesk's)."""
        return False

    async def _run_on_page(self, call: PageCall[T]) -> T:
        """``_run_on_page_once``; a browser that stopped answering, or a page that keeps crashing, restarts the
        computer and the call runs once more on the fresh browser."""
        try:
            return await self._run_on_page_once(call)
        except (CdpReplyError, PageKeepsCrashing) as exc:
            if not await self._browser_hung(exc) or not await self._restart_hung():
                raise
        return with_notice(await self._run_on_page_once(call), BROWSER_RESTARTED_TEXT)

    async def _browser_hung(self, exc: BaseException) -> bool:
        if isinstance(exc, PageKeepsCrashing):
            return True
        probe = getattr(self._page, "browser_answers", None)     # a page stand-in without the probe is taken as alive
        return probe is not None and not await probe()

    async def _run_on_page_once(self, call: PageCall[T]) -> T:
        """Run ``call`` on the bot's page; a dead connection, or a tab session still gone after one re-attach, gets
        a fresh page and one more try. Any other ``CdpReplyError`` is raised as it is."""
        last_exc: BaseException = RuntimeError("unreachable")   # a page call always runs at least once below
        for _ in range(_MAX_PAGE_ATTEMPTS):
            page = await self._ensure_page()
            try:
                await self._follow_after_hands(page)
                return await self._healing(page, call)
            except DEAD_CONNECTION_ERRORS as exc:
                if not (dead_connection(exc) or session_gone(exc)):
                    raise
                await self._drop_page(page)
                last_exc = exc
        raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {last_exc}") from last_exc

    async def _healing(self, page: DeskBrowserPage, call: PageCall[T]) -> T:
        """The call on a guarded page; a tab whose session is gone is forgotten and the call runs once more. A tab
        that crashed (§4: the command failed and the tab no longer answers) is closed, its address opened again in a
        fresh tab, and the call runs once more there; the result says so."""
        try:
            await self._guard_page(page)
            return await call(page)
        except CdpReplyError as exc:
            if session_gone(exc):
                page.forget_session()
                await self._guard_page(page)
                return await call(page)
            crashed = getattr(page, "tab_crashed", None)     # a page stand-in without the watch is taken as alive
            if crashed is None or self._control_mark().held or not await crashed():
                raise        # while you hold the computer, no tab of yours is closed or opened again under you
            return await self._after_crash(page, call)

    async def _after_crash(self, page: DeskBrowserPage, call: PageCall[T]) -> T:
        """The fresh tab and the one retry; a fresh tab that fails too says the page keeps crashing."""
        try:
            await page.reopen_crashed_tab()
            await self._guard_page(page)
            result = await call(page)
        except CdpReplyError as exc:
            raise PageKeepsCrashing() from exc
        return with_crash_notice(result)

    async def _follow_after_hands(self, page: DeskBrowserPage) -> None:
        """You took the computer and gave it back since this page last looked: the bot's tab becomes the tab
        you left in front (a sign-in that opened in a new tab, say). Never while you still hold it."""
        mark = self._control_mark()
        if mark == self._seen_mark or mark.held:
            return
        await page.follow_front_tab()
        self._seen_mark = mark

    async def _guard_page(self, page: DeskBrowserPage) -> None:
        """While a fence is armed, the page in use carries guards with it: a replacement page gets them before
        anything runs on it, and the old page's guards are let go."""
        if self._fence is None or self._guarded is page:
            return
        old, self._guards, self._guarded = self._guards, None, None
        if old is not None:
            await old.disarm()
        guards = await page.guards(hands_off=lambda: self._control_mark().held)
        await guards.arm(self._fence)
        self._guards, self._guarded = guards, page

    async def _page_session(self) -> tuple[Any, str]:
        """The bot's tab session; a tab closed by hand (a sign-in in a new tab, say) is attached again."""
        return await self._call_with_reconnect(lambda page: page.page_session())

    async def _on_page_session(self, call: Callable[[Any, str], Awaitable[T]]) -> T:
        """C3's page driver: one method's CDP work on the bot's tab, healed as any page call, mid-method too."""
        return await self._run_on_page(lambda page: _with_session(page, call))

    async def _arm_fence(self, fence: Any) -> None:
        """Arm the browser guards with ``fence`` (again: a wider fence only swaps it). A failed arm keeps the
        fence that was armed before, so a refused arm never guards later pages."""
        previous, self._fence = self._fence, fence

        async def arm(page: DeskBrowserPage) -> Any:
            guards = await page.guards(hands_off=lambda: self._control_mark().held)
            await guards.arm(fence)
            self._guards, self._guarded = guards, page
            return guards

        try:
            await self._call_with_reconnect(arm)
        except BaseException:
            self._fence = previous
            raise

    async def disarm_guards(self) -> None:
        guards, self._guards, self._guarded, self._fence = self._guards, None, None, None
        if guards is not None:
            await guards.disarm()

    def guards(self) -> Any:
        """The armed guards (what they blocked, closed or intercepted), or None."""
        return self._guards
