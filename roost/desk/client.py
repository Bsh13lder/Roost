"""Gateway-side client for the keeper's signed HTTP API.

``KeeperClient`` builds and sends one signed request at a time
(``roost.desk.signing``) and turns any connection-level failure — the
keeper process not running, connection refused, timed out — into
``DeskUnavailable``, never a raw ``httpx`` exception leaking past this
module. ``KeeperDesk`` is the real (non-fake) ``Desk`` implementation
Night-1 runs with by default: it drives ``KeeperClient`` for the HTTP
lifecycle endpoints and lazily opens a ``DeskBrowserPage`` (over a
``CdpClient`` connected through the keeper's CDP relay) the first time
anything needs to look at the bot's tab.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable

import httpx
import websockets

from roost.computer_use.timing import desk_input_timeout_s
from roost.config import RoostConfig
from roost.constants import (
    COMPUTER_HUNG_RESTART_COOLDOWN_S,
    DESK_WAKE_CHECK_AFTER_S,
    COMPUTER_ROOM_POLL_S, COMPUTER_ROOM_WAIT_S, LIVE_RELAY_CHUNK_MAX,
    EXEC_TIMEOUT_S, KEEPER_EXEC_REQUEST_TIMEOUT_S, KEEPER_RETIRE_REQUEST_TIMEOUT_S, MAC_REQUEST_TIMEOUT_S,
)
from roost.desk import (
    ComputerKind, DeskAsleep, DeskBusy, DeskStatus, DeskUnavailable, ExecResult, FrontWindow, InputRefusedByComputer,
    PageText, ScreenInput, ScreenStream, build_shell_argv,
)
from roost.desk.tabs import CloseResult, TabView
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpClient, CdpReplyError
from roost.desk.control import ControlMark
from roost.desk.page_keeping import DEAD_CONNECTION_ERRORS, PageKeeping
from roost.desk.page_targets import CdpPageDriver
from roost.desk.signing import signed_headers
from roost.desk.site_data import SignInSignals, SiteCleared, valid_host
from roost.research.results import SearchPage
from roost.desk.url_policy import UrlBlocked
from roost.keeper.macfs.errors import MacFsError

logger = logging.getLogger(__name__)

_DESK_TOKEN_HEADER = "X-Roost-Desk-Token"
# The default timeout for every keeper call *except* workspace/exec,
# which needs its own, longer one -- see KEEPER_EXEC_REQUEST_TIMEOUT_S
# (Fix round 1, finding 5).
_CONTROL_REQUEST_TIMEOUT_S = 15.0
# A computer start may pull the boot wait (COMPUTER_BOOT_TIMEOUT_S) and a memory check into one call.
KEEPER_COMPUTER_START_TIMEOUT_S = 60.0
_BUSY_MAX = 50       # the keeper refuses a longer "busy" list
_ASLEEP = "asleep"
_INPUT_REFUSALS = frozenset({"held", "not_chromium", "outside", "too_fast", "in_browser", "no_window"})
# The fields each verb sends to the keeper's input route (its body is extra="forbid").
_INPUT_FIELDS = {
    "click": ("x", "y", "count"), "move": ("x", "y"), "key": ("key",), "type": ("text",),
    "scroll": ("x", "y", "notches"),
}


def input_body(action: ScreenInput, *, held: bool) -> dict[str, Any]:
    """The keeper's ``InputBody`` for ``action``: only its verb's own fields, and the bot's window or, for a
    screen act, the screen flag (never both)."""
    fields = {name: getattr(action, name) for name in _INPUT_FIELDS[action.verb]}
    body: dict[str, Any] = {"action": {"verb": action.verb, **fields}, "held": held}
    if action.screen:
        return {**body, "screen": True}
    left, top, width, height = action.require_window()
    return {**body, "window": {"left": left, "top": top, "width": width, "height": height}}


def input_timeout_s(action: ScreenInput) -> float:
    """How long the desk waits for one input: longer than the keeper, which waits longer than roost-input."""
    chars = len(action.text) if action.verb == "type" else 0
    return max(_CONTROL_REQUEST_TIMEOUT_S, desk_input_timeout_s(chars))


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _rect_of(value: Any) -> tuple[int, int, int, int] | None:
    """Four integers from the keeper, or None (the keeper already checked them; this is the second look)."""
    if isinstance(value, list) and len(value) == 4 and all(type(v) is int for v in value):
        return value[0], value[1], value[2], value[3]
    return None


def front_from(data: dict[str, Any]) -> FrontWindow:
    """The keeper's ``front`` answer; anything strange is ``DeskUnavailable``."""
    rect = _rect_of(data.get("window"))
    if data.get("front") == "brave" and rect is not None:
        return FrontWindow("brave", rect)
    if data.get("front") == "other" and data.get("window") is None:
        return FrontWindow("other")
    raise DeskUnavailable("the computer gave a strange answer about its front window")


def windows_from(data: dict[str, Any]) -> tuple[tuple[int, int, int, int], ...]:
    raw = data.get("windows")
    rects = tuple(_rect_of(item) for item in raw) if isinstance(raw, list) else (None,)
    if any(rect is None for rect in rects):
        raise DeskUnavailable("the computer gave a strange list of browser windows")
    return tuple(rect for rect in rects if rect is not None)


def _input_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail if isinstance(detail, str) else ""

_NOBODY_HOLDS = ControlMark(epoch=0, held=False)


def _never_held() -> ControlMark:
    return _NOBODY_HOLDS


async def _connect_page(relay_url: str, token: str) -> DeskBrowserPage:
    """Open one fresh ``CdpClient``/``DeskBrowserPage`` pair against the
    keeper's relay. The default (real) page builder ``KeeperDesk`` uses;
    tests inject their own in its place.

    A refused or failed WebSocket upgrade (the keeper process down, a
    bad token, no browser running for this bot) raises ``OSError`` or a
    ``websockets`` exception straight out of ``connect()`` -- wrapped
    here into ``DeskUnavailable`` so it reaches the gateway route the
    same way every other "can't use the desk right now" failure does,
    instead of as a raw exception type the route's ``except
    DeskUnavailable`` was never written to catch (Fix round 1,
    finding 6).
    """
    cdp_client = CdpClient(relay_url, token)
    try:
        await cdp_client.connect()
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        raise DeskUnavailable(f"could not reach the desk's CDP relay at {relay_url}: {exc}") from exc
    return DeskBrowserPage(cdp_client)


def _vnc_url(keeper_url: str, bot_id: str) -> str:
    """The keeper's per-computer VNC relay: ``ws://.../desks/{bot_id}/computer/vnc`` (binary frames)."""
    return _relay_url(keeper_url, bot_id, "linux").removesuffix("/cdp") + "/vnc"


async def _connect_screen(url: str, headers: dict[str, str]) -> Any:
    return await websockets.connect(url, additional_headers=headers, max_size=LIVE_RELAY_CHUNK_MAX * 4)


class KeeperScreen:
    """A ``ScreenStream`` over the keeper's VNC relay socket. It never logs what passes through it."""

    def __init__(self, socket: Any) -> None:
        self._socket = socket

    async def send(self, data: bytes) -> None:
        await self._socket.send(data)

    async def receive(self) -> bytes:
        """The next binary chunk, or ``b""`` once the far end has closed."""
        try:
            message = await self._socket.recv()
        except websockets.ConnectionClosed:
            return b""
        return message if isinstance(message, bytes) else b""

    async def close(self) -> None:
        await self._socket.close()


def _relay_url(keeper_url: str, bot_id: str, computer: ComputerKind = "mac_brave") -> str:
    """``http://127.0.0.1:18801`` -> ``ws://127.0.0.1:18801/desks/{bot_id}/cdp``, or ``.../computer/cdp`` for a
    Linux computer (and ``https`` -> ``wss``, for completeness, though Night-1 never uses it)."""
    if keeper_url.startswith("https://"):
        base = "wss://" + keeper_url[len("https://") :]
    elif keeper_url.startswith("http://"):
        base = "ws://" + keeper_url[len("http://") :]
    else:
        base = keeper_url
    return f"{base}/desks/{bot_id}/{'computer/' if computer == 'linux' else ''}cdp"


class KeeperClient:
    """Signs and sends one keeper HTTP request at a time.

    ``transport`` is an injectable ``httpx`` transport (defaulting to a
    real one) so tests can point this at the keeper's actual FastAPI app
    in-process via ``httpx.ASGITransport`` — the same "run the real app,
    fake only the process boundary" style ``tests/test_bots_api.py`` uses
    for the gateway — instead of needing a live keeper process.
    """

    def __init__(self, config: RoostConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._transport = transport

    async def _request(
        self, method: str, path: str, body: bytes = b"", *, timeout: float = _CONTROL_REQUEST_TIMEOUT_S,
        asleep_on_conflict: bool = False, refused_on_bad_request: bool = False, busy_on_conflict: bool = False,
    ) -> dict[str, Any]:
        headers = signed_headers(self._config.keeper_secret, method, path, body)
        url = f"{self._config.keeper_url}{path}"
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.request(method, url, content=body, headers=headers)
        except httpx.TransportError as exc:
            raise DeskUnavailable(f"keeper unreachable at {self._config.keeper_url}: {exc}") from exc
        if asleep_on_conflict and response.status_code == 409:
            raise DeskAsleep(f"the browser of {path} is closed")
        if busy_on_conflict and response.status_code == 409:
            raise DeskBusy(f"no free computer for {path}")
        if refused_on_bad_request and response.status_code == 400:
            # Stuck flow (Task 6): the keeper's check_url refused the address. That is
            # the user's 400 ("That address can't be opened."), not a down desk's 503.
            raise UrlBlocked(f"the keeper refused the address sent to {method} {path}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Fix round 1, finding 6: a non-2xx keeper response (Docker
            # not running, Brave failed to launch, a secret mismatch,
            # a malformed bot id, ...) used to propagate as a raw
            # HTTPStatusError all the way to the gateway route, which
            # only catches DeskUnavailable -- turning any of these into
            # a bare 500 instead of the clean 503 the contract defines
            # for "the desk can't be used right now".
            raise DeskUnavailable(
                f"keeper returned {response.status_code} for {method} {path}: {response.text}"
            ) from exc
        return response.json()

    async def get_desk(self, bot_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/desks/{bot_id}")

    async def start_browser(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/browser/start")

    async def stop_browser(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/browser/stop")

    async def start_workspace(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/workspace/start")

    async def exec_workspace(self, bot_id: str, argv: list[str], timeout_s: int) -> dict[str, Any]:
        body = json.dumps({"argv": argv, "timeout_s": timeout_s}).encode()
        # Fix round 1, finding 5: the keeper itself may legitimately
        # take up to EXEC_TIMEOUT_S running the command -- this one
        # call needs a longer HTTP timeout than every other keeper
        # call, or a slow-but-fine command looks exactly like a dead
        # keeper (503) right before it would have returned.
        return await self._request(
            "POST", f"/desks/{bot_id}/workspace/exec", body=body, timeout=KEEPER_EXEC_REQUEST_TIMEOUT_S
        )

    async def set_workspace_internet(self, bot_id: str, on: bool) -> dict[str, Any]:
        """A4: the keeper recreates the workspace on its network (or with none); files are kept."""
        body = json.dumps({"internet": on}).encode()
        return await self._request("POST", f"/desks/{bot_id}/workspace/internet", body=body)

    async def stop_workspace(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/workspace/stop")

    async def retire(self, bot_id: str) -> dict[str, Any]:
        # Needs its own longer timeout -- see KEEPER_RETIRE_REQUEST_TIMEOUT_S's
        # docstring (the same class of fix as exec_workspace's, above).
        return await self._request(
            "DELETE", f"/desks/{bot_id}", timeout=KEEPER_RETIRE_REQUEST_TIMEOUT_S
        )

    async def attach_browser(self, bot_id: str) -> dict[str, Any]:
        """The running browser's relay token. Never starts it: 409 → ``DeskAsleep`` (S1.8)."""
        return await self._request("POST", f"/desks/{bot_id}/browser/attach", asleep_on_conflict=True)

    async def start_computer(self, bot_id: str, busy: frozenset[str] = frozenset()) -> dict[str, Any]:
        """Start or wake the bot's Linux computer. 409 ``no_room`` raises ``DeskBusy``."""
        body = json.dumps({"busy": sorted(busy - {bot_id})[:_BUSY_MAX]}).encode()
        return await self._request("POST", f"/desks/{bot_id}/computer/start", body=body, busy_on_conflict=True,
                                   timeout=KEEPER_COMPUTER_START_TIMEOUT_S)

    async def attach_computer(self, bot_id: str) -> dict[str, Any]:
        """The running computer's tokens. Never wakes it: 409 raises ``DeskAsleep``."""
        return await self._request("POST", f"/desks/{bot_id}/computer/attach", asleep_on_conflict=True)

    async def pause_computer(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/computer/pause")

    async def stop_computer(self, bot_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/desks/{bot_id}/computer/stop", timeout=KEEPER_COMPUTER_START_TIMEOUT_S)

    async def open_in_main_browser(self, bot_id: str, url: str) -> None:
        """Stuck flow (Task 6): the keeper opens ``url`` in the user's own Brave.

        A refused address raises ``UrlBlocked``. An unreachable keeper or a failed
        open raises ``DeskUnavailable``. The keeper's own ``MAIN_BROWSER_OPEN_TIMEOUT_S``
        (10 s) runs out before this call's 15 s request timeout."""
        body = json.dumps({"url": url}).encode()
        await self._request(
            "POST", f"/desks/{bot_id}/main-browser/open", body=body, refused_on_bad_request=True
        )

    async def computer_input(self, bot_id: str, action: ScreenInput, held: bool) -> None:
        """One click, move, key, type or scroll on the running computer's screen. Never wakes it.

        409 ``asleep`` raises ``DeskAsleep``; 409 ``held`` / ``not_chromium`` / ``outside`` / ``in_browser`` and
        429 ``too_fast`` raise ``InputRefusedByComputer``; anything else ``DeskUnavailable`` with the status only
        (never the body, which could echo what was typed)."""
        await self._input_post(bot_id, input_body(action, held=held), input_timeout_s(action), action.verb)

    async def computer_ask(self, bot_id: str, verb: str, *, app: str = "", held: bool = False) -> dict[str, Any]:
        """``front``, ``browsers`` or ``open <app>`` on the running computer (full computer). Never wakes it."""
        action: dict[str, Any] = {"verb": verb, **({"app": app} if verb == "open" else {})}
        return await self._input_post(bot_id, {"action": action, "held": held}, _CONTROL_REQUEST_TIMEOUT_S, verb)

    async def _input_post(self, bot_id: str, payload: dict[str, Any], timeout: float, verb: str) -> dict[str, Any]:
        path = f"/desks/{bot_id}/computer/input"
        body = json.dumps(payload).encode()
        headers = signed_headers(self._config.keeper_secret, "POST", path, body)
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.post(f"{self._config.keeper_url}{path}", content=body, headers=headers)
        except httpx.TransportError as exc:
            raise DeskUnavailable(f"keeper unreachable at {self._config.keeper_url}: {type(exc).__name__}") from exc
        if response.is_success:
            return _json_object(response)
        word = _input_detail(response) if response.status_code in (409, 429) else ""
        if word == _ASLEEP:
            raise DeskAsleep(f"the computer of bot {bot_id} is asleep")
        if word in _INPUT_REFUSALS:
            raise InputRefusedByComputer(word)
        raise DeskUnavailable(f"keeper returned {response.status_code} for a {verb} on bot {bot_id}")

    async def mac(
        self, route: str, payload: dict[str, Any], *, timeout: float = MAC_REQUEST_TIMEOUT_S, method: str = "POST",
    ) -> dict[str, Any]:
        """One signed Mac file request (``/mac/...``). A keeper answer with a ``{"code": ...}`` detail
        raises ``MacFsError`` (plus ``current_sha256`` for ``changed`` and ``grant_id`` for ``bad_grant``).
        An unreachable keeper, or any other non-2xx answer, raises ``DeskUnavailable``. The error text
        never carries the keeper's body: it can hold a path or a file name."""
        body = json.dumps(payload).encode()
        headers = signed_headers(self._config.keeper_secret, method, route, body)
        headers["content-type"] = "application/json"
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.request(method, f"{self._config.keeper_url}{route}", content=body, headers=headers)
        except httpx.TransportError as exc:
            raise DeskUnavailable(f"keeper unreachable at {self._config.keeper_url}: {type(exc).__name__}") from exc
        if response.is_success:
            return response.json()
        raise _mac_error(response)


def _mac_error(response: httpx.Response) -> Exception:
    """``MacFsError`` for a coded keeper refusal, else ``DeskUnavailable`` (status only)."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return MacFsError(detail["code"], current_sha256=detail.get("current_sha256"), grant_id=detail.get("grant_id"))
    return DeskUnavailable(f"keeper returned {response.status_code} for a Mac file request")


class KeeperDesk(PageKeeping):
    """The real ``Desk``: one ``KeeperClient`` plus a lazily-connected
    ``DeskBrowserPage`` for the bot's single persistent tab.

    The browser page is only connected once something actually needs it
    (``open_page``/``read_page``) — calling ``status()`` or starting the
    workspace never touches the CDP relay at all. Once connected, the
    same ``DeskBrowserPage``/``CdpClient`` pair is reused for the life of
    this ``KeeperDesk`` (itself cached by ``DeskFactory``), so the bot's
    tab really is one tab across many tool calls.
    """

    def __init__(
        self,
        config: RoostConfig,
        bot_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
        connect_page: Callable[[str, str], Awaitable[DeskBrowserPage]] = _connect_page,
        computer: ComputerKind = "mac_brave",
        busy: Callable[[], frozenset[str]] = frozenset,
        on_wait: Callable[[], Awaitable[None]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        connect_screen: Callable[[str, dict[str, str]], Awaitable[Any]] = _connect_screen,
        room_wait_s: float = COMPUTER_ROOM_WAIT_S,
        room_poll_s: float = COMPUTER_ROOM_POLL_S,
        control_mark: Callable[[], ControlMark] = _never_held,
        on_fresh: Callable[[], Awaitable[None]] | None = None,
        wake_check_after_s: float = DESK_WAKE_CHECK_AFTER_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._wake_check_after_s = wake_check_after_s
        self._clock = clock
        self._last_page_use = float("-inf")
        self._last_hung_restart = float("-inf")
        self._on_fresh = on_fresh        # Install an app: a computer created fresh gets its approved apps back
        self._bot_id = bot_id
        self._computer = computer
        self._busy = busy                # the bots that are On it: the keeper never evicts those for room
        self._on_wait = on_wait          # says "Waiting for a free computer" once per wait
        self._sleep = sleep
        self._connect_screen = connect_screen
        self._room_wait_s = room_wait_s
        self._room_poll_s = room_poll_s
        # Take control / Give it back for this bot: once you give it back, the bot's tab is the one you left in
        # front (``_follow_after_hands``), and while you hold it the guards leave your tabs alone.
        self._control_mark = control_mark
        self._seen_mark = _NOBODY_HOLDS
        self._client = KeeperClient(config, transport=transport)
        self._page: DeskBrowserPage | None = None
        self._page_lock = asyncio.Lock()         # one connection per bot: the keeper 4409s a second one
        self._guards: Any = None                 # C3: BrowserGuards while a screen loop holds the lease
        self._guarded: Any = None                # the page they are on
        self._fence: Any = None                  # the armed fence: a replacement page is guarded with it
        # Injectable so tests can exercise the "dead connection gets
        # replaced" path (below) without a real keeper/Brave on the
        # other end -- the real page builder is still `_connect_page`.
        self._connect_page = connect_page
        # Final review, finding 5: set by `retire()`. `DeskFactory.forget`
        # drops this instance from its cache on a normal retire, but a
        # turn already in flight when the bot was retired may still hold
        # (or be about to fetch) a reference to THIS SAME instance --
        # this flag is the last line of defense against that one still
        # relaunching Brave (and recreating the desk directory retire
        # just removed) for a bot that's already gone.
        self._retired = False

    async def status(self) -> DeskStatus:
        result = await self._client.get_desk(self._bot_id)
        if self._computer == "mac_brave":
            return DeskStatus(browser=result["browser"], workspace=result["workspace"])
        state = result["computer"]      # paused, stopped and absent all read as asleep
        return DeskStatus(browser="running" if state == "running" else "stopped", workspace=result["workspace"],
                          computer="linux", state=state)

    async def start_browser(self) -> DeskStatus:
        await self._start_browser_session()
        return await self.status()

    async def _start_browser_session(self) -> dict[str, Any]:
        """Start (or wake) this bot's browser and return the keeper's answer with its ``cdp_token``."""
        if self._computer == "mac_brave":
            return await self._client.start_browser(self._bot_id)
        started = await self._start_computer_when_free()
        if started.get("fresh") is True and self._on_fresh is not None:
            await self._on_fresh()       # it only schedules the reinstall: the start never waits for apt
        return started

    async def wake_if_room(self) -> bool:
        """Routine watch (owner, 2026-11-04): start or wake the Linux computer only when the keeper has room right
        now. With no room it is False at once (no "Waiting for a free computer", no wait); Mac Brave always is."""
        if self._computer == "mac_brave":
            return True
        try:
            started = await self._client.start_computer(self._bot_id, self._busy())
        except DeskBusy:
            return False
        if started.get("fresh") is True and self._on_fresh is not None:
            await self._on_fresh()
        return True

    async def _start_computer_when_free(self) -> dict[str, Any]:
        """Ask for the computer; with no room, say so once and ask again every ``room_poll_s`` until
        ``room_wait_s`` is spent, then raise ``DeskBusy`` (Design meets code 5)."""
        waited, said = 0.0, False
        while True:
            try:
                return await self._client.start_computer(self._bot_id, self._busy())
            except DeskBusy:
                if waited >= self._room_wait_s:
                    raise
            if not said and self._on_wait is not None:
                said = True
                await self._on_wait()
            await self._sleep(self._room_poll_s)
            waited += self._room_poll_s

    async def stop_browser(self) -> DeskStatus:
        if self._computer == "mac_brave":
            await self._client.stop_browser(self._bot_id)
        else:
            await self._client.stop_computer(self._bot_id)
        # Browser stop invalidates any open CDP session/tab for it.
        if self._page is not None:
            await self._page.close()
            self._page = None
        return await self.status()

    async def _ensure_page(self) -> DeskBrowserPage:
        if self._retired:
            raise DeskUnavailable(f"desk for bot {self._bot_id} has been retired")
        if self._page is not None:
            if not await self._fell_asleep():
                return self._page
            await self._drop_page(self._page)                # woken below on a fresh connection
        started = await self._start_browser_session()       # outside the lock: it may wait for a free computer
        self._last_page_use = self._clock()
        return await self._connect_once(self._relay(), started["cdp_token"])

    async def _fell_asleep(self) -> bool:
        """Owner, 2026-11-04: whether the Linux computer was paused or stopped since the cached page's last use. CDP
        sent to a paused container hangs until it times out, and the crash probe then calls a live tab dead."""
        now, last = self._clock(), self._last_page_use
        self._last_page_use = now
        if self._computer == "mac_brave" or now - last < self._wake_check_after_s:
            return False
        try:
            return (await self.status()).state != "running"
        except Exception:                                    # the keeper didn't say: keep the page, as before
            logger.warning("could not read the computer state of bot %s", self._bot_id, exc_info=True)
            return False

    async def _restart_hung(self) -> bool:
        """A hung browser (owner, 2026-11-06): stop the Linux computer (its profile stays) so the next page call
        starts it fresh. Never on Mac Brave, a retired desk, while you hold the computer, or twice within
        ``COMPUTER_HUNG_RESTART_COOLDOWN_S``."""
        now = self._clock()
        if (self._computer == "mac_brave" or self._retired or self._control_mark().held
                or now - self._last_hung_restart < COMPUTER_HUNG_RESTART_COOLDOWN_S):
            return False
        self._last_hung_restart = now
        logger.warning("the browser of bot %s stopped answering; restarting its computer", self._bot_id)
        try:
            await self._client.stop_computer(self._bot_id)
        except DeskUnavailable as exc:
            logger.warning("could not restart the computer of bot %s: %s", self._bot_id, type(exc).__name__)
            return False
        if self._page is not None:
            await self._drop_page(self._page)
        return True

    def _relay(self) -> str:
        return _relay_url(self._config.keeper_url, self._bot_id, self._computer)

    async def open_page(self, url: str) -> PageText:
        if self._computer == "mac_brave":
            return await self._call_with_reconnect(lambda page: page.open_page(url))
        # a Linux computer keeps its tabs: a site's front page already open is that tab (owner, 2026-10-27)
        return await self._call_with_reconnect(lambda page: page.open_page(url, reuse_tab=True))

    async def read_page(self) -> PageText:
        return await self._call_with_reconnect(lambda page: page.read_page())

    async def exec(self, command: str, timeout_s: int = EXEC_TIMEOUT_S) -> ExecResult:
        await self._client.start_workspace(self._bot_id)
        argv = build_shell_argv(command)
        result = await self._client.exec_workspace(self._bot_id, argv, min(timeout_s, EXEC_TIMEOUT_S))
        return ExecResult(
            exit_code=result["exit_code"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            timed_out=result["timed_out"],
            truncated=result["truncated"],
        )

    async def retire(self) -> None:
        # Mirrors stop_browser(): an open CDP connection must be closed,
        # not just dropped -- leaving it open abandons a live WebSocket
        # to the keeper's relay for however long it takes the far end
        # (a browser that's about to be killed) to notice on its own.
        if self._page is not None:
            await self._page.close()
            self._page = None
        await self._client.retire(self._bot_id)
        self._retired = True

    async def screenshot(self) -> bytes:
        """Viewing never wakes the computer (S1.8). It attaches only to a running browser
        (``/browser/attach``) and never goes through ``_ensure_page`` or ``_call_with_reconnect``,
        which POST ``/browser/start``. A dead connection is ``DeskUnavailable``; the next poll
        attaches afresh, or is told ``DeskAsleep``.

        A ``CdpReplyError`` (a CDP error reply, or the 30s send timeout) is
        NOT a dead connection -- the socket this bot's own ``open_page``/
        ``read_page`` use is still fine, only this one capture failed (e.g.
        the tab was minimized/hidden, or the viewed tab had already closed).
        Closing it here would tear down the bot's own tab over a view
        failure alone, so it's reported unavailable without touching
        ``self._page`` at all (S1.8 Fix round 1, finding 1)."""
        if self._retired:
            raise DeskUnavailable(f"desk for bot {self._bot_id} has been retired")
        page = self._page or await self._attach_page()
        try:
            return await page.capture_screenshot()
        except CdpReplyError as exc:
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc
        except DEAD_CONNECTION_ERRORS as exc:
            await self._drop_page(page)
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc

    async def current_url(self) -> str:
        """The page's address for "which account did you use?". Attaches only to a running browser (409 and a
        dead connection both give ""), so it never wakes the computer."""
        if self._retired:
            return ""
        try:
            page = self._page or await self._attach_page()
            return await page.current_url()
        except (DeskAsleep, DeskUnavailable, *DEAD_CONNECTION_ERRORS):
            return ""

    async def _attach_page(self) -> DeskBrowserPage:
        if self._page is not None:
            return self._page
        if self._computer == "mac_brave":
            attached = await self._client.attach_browser(self._bot_id)   # 409 → DeskAsleep
        else:
            attached = await self._client.attach_computer(self._bot_id)  # 409 → DeskAsleep, never wakes
        return await self._connect_once(self._relay(), attached["cdp_token"])

    async def send_input(self, action: ScreenInput, *, held: bool = False) -> None:
        """Send one input to this bot's Linux computer screen (screen pixels). Never wakes it (``DeskAsleep``);
        Mac Brave has no screen to send to (``DeskUnavailable``)."""
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer screen to send input to")
        await self._client.computer_input(self._bot_id, action, held)

    def _require_screen(self, what: str) -> None:
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer screen to {what}")

    async def front_window(self) -> FrontWindow:
        """Full computer: what is in front (Brave and its rect, or another window). Never wakes the computer."""
        self._require_screen("read")
        return front_from(await self._client.computer_ask(self._bot_id, "front"))

    async def browser_windows(self) -> tuple[tuple[int, int, int, int], ...]:
        """Full computer: the rect of every visible Brave window, for the black-out on a desktop look."""
        self._require_screen("read")
        return windows_from(await self._client.computer_ask(self._bot_id, "browsers"))

    async def open_app(self, app: str, *, held: bool = False) -> None:
        """Full computer: bring Brave up, or start one fixed app or an installed package's window."""
        self._require_screen("open an app on")
        await self._client.computer_ask(self._bot_id, "open", app=app, held=held)

    async def tabs(self) -> tuple[TabView, ...]:
        """B1: every page tab of this bot's Linux browser, its own marked."""
        self._require_screen("list the tabs of")
        return await self._call_with_reconnect(lambda page: page.tab_list())

    async def switch_tab(self, target_id: str) -> None:
        """B1: bring that tab to the front and make it the bot's tab (its armed guards move with it)."""
        self._require_screen("switch tabs on")
        await self._call_with_reconnect(lambda page: page.attach_tab(target_id))

    async def close_tab(self, target_id: str) -> CloseResult:
        """B1: close that tab; the last one goes to about:blank instead."""
        self._require_screen("close tabs on")
        return await self._call_with_reconnect(lambda page: page.close_tab(target_id))

    def page(self) -> Any:
        """C3's ``PageDriver`` over this desk's tab on a Linux computer; None on Mac Brave. Its calls use the
        bot's own tab, as ``open_page`` does."""
        if self._retired or self._computer == "mac_brave":
            return None
        return CdpPageDriver(self._page_session, self.read_page, run=self._on_page_session)

    async def arm_guards(self, fence: Any) -> None:
        """C3: arm the browser guards (the site fence, no downloads, uploads, prompts or popups) on this
        bot's tab. Linux only."""
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer browser to guard")
        await self._arm_fence(fence)

    async def clear_site_data(self, host: str) -> SiteCleared:
        """The Sign-in card: clear one site's cookies and storage in this bot's Linux Chromium. The host is
        validated before anything wakes (``BadHost``); a sleeping computer is started, since its profile keeps
        the login. Mac Brave is never touched (``DeskUnavailable``)."""
        site = valid_host(host)
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer browser to clear")
        return await self._call_with_reconnect(lambda page: page.clear_site(site))

    async def set_workspace_internet(self, on: bool) -> None:
        """A4: Internet in the workspace on or off (the keeper recreates the container; files are kept)."""
        if self._retired:
            raise DeskUnavailable(f"desk for bot {self._bot_id} has been retired")
        await self._client.set_workspace_internet(self._bot_id, on)

    async def search_page(self, url: str) -> SearchPage:
        """web_search (A3): open the search results page in the bot's own browser and read its HTML. The address
        is checked by ``open_page`` as any other."""
        page, html = await self._call_with_reconnect(lambda browser: browser.open_and_html(url))
        return SearchPage(page=page, html=html)

    async def sign_in_signals(self, host: str) -> SignInSignals:
        """The Sign-in card's I'm done (A1): the front tab's page and the host's cookie count in this bot's Linux
        Chromium. The host is validated first (``BadHost``); Mac Brave is never read (``DeskUnavailable``)."""
        site = valid_host(host)
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer browser to read")
        return await self._call_with_reconnect(lambda page: page.sign_in_signals(site))

    async def open_screen(self) -> ScreenStream:
        """Watch the computer's screen. Attaches to a running computer only: a sleeping one is
        ``DeskAsleep`` and nothing is started. Mac Brave has no screen to open."""
        if self._retired or self._computer == "mac_brave":
            raise DeskUnavailable(f"bot {self._bot_id} has no computer screen to open")
        attached = await self._client.attach_computer(self._bot_id)          # 409 -> DeskAsleep
        try:
            socket = await self._connect_screen(_vnc_url(self._config.keeper_url, self._bot_id),
                                                {_DESK_TOKEN_HEADER: attached["vnc_token"]})
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            raise DeskUnavailable(f"could not reach the computer's screen for bot {self._bot_id}") from exc
        return KeeperScreen(socket)
