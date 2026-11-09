"""The fence lives in the browser (C3 Task 7, Design meets code 7).

While a computer-use run holds the lease, ``BrowserGuards`` keeps the bot's Chromium to the job:

- **The site fence:** ``Fetch.enable`` pauses every ``Document`` request at the Request stage. A top-level navigation
  to a host outside the fence (or one ``check_url`` refuses) fails with ``BlockedByClient`` and the host is kept as
  ``blocked_last()`` for the runner's new-site card. Sub-resources are never paused, and a frame's own document (a
  payment widget) goes through: only the main frame is fenced.
- **No downloads:** ``Browser.setDownloadBehavior`` ``deny``.
- **No uploads:** ``Page.setInterceptFileChooserDialog``: a file picker never opens; ``chooser_opened()`` says one
  was asked for.
- **No prompts:** notifications, location, camera, microphone and the clipboard are denied.
- **No popups:** every page target that appears after ``arm`` is closed at once, and its address (when it has one)
  is kept for the runner to offer on a new-site card. B1 (2026-10-23): a new tab on the fence or on a sign-in
  host (``SIGN_IN_POPUP_HOSTS``: Google, Apple, Microsoft) stays open as a tab the bot can ``switch_tab`` to
  (``kept_targets()``); a blank one the bot's own tab opened waits for its address (``Target.targetInfoChanged``)
  and is then kept or closed by the same rule, once.
- **Your hands are yours:** while you hold control (``hands_off``), a tab you open is kept and your navigations are
  not fenced. The bot only works in your tab when it is the tab in front once you give it back
  (``roost/desk/front_tab.py``); ``retarget`` then moves the guards onto it.

``arm`` is idempotent (a second call only swaps the fence); ``disarm`` turns ``Fetch`` and the chooser interception
off and puts downloads back to ``default``. Neither the pump nor ``disarm`` fails on a connection that died (a
replaced page): ``KeeperDesk`` arms fresh guards on the new one.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

from roost.computer_use.fence import SiteFence
from roost.constants import SIGN_IN_POPUP_HOSTS
from roost.desk.cdp import CdpClientError, CdpReplyError, CdpTimeoutError
from roost.desk.url_policy import UrlBlocked, check_url

logger = logging.getLogger(__name__)

PAUSED = "Fetch.requestPaused"
CHOOSER = "Page.fileChooserOpened"
TARGET_CREATED = "Target.targetCreated"
TARGET_CHANGED = "Target.targetInfoChanged"
GUARD_EVENTS = frozenset({PAUSED, CHOOSER, TARGET_CREATED, TARGET_CHANGED})
DENIED_PERMISSIONS = ("notifications", "geolocation", "camera", "microphone", "clipboard-read", "clipboard-write")
BLOCKED_REASON = "BlockedByClient"
_DOCUMENT_PATTERN = {"resourceType": "Document", "requestStage": "Request"}
_WEB_SCHEMES = frozenset({"http", "https"})
_BLANK = "about:blank"
_PAGE = "page"


class GuardClient(Protocol):
    async def send(self, method: str, params: dict[str, Any] | None = None,
                   session_id: str | None = None) -> dict: ...
    def listen(self, methods: frozenset[str]) -> "asyncio.Queue[dict[str, Any]]": ...
    def unlisten(self, queue: "asyncio.Queue[dict[str, Any]]") -> None: ...


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def fence_allows(fence: SiteFence, url: str) -> bool:
    """A top-level address the fence lets through: about:blank, or a web address on a fence host that
    ``check_url`` accepts (no local addresses)."""
    if url == _BLANK:
        return True
    try:
        scheme = urlsplit(url).scheme.lower()
        check_url(url)
    except (ValueError, UrlBlocked):
        return False
    return scheme in _WEB_SCHEMES and fence.allows(_host(url))


def _sign_in_host(url: str) -> bool:
    """An https address on one of the sign-in hosts (or a subdomain of one)."""
    host = _host(url)
    if not url.lower().startswith("https://") or not host:
        return False
    return any(host == known or host.endswith(f".{known}") for known in SIGN_IN_POPUP_HOSTS)


class BrowserGuards:
    """One per computer-use lease, over the bot's CDP connection and its tab's session."""

    def __init__(self, client: GuardClient, session_id: str, own_target_id: str,
                 hands_off: Callable[[], bool] = lambda: False) -> None:
        self._client = client
        self._hands_off = hands_off
        self._session_id = session_id
        self._own_target = own_target_id
        self._fence = SiteFence(frozenset())
        self._armed = False
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._pump: asyncio.Task[None] | None = None
        self._main_frame = ""
        self._known_targets: frozenset[str] = frozenset()
        self._blocked_last = ""
        self._closed: tuple[str, ...] = ()
        self._kept: tuple[str, ...] = ()
        self._pending: frozenset[str] = frozenset()    # blank popups of the bot's tab, waiting for an address
        self._chooser = False

    @property
    def armed(self) -> bool:
        return self._armed

    def blocked_last(self) -> str:
        return self._blocked_last

    def closed_targets(self) -> tuple[str, ...]:
        return self._closed

    def chooser_opened(self) -> bool:
        return self._chooser

    def kept_targets(self) -> tuple[str, ...]:
        """The addresses of new tabs kept open (on the fence, or a sign-in host), oldest first."""
        return self._kept

    async def arm(self, fence: SiteFence) -> None:
        self._fence = fence
        if self._armed:
            return
        self._main_frame = await self._main_frame_id()
        self._known_targets = await self._page_targets()
        self._queue = self._client.listen(GUARD_EVENTS)          # before Fetch.enable: no pause is ever missed
        sid = self._session_id
        await self._client.send("Fetch.enable", {"patterns": [_DOCUMENT_PATTERN]}, session_id=sid)
        await self._client.send("Browser.setDownloadBehavior", {"behavior": "deny"})
        await self._client.send("Page.setInterceptFileChooserDialog", {"enabled": True}, session_id=sid)
        for name in DENIED_PERMISSIONS:
            await self._client.send("Browser.setPermission", {"permission": {"name": name}, "setting": "denied"})
        await self._client.send("Target.setDiscoverTargets", {"discover": True})
        self._pump = asyncio.create_task(self._drain(self._queue))
        self._armed = True

    async def retarget(self, session_id: str, own_target_id: str) -> None:
        """The bot's tab is now another one (the tab in front): armed guards move onto its session."""
        if session_id == self._session_id:
            return
        was_armed = self._armed
        if was_armed:
            await self.disarm()
        self._session_id, self._own_target = session_id, own_target_id
        if was_armed:
            await self.arm(self._fence)

    async def disarm(self) -> None:
        if not self._armed:
            return
        self._armed = False
        if self._pump is not None:
            self._pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump
            self._pump = None
        if self._queue is not None:
            self._client.unlisten(self._queue)
            self._queue = None
        sid = self._session_id
        steps = (("Fetch.disable", {}, sid), ("Page.setInterceptFileChooserDialog", {"enabled": False}, sid),
                 ("Browser.setDownloadBehavior", {"behavior": "default"}, None),
                 ("Target.setDiscoverTargets", {"discover": False}, None))
        for method, params, session_id in steps:
            if not await self._quiet(method, params, session_id):
                return   # a browser that is gone or hung answers none of the rest: don't wait 30 s for each

    async def handle(self, event: Mapping[str, Any]) -> None:
        """One guard event; the pump calls this for every queued event."""
        method, params = event.get("method"), event.get("params") or {}
        if method == PAUSED and event.get("sessionId") in (None, self._session_id):
            await self._on_paused(params)
        elif method == CHOOSER:
            self._chooser = True
        elif method == TARGET_CREATED:
            await self._on_target(params.get("targetInfo") or {})
        elif method == TARGET_CHANGED:
            await self._on_changed(params.get("targetInfo") or {})

    async def _drain(self, queue: "asyncio.Queue[dict[str, Any]]") -> None:
        while True:
            event = await queue.get()
            try:
                await self.handle(event)
            except CdpClientError as exc:           # the request, the tab or the whole connection went away
                logger.warning("a browser guard step failed: %s", exc)

    async def _on_paused(self, params: Mapping[str, Any]) -> None:
        request_id = params.get("requestId")
        url = str((params.get("request") or {}).get("url", ""))
        top_level = not self._main_frame or params.get("frameId") == self._main_frame
        if not top_level or self._hands_off() or fence_allows(self._fence, url):
            await self._client.send("Fetch.continueRequest", {"requestId": request_id}, session_id=self._session_id)
            return
        self._blocked_last = _host(url) or url
        await self._client.send("Fetch.failRequest", {"requestId": request_id, "errorReason": BLOCKED_REASON},
                                session_id=self._session_id)

    async def _on_target(self, info: Mapping[str, Any]) -> None:
        target_id = str(info.get("targetId", ""))
        if info.get("type") != _PAGE or target_id in self._known_targets or target_id == self._own_target:
            return
        self._known_targets = self._known_targets | {target_id}
        if self._hands_off():                       # you opened it while in control: it stays
            return
        url = str(info.get("url", ""))
        if url in ("", _BLANK) and info.get("openerId") == self._own_target:
            self._pending = self._pending | {target_id}   # window.open(): its address comes next
            return
        await self._keep_or_close(target_id, url)

    async def _on_changed(self, info: Mapping[str, Any]) -> None:
        target_id, url = str(info.get("targetId", "")), str(info.get("url", ""))
        if target_id not in self._pending or url in ("", _BLANK):
            return
        self._pending = self._pending - {target_id}
        await self._keep_or_close(target_id, url)

    async def _keep_or_close(self, target_id: str, url: str) -> None:
        """B1: a tab on the fence or on a sign-in host stays (the bot may switch to it); anything else closes."""
        if (url != _BLANK and fence_allows(self._fence, url)) or _sign_in_host(url):
            self._kept = (*self._kept, url)
            return
        await self._client.send("Target.closeTarget", {"targetId": target_id})
        if urlsplit(url).scheme.lower() in _WEB_SCHEMES:
            self._closed = (*self._closed, url)

    async def _main_frame_id(self) -> str:
        tree = await self._client.send("Page.getFrameTree", {}, session_id=self._session_id)
        frame_id = (tree.get("result") or {}).get("frameTree", {}).get("frame", {}).get("id")
        return frame_id if isinstance(frame_id, str) else ""

    async def _page_targets(self) -> frozenset[str]:
        """The pages open before arming (yours from Take control among them): never closed."""
        reply = await self._client.send("Target.getTargets", {})
        infos = (reply.get("result") or {}).get("targetInfos") or []
        return frozenset(str(t.get("targetId")) for t in infos if t.get("type") == _PAGE)

    async def _quiet(self, method: str, params: dict[str, Any], session_id: str | None) -> bool:
        """One disarm step; never raises. False when the browser is gone or hung (a dead socket or a
        timeout), so the steps after it are skipped; an error reply from a live browser is only a warning."""
        try:
            await self._client.send(method, params, session_id=session_id)
        except CdpClientError as exc:
            logger.warning("%s failed while disarming the browser guards: %s", method, exc)
            return isinstance(exc, CdpReplyError) and not isinstance(exc, CdpTimeoutError)
        return True
