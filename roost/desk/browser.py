"""The bot's one persistent browser tab — ``DeskBrowserPage`` turns a raw
``CdpClient`` connection into ``open_page``/``read_page``, the only two
ways anything in Roost ever looks at what a bot's browser is showing.

On first use: the tab in front (``roost/desk/front_tab.py``: the active tab
of the focused window), or ``Target.createTarget`` (a fresh ``about:blank``
tab) only when no page is open →
``Target.attachToTarget`` (``flatten: true``, so every later command can
carry a flat ``sessionId`` instead of a nested target/session dance) →
``Page.enable`` (needed before ``Page.loadEventFired`` will ever fire) →
``Page.getFrameTree`` (the main frame's id, which tells the page's own
document apart from its iframes'). Every later call reuses that one
session — the bot gets one tab, not a fresh one per navigation — until
``follow_front_tab`` (after you give the computer back) moves it to the tab
you left in front. The front tab is read in an isolated world, never the
page's own (the same rule as ``ready.py`` and ``page_geometry.py``).

``Network`` and ``DOM`` are on only while they are needed. ``Network.enable``
(each response's HTTP status, for the stuck flow) is sent at the start of a
navigation and ``Network.disable`` when it ends; ``DOM.disable`` follows the
stuck signals' read. Left on, each one makes the browser stream or hold state
for the tab for as long as the session lives.

``read_page`` never runs JavaScript in the page — it reads the
already-computed accessibility tree (``Accessibility.getFullAXTree``)
instead. **No ``Runtime.evaluate`` anywhere in this module, deliberately**:
a hostile page's own script can poison anything ``Runtime.evaluate``
would hand back, and the accessibility tree is Chromium's own trusted
computation of what's rendered, not the page's. The stuck flow's two
page signals (a password box, a visible captcha frame) come from
``DOM.querySelectorAll`` for the same reason: Chromium's own selector
engine over the parsed DOM, with no page script run.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from roost.constants import (
    CDP_CRASH_PROBE_TIMEOUT_S,
    CU_FIRST_TAB_POLL_S,
    CU_FIRST_TAB_WAIT_S,
    PAGE_LOAD_EVENT_TIMEOUT_S,
    PAGE_TEXT_LIMIT,
    SCREENSHOT_JPEG_QUALITY,
    STUCK_CAPTCHA_FRAME_SELECTOR,
    STUCK_PASSWORD_SELECTOR,
    WEB_SEARCH_HTML_MAX_CHARS,
)
from roost.desk import DeskAsleep, PageText
from roost.desk.cdp import CdpClient, CdpClientError, CdpReplyError
from roost.desk.crash import CrashWatch
from roost.desk.front_tab import Tab, front_tab, page_tabs
from roost.desk.tabs import BLANK, CloseResult, TabView, tab_for_site, tab_views
from roost.desk.url_policy import check_url

from roost.desk.site_data import SignInSignals, SiteCleared, clear_site, count_site_cookies

if TYPE_CHECKING:
    from roost.desk.browser_guards import BrowserGuards
    from roost.desk.page_targets import CdpPageDriver

logger = logging.getLogger(__name__)

# Accessibility node roles worth reading as page content — everything
# else (generic containers, images, presentation-only nodes, ...) is
# noise for a model deciding what a page says.
_READABLE_ROLES = frozenset({"heading", "link", "StaticText", "paragraph", "listitem", "cell", "button"})

_LOAD_EVENT_METHOD = "Page.loadEventFired"
_RESPONSE_EVENT_METHOD = "Network.responseReceived"
# CDP's ``Network.ResourceType`` for a frame's own HTML; scripts, images and XHRs have other types.
_DOCUMENT_TYPE = "Document"
# ``DOM.getDocument`` depth: CDP's documented default and smallest allowed value (only the root's
# own children come back); ``DOM.querySelectorAll`` searches the whole tree from the root anyway.
_DOCUMENT_DEPTH = 1
# (password_field, captcha_frame) when the page's DOM cannot be read.
_NO_SIGNALS = (False, False)


def _status_of(response_event: asyncio.Future[dict[str, Any] | None]) -> int | None:
    """The HTTP status in a finished ``Network.responseReceived`` wait, or None
    when the wait has not finished, ran out, or the event carries no number."""
    if not response_event.done() or response_event.cancelled() or response_event.exception() is not None:
        return None
    params = (response_event.result() or {}).get("params") or {}
    status = (params.get("response") or {}).get("status")
    return status if isinstance(status, int) else None


def _settle(waiter: asyncio.Future[Any]) -> None:
    """Mark a finished wait's failure as seen (a closed connection fails every wait), so asyncio never logs it."""
    if waiter.done() and not waiter.cancelled():
        waiter.exception()


def _collapse_consecutive_repeats(lines: list[str]) -> list[str]:
    """Drop a line that is identical to the one right before it — the
    accessibility tree routinely repeats a node's own name at an
    ancestor and its single child (e.g. a heading wrapping one text
    node), which would otherwise double every line of real content."""
    collapsed: list[str] = []
    for line in lines:
        if collapsed and collapsed[-1] == line:
            continue
        collapsed.append(line)
    return collapsed


# What a person types sits in these as a child StaticText; the bot must never read it.
_TEXT_BOX_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})


def _inside_text_boxes(nodes: list[dict[str, Any]]) -> set[str]:
    """Ids of every node below a text box, walking ``childIds`` and, for orphans, ``parentId``."""
    by_id = {str(n["nodeId"]): n for n in nodes if "nodeId" in n}
    children: dict[str, list[str]] = {}
    for node_id, node in by_id.items():
        for child in node.get("childIds") or ():
            children.setdefault(node_id, []).append(str(child))
        parent = node.get("parentId")
        if parent is not None:
            children.setdefault(str(parent), []).append(node_id)
    pending = [i for i, n in by_id.items() if (n.get("role") or {}).get("value") in _TEXT_BOX_ROLES]
    hidden: set[str] = set()
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in hidden:
                hidden.add(child)
                pending.append(child)
    return hidden


def _extract_readable_lines(nodes: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    hidden = _inside_text_boxes(nodes)
    for node in nodes:
        if node.get("ignored") or str(node.get("nodeId")) in hidden:
            continue
        role = (node.get("role") or {}).get("value")
        if role not in _READABLE_ROLES:
            continue
        name = (node.get("name") or {}).get("value")
        if name:
            lines.append(name)
    return lines


def _build_page_text(nodes: list[dict[str, Any]]) -> tuple[str, bool]:
    collapsed = _collapse_consecutive_repeats(_extract_readable_lines(nodes))
    text = "\n".join(collapsed)
    if len(text) > PAGE_TEXT_LIMIT:
        return text[:PAGE_TEXT_LIMIT], True
    return text, False


class DeskBrowserPage:
    """Wraps one connected ``CdpClient`` as the bot's single tab."""

    def __init__(self, client: CdpClient,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._client = client
        self._sleep = sleep
        self._target_id: str | None = None
        self._session_id: str | None = None
        self._view_session_id: str | None = None
        self._main_frame_id: str | None = None
        self._frame_warned = False
        self._guards: "BrowserGuards | None" = None
        self._crash = CrashWatch(client)     # §4: tells a crashed tab from a slow one

    async def close(self) -> None:
        """Drop this page's underlying CDP connection. ``KeeperDesk``
        calls this when the connection turns out to be dead (an
        oversized reply, a keeper restart, a Brave crash, or a 4409
        takeover by another connection) so the next call opens a fresh
        page instead of failing against the same dead client forever
        (Fix round 1, finding 4)."""
        await self._client.close()

    def forget_session(self) -> None:
        """The bot's tab went away (closed by hand, crashed) while the socket is fine: the next call attaches the tab
        in front again on this same connection, and armed guards move onto it (``_ensure_session``)."""
        self._session_id = None
        self._target_id = None
        self._view_session_id = None

    async def _ensure_session(self) -> str:
        if self._session_id is not None:
            return self._session_id
        front = await self._first_front_tab()
        if front is not None:
            session_id = await self._attach(front.target_id)
        else:
            created = await self._client.send("Target.createTarget", {"url": "about:blank"})
            session_id = await self._attach(created["result"]["targetId"])
        if self._guards is not None:            # a forgotten session: the armed guards follow the new one
            await self._guards.retarget(session_id, self._target_id or "")
        return session_id

    async def _first_front_tab(self) -> Tab | None:
        """The tab in front. D5: Brave starts on the first DevTools bytes, so its own first window may come a
        moment later; it gets ``CU_FIRST_TAB_WAIT_S`` before a tab is made, so there is one tab, not two."""
        polls = int(CU_FIRST_TAB_WAIT_S / CU_FIRST_TAB_POLL_S)
        for _ in range(polls):
            front = await front_tab(self._client)
            if front is not None:
                return front
            await self._sleep(CU_FIRST_TAB_POLL_S)
        return await front_tab(self._client)

    async def _attach(self, target_id: str) -> str:
        attached = await self._client.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached["result"]["sessionId"]

        await self._client.send("Page.enable", session_id=session_id)
        await self._client.send("Inspector.enable", session_id=session_id)   # §4: Inspector.targetCrashed arrives
        # Stuck flow (design §1): the main frame's id (stable across top-level
        # navigations) picks the page's own document out of its iframes'. The
        # Network events that carry its status are on only during a navigation.
        tree = await self._client.send("Page.getFrameTree", session_id=session_id)

        self._target_id = target_id
        self._main_frame_id = tree.get("result", {}).get("frameTree", {}).get("frame", {}).get("id")
        self._frame_warned = False
        self._session_id = session_id
        return session_id

    async def follow_front_tab(self) -> bool:
        """Make the tab in front the bot's tab (you gave the computer back on another tab). Armed guards move
        with it, and the old tab is left open. False when nothing changed or no session was made yet (the
        first call picks the front tab anyway)."""
        if self._session_id is None:
            return False
        front = await front_tab(self._client)
        if front is None or front.target_id == self._target_id:
            return False
        await self._move_to(front.target_id)
        return True

    async def _move_to(self, target_id: str) -> str:
        """The bot's tab becomes ``target_id``: a new session, the armed guards moved onto it, the old one let go."""
        old_session = self._session_id
        session_id = await self._attach(target_id)
        if self._guards is not None:
            await self._guards.retarget(session_id, target_id)
        if old_session is not None:
            try:
                await self._client.send("Target.detachFromTarget", {"sessionId": old_session})
            except CdpReplyError as exc:               # the old tab is gone already
                logger.warning("the bot's previous tab could not be detached: %s", exc)
        return session_id

    # -- B1: the bot's tabs (docs/plans/2026-10-23-roost-tabs-signin-flow.md) -------------------------------

    async def tab_list(self) -> tuple[TabView, ...]:
        """Every page tab, numbered from 1, the bot's own marked. Reads no page: CDP's target list only."""
        await self._ensure_session()
        tabs = await page_tabs(self._client)
        return tab_views(((t.target_id, t.url, t.title) for t in tabs), self._target_id)

    async def attach_tab(self, target_id: str) -> None:
        """Bring ``target_id`` to the front and make it the bot's tab (its guards move with it)."""
        await self._ensure_session()
        await self._client.send("Target.activateTarget", {"targetId": target_id})
        session_id = self._session_id if target_id == self._target_id else await self._move_to(target_id)
        await self._client.send("Page.bringToFront", session_id=session_id)

    async def close_tab(self, target_id: str) -> CloseResult:
        """Close ``target_id``. The last tab is never closed: it goes to about:blank. Closing the bot's own tab
        makes the tab in front its tab."""
        await self._ensure_session()
        tabs = await page_tabs(self._client)
        if len(tabs) <= 1:
            session_id = self._session_id if target_id == self._target_id else await self._move_to(target_id)
            await self._client.send("Page.navigate", {"url": BLANK}, session_id=session_id)
            return "blanked"
        await self._client.send("Target.closeTarget", {"targetId": target_id})
        if target_id == self._target_id:
            front = await front_tab(self._client)
            if front is not None:
                self._session_id = None               # that session went with its tab
                await self._move_to(front.target_id)
        return "closed"

    # -- §4: a crashed tab (OOM-killed renderer) ---------------------------------------------------------------

    async def tab_crashed(self) -> bool:
        """Whether the bot's tab is dead: its crash event was seen, or it no longer answers a probe. False with no
        session yet (nothing to have crashed)."""
        if self._session_id is None:
            return False
        return await self._crash.crashed(self._session_id)

    async def browser_answers(self) -> bool:
        """A hung browser (2026-11-06): the browser itself, not the tab, answers ``Browser.getVersion`` within the
        probe's time."""
        try:
            async with asyncio.timeout(CDP_CRASH_PROBE_TIMEOUT_S):
                await self._client.send("Browser.getVersion")
        except (CdpClientError, TimeoutError):
            return False
        return True

    async def _target_url(self, target_id: str) -> str:
        """The address the crashed tab showed, from the browser (a dead renderer's target still knows it)."""
        try:
            info = await self._client.send("Target.getTargetInfo", {"targetId": target_id})
        except CdpReplyError:
            return ""
        return str(info.get("result", {}).get("targetInfo", {}).get("url") or "")

    async def reopen_crashed_tab(self) -> str | None:
        """Close the bot's crashed tab and open the same address in a fresh one (made, attached, guarded and
        navigated the normal way). Returns the address reopened, or ``None`` when there was no tab to reopen."""
        dead = self._target_id
        if dead is None:
            return None
        url = await self._target_url(dead)
        try:
            await self._client.send("Target.closeTarget", {"targetId": dead})
        except CdpReplyError as exc:               # already gone with its crash
            logger.warning("the crashed tab could not be closed: %s", exc)
        self.forget_session()
        created = await self._client.send("Target.createTarget", {"url": BLANK})
        session_id = await self._attach(created["result"]["targetId"])
        if self._guards is not None:
            await self._guards.retarget(session_id, self._target_id or "")
        if url and url != BLANK:
            await self._navigate(session_id, url)
        return url

    async def page_session(self) -> tuple[CdpClient, str]:
        """The CDP client and the bot's tab session, for C3's page driver (``roost/desk/page_targets.py``). A closed
        socket (the keeper's 4409 when another connection came) is never handed out, even with a session cached:
        ``CdpClientError`` lets ``KeeperDesk`` replace the page."""
        if not self._client.is_open:
            raise CdpClientError("connection closed")
        return self._client, await self._ensure_session()

    async def guards(self, hands_off: Callable[[], bool] = lambda: False) -> "BrowserGuards":
        """C3: the browser guards over the bot's tab (one per page, armed while a screen loop holds the lease;
        they follow the tab in front). ``hands_off`` says you hold control: your tabs and navigations stay."""
        from roost.desk.browser_guards import BrowserGuards

        session_id = await self._ensure_session()
        if self._guards is None:
            self._guards = BrowserGuards(self._client, session_id, self._target_id or "", hands_off)
        return self._guards

    async def clear_site(self, host: str) -> SiteCleared:
        """The Sign-in card: clear one site's cookies and storage in this browser (``roost/desk/site_data.py``)."""
        return await clear_site(self._client, await self._ensure_session(), host)

    async def open_and_html(self, url: str) -> tuple[PageText, str]:
        """web_search (A3): open the results page, then read its document's HTML by fixed CDP (``DOM.getDocument``,
        ``DOM.getOuterHTML``; no page script). Roost parses it; nothing in it runs."""
        page = await self.open_page(url)
        session_id = await self._ensure_session()
        document = await self._client.send("DOM.getDocument", {"depth": 0}, session_id=session_id)
        node_id = document.get("result", {}).get("root", {}).get("nodeId")
        outer = await self._client.send("DOM.getOuterHTML", {"nodeId": node_id}, session_id=session_id)
        return page, str(outer.get("result", {}).get("outerHTML", ""))[:WEB_SEARCH_HTML_MAX_CHARS]

    async def sign_in_signals(self, host: str) -> SignInSignals:
        """The Sign-in card's I'm done: the tab in front becomes the bot's tab, then its page and the host's
        cookie count are read (``roost/desk/site_data.py``)."""
        await self.follow_front_tab()
        cookies = await count_site_cookies(self._client, host)
        return SignInSignals(page=await self.read_page(), cookies=cookies)

    def page_driver(self) -> "CdpPageDriver":
        """C3's ``PageDriver`` over this tab: its controls, boxes, screenshots and facts."""
        from roost.desk.page_targets import CdpPageDriver

        return CdpPageDriver(self.page_session, self.read_page)

    async def open_page(self, url: str, *, reuse_tab: bool = False) -> PageText:
        """Navigate the bot's tab to ``url``. With ``reuse_tab`` (a Linux computer), a site's front page that a
        tab already shows is that tab, brought up and read, not loaded again (``tab_for_site``)."""
        checked_url = check_url(url)
        if reuse_tab:
            tab = tab_for_site(await self.tab_list(), checked_url)
            if tab is not None:
                if not tab.mine:
                    await self.attach_tab(tab.target_id)
                return await self.read_page()
        session_id = await self._ensure_session()
        status = await self._navigate(session_id, checked_url)
        return replace(await self.read_page(), status=status)

    async def _navigate(self, session_id: str, url: str) -> int | None:
        """Navigate the bot's tab to ``url``. Returns the main document's HTTP
        status, or None when none arrived (a DNS error, a page that never answered).

        Both waits are armed *before* `Page.navigate` is sent, not after —
        otherwise a load event that fires faster than this coroutine
        gets scheduled back (a real risk once the keeper relay and the
        browser are both local processes with near-zero latency) would
        already have come and gone by the time anything was listening
        for it, turning a near-instant navigation into a full 20 s wait
        for nothing. ``CdpClient`` routes frames in socket order, and the
        main document's ``responseReceived`` always comes before
        ``loadEventFired``: once the load event is in, the status is
        caught or never coming, so it is read without waiting any longer.
        A redirect's 3xx never fires ``responseReceived``, so the status is
        the final page's. ``Network`` is on from before the waiters are armed
        until the navigation ends, however it ends.
        """
        await self._client.send("Network.enable", session_id=session_id)
        load_event = asyncio.ensure_future(
            self._client.wait_event(_LOAD_EVENT_METHOD, session_id=session_id, timeout=PAGE_LOAD_EVENT_TIMEOUT_S)
        )
        response_event = asyncio.ensure_future(
            self._client.wait_event(
                _RESPONSE_EVENT_METHOD, session_id=session_id, timeout=PAGE_LOAD_EVENT_TIMEOUT_S,
                predicate=self._is_main_document,
            )
        )
        try:
            navigated = await self._client.send("Page.navigate", {"url": url}, session_id=session_id)
            self._warn_if_status_unreadable(navigated.get("result", {}).get("frameId"))
            await load_event
            return _status_of(response_event)
        finally:
            load_event.cancel()
            response_event.cancel()
            _settle(response_event)
            await self._disable(session_id, "Network.disable")

    def _warn_if_status_unreadable(self, navigated_frame_id: str | None) -> None:
        """Without a main frame id, or with one that is not the frame ``Page.navigate`` navigated, no
        response can be taken for the page's own, so every ``open_page`` would report no status and
        the stuck detector would never see a 403 or a 429. Said once per page session, and never with
        the address in it (it can carry a token)."""
        if self._frame_warned:
            return
        if self._main_frame_id is not None and navigated_frame_id in (None, self._main_frame_id):
            return
        self._frame_warned = True
        logger.warning("The page's main frame id is missing or does not match the navigated frame; "
                       "pages in this session will report no HTTP status")

    async def _disable(self, session_id: str, method: str) -> None:
        """Switch a CDP domain off again. An error reply (the tab went away) is only a warning:
        the read or navigation it follows has its own result, and ``KeeperDesk`` treats any CDP
        error as a dead connection."""
        try:
            await self._client.send(method, session_id=session_id)
        except CdpReplyError as exc:
            logger.warning("%s failed: %s", method, exc)

    def _is_main_document(self, event: dict[str, Any]) -> bool:
        """The page's own HTML response: a Document in the main frame, never an iframe's or a file's."""
        params = event.get("params") or {}
        return (
            self._main_frame_id is not None
            and params.get("type") == _DOCUMENT_TYPE
            and params.get("frameId") == self._main_frame_id
        )

    async def read_page(self) -> PageText:
        session_id = await self._ensure_session()

        tree = await self._client.send("Accessibility.getFullAXTree", session_id=session_id)
        nodes = tree.get("result", {}).get("nodes", [])
        text, truncated = _build_page_text(nodes)

        info = await self._client.send(
            "Target.getTargetInfo", {"targetId": self._target_id}, session_id=session_id
        )
        target_info = info.get("result", {}).get("targetInfo", {})
        password_field, captcha_frame = await self._read_signals(session_id)

        return PageText(
            url=target_info.get("url", ""),
            title=target_info.get("title", ""),
            text=text,
            truncated=truncated,
            password_field=password_field,
            captcha_frame=captcha_frame,
        )

    async def _read_signals(self, session_id: str) -> tuple[bool, bool]:
        """``(password_field, captcha_frame)`` for the stuck detector (design R2).

        The accessibility text drops text boxes and frames, so these come from
        ``DOM.querySelectorAll`` with the shared selectors -- Chromium's own
        selector engine, no page script, still no ``Runtime.evaluate``. A DOM
        that cannot be read right now (the page navigating away mid-read)
        gives no signals rather than failing the read: ``KeeperDesk`` treats
        any CDP error as a dead connection and would replace the bot's tab."""
        try:
            document = await self._client.send("DOM.getDocument", {"depth": _DOCUMENT_DEPTH}, session_id=session_id)
            root_id = document.get("result", {}).get("root", {}).get("nodeId")
            if root_id is None:
                logger.warning("DOM.getDocument gave no root node; the page's signals are unknown")
                return _NO_SIGNALS
            return (
                await self._any_match(session_id, root_id, STUCK_PASSWORD_SELECTOR),
                await self._any_match(session_id, root_id, STUCK_CAPTCHA_FRAME_SELECTOR),
            )
        except CdpReplyError as exc:
            logger.warning("could not read the page's DOM signals: %s", exc)
            return _NO_SIGNALS
        finally:
            await self._disable(session_id, "DOM.disable")

    async def _any_match(self, session_id: str, root_id: int, selector: str) -> bool:
        found = await self._client.send(
            "DOM.querySelectorAll", {"nodeId": root_id, "selector": selector}, session_id=session_id
        )
        return bool(found.get("result", {}).get("nodeIds"))

    async def capture_screenshot(self) -> bytes:
        """The bot's tab as a JPEG (CDP ``Page.captureScreenshot``). Reads pixels only: no script runs.
        Never opens a tab (S1.8): the bot's own session, else a session on the page already open.

        A ``CdpReplyError`` (e.g. "Session with given id not found") means the
        session behind that capture -- the bot's own, or a previous view's --
        no longer has a tab, not that the connection died. Re-attach to
        whatever page is open now and retry once, still never
        ``Target.createTarget``, so a tab the user closed doesn't fail every
        poll (S1.8 Fix round 1, finding 1)."""
        session_id = self._session_id or self._view_session_id or await self._attach_view()
        try:
            return await self._send_capture(session_id)
        except CdpReplyError:
            self._view_session_id = None   # that tab went away: attach to whatever's open now
            return await self._send_capture(await self._attach_view())

    async def current_url(self) -> str:
        """The address of the tab in front (the one you were on). Opens nothing; no page script runs."""
        front = await front_tab(self._client)
        return front.url if front is not None else ""

    async def _send_capture(self, session_id: str) -> bytes:
        shot = await self._client.send(
            "Page.captureScreenshot", {"format": "jpeg", "quality": SCREENSHOT_JPEG_QUALITY}, session_id=session_id,
        )
        return base64.b64decode(shot.get("result", {}).get("data", ""))

    async def _attach_view(self) -> str:
        """Attach to the browser's tab in front for viewing only, never ``Target.createTarget``.
        With no page open there is nothing to show: ``DeskAsleep``."""
        front = await front_tab(self._client)
        if front is None:
            raise DeskAsleep("the bot's browser has no open page")
        attached = await self._client.send("Target.attachToTarget", {"targetId": front.target_id, "flatten": True})
        self._view_session_id = attached["result"]["sessionId"]
        return self._view_session_id
