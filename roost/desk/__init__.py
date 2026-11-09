"""Desk facade — the server-side (gateway) view of a bot's browser/workspace.

``roost/desk/signing.py`` lives here because it is the one piece shared by
both sides of the keeper boundary: the gateway's keeper client signs
requests with it, and the keeper's own auth dependency
(``roost/keeper/auth.py``) verifies them with it.

This module (``__init__.py``) is the package's public surface: the
``Desk`` protocol every implementation (``KeeperDesk``, ``FakeDesk``)
satisfies, its result dataclasses, and ``DeskFactory`` — the one object
``roost/gateway/app.py`` builds and every desk route reads off
``request.app.state.desks``.

``DeskFactory.for_bot`` imports ``roost.desk.client``/``roost.desk.fake``
*inside* the method rather than at module level, on purpose: those
modules import types back from this one (``from roost.desk import
DeskStatus, ...``), and importing them here at module load time would
make that a circular import. Deferring the import to call time means
this module always finishes defining its own names first — see each
submodule (``client.py``, ``cdp.py``, ``browser.py``, ``url_policy.py``,
``fake.py``) for the rest of the facade.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from roost.config import RoostConfig
from roost.desk.control import ControlMark

if TYPE_CHECKING:
    from roost.desk.site_data import SignInSignals
    from roost.research.results import SearchPage

ComputerKind = Literal["linux", "mac_brave"]
ComputerState = Literal["running", "paused", "stopped", "absent"]
InputVerb = Literal["click", "move", "key", "type", "scroll"]
FrontKind = Literal["brave", "other"]
Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class DeskStatus:
    browser: Literal["running", "stopped"]
    workspace: Literal["running", "stopped", "absent"]
    computer: ComputerKind = "mac_brave"
    state: ComputerState | None = None      # None for Mac Brave


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool


@dataclass(frozen=True)
class PageText:
    """What the bot's browser shows. The last three fields are the stuck detector's signals
    (``roost/desk/stuck.py``); they default to "nothing seen", so every older constructor still works."""

    url: str
    title: str
    text: str
    truncated: bool
    status: int | None = None       # main document HTTP status; None when unknown (read_page)
    password_field: bool = False    # an <input type="password"> is on the page
    captcha_frame: bool = False     # a visible hCaptcha / reCAPTCHA / Turnstile frame is on the page
    # §4 crashed tab recovery: the words the tool result starts with when this read came after the bot's tab
    # crashed and was opened again (``CRASHED_TAB_RECOVERED_TEXT``); None for an ordinary read.
    notice: str | None = None


class DeskUnavailable(RuntimeError):
    """Raised by a ``Desk`` method when the keeper can't be reached at
    all (process down, connection refused, timed out) — the gateway route
    (``roost/gateway/routes/desk.py``) turns this into a clean 503
    ``{"detail": "desk unavailable"}`` rather than a raw connection
    error."""


class DeskAsleep(RuntimeError):
    """The bot's browser is closed. A screenshot never starts it (S1.8): the
    Computer tab says "<bot>'s computer is asleep · Open it" instead."""


class DeskBusy(RuntimeError):
    """No Linux computer was free after ``COMPUTER_ROOM_WAIT_S``. The tools say it in plain words."""


class InputRefusedByComputer(RuntimeError):
    """The keeper or the computer refused one screen input: ``held`` (you hold Take control), ``not_chromium``
    (Chromium's window could not be brought up), ``outside`` (the point is not in it), ``too_fast``, or, for the
    full computer, ``in_browser`` (a screen act aimed at Brave) and ``no_window`` (an app with nothing to open)."""

    def __init__(self, word: str) -> None:
        super().__init__(f"the computer refused the input: {word}")
        self.word = word


@dataclass(frozen=True)
class ScreenInput:
    """One input on a Linux computer's screen (C3), in **screen** pixels (``page_geometry.viewport_to_screen``).

    ``key`` is an xdotool keysym from ``CU_KEYS.values()``; ``text`` is only for ``type``. ``repr`` never shows
    the text, so a log line or a traceback cannot leak what is typed. ``window`` is the bot's Chromium window as
    the desk read it (``WindowGeometry.window_rect``): roost-input acts only in the window that matches, and an
    input without one is never sent (``ValueError``)."""

    verb: InputVerb
    x: int = 0
    y: int = 0
    count: int = 1
    key: str = ""
    text: str = field(default="", repr=False)
    notches: int = 0
    window: tuple[int, int, int, int] | None = None
    screen: bool = False      # full computer: anywhere on the screen but in Brave, with no window

    def require_window(self) -> tuple[int, int, int, int]:
        if self.window is None:
            raise ValueError("A screen input needs the bot's window it aims at.")
        return self.window


@dataclass(frozen=True)
class FrontWindow:
    """What is in front on a Linux computer: Brave's window (with its rect) or anything else. Never a title."""

    kind: FrontKind
    window: Rect | None = None


class ScreenStream(Protocol):
    """RFB bytes both ways between the gateway and a bot's computer screen."""

    async def send(self, data: bytes) -> None: ...
    async def receive(self) -> bytes: ...      # b"" when the far end closed
    async def close(self) -> None: ...


class Desk(Protocol):
    """One per bot — built by ``DeskFactory.for_bot``. ``KeeperDesk``
    (``roost/desk/client.py``) is the real implementation, talking to the
    keeper over signed HTTP and the CDP relay; ``FakeDesk``
    (``roost/desk/fake.py``) is the in-memory stand-in every test and
    ``ROOST_DESK=fake`` run uses instead."""

    async def status(self) -> DeskStatus: ...
    async def start_browser(self) -> DeskStatus: ...
    async def wake_if_room(self) -> bool: ...     # routine watch: wake only with room right now; never waits
    async def stop_browser(self) -> DeskStatus: ...
    async def open_page(self, url: str) -> PageText: ...
    async def search_page(self, url: str) -> SearchPage: ...          # web_search: the fixed engine's results
    async def sign_in_signals(self, host: str) -> SignInSignals: ...  # A1: does the computer look signed in?
    async def set_workspace_internet(self, on: bool) -> None: ...     # A4: recreate the workspace with or without it
    async def read_page(self) -> PageText: ...
    async def exec(self, command: str, timeout_s: int = ...) -> ExecResult: ...   # timeout_s <= EXEC_TIMEOUT_S
    async def retire(self) -> None: ...
    async def screenshot(self) -> bytes: ...
    async def open_screen(self) -> ScreenStream: ...   # never wakes: DeskAsleep / DeskUnavailable
    async def current_url(self) -> str: ...   # the bot's page address; "" when asleep or unreadable; never wakes
    async def send_input(self, action: ScreenInput, *, held: bool = False) -> None: ...  # Linux only; never wakes
    async def front_window(self) -> FrontWindow: ...          # full computer: Linux only; never wakes
    async def browser_windows(self) -> tuple[Rect, ...]: ...  # every visible Brave window; Linux only
    async def open_app(self, app: str, *, held: bool = False) -> None: ...   # Linux only; never wakes
    async def clear_site_data(self, host: str) -> Any: ...  # Sign-in card: a SiteCleared; Linux only; BadHost first
    async def tabs(self) -> Any: ...                          # B1: the browser's tabs (TabView); Linux only
    async def switch_tab(self, target_id: str) -> None: ...   # B1: bring it up, make it the bot's tab
    async def close_tab(self, target_id: str) -> Any: ...     # B1: "closed", or "blanked" for the last tab
    def page(self) -> Any: ...      # C3's PageDriver for a Linux computer (Task 6); None until then and on Mac Brave


def build_shell_argv(command: str) -> list[str]:
    """The fixed ``["/bin/sh", "-c", command]`` argv every desk ``exec``
    sends to the keeper — the only shape ``roost.keeper.workspaces``'s
    locked-down exec endpoint accepts. The user's own "run a command" and,
    since Programs, a bot's ``run_program`` and file tools
    (``roost/programs/``) both run through it, so the command runs only in
    the bot's own sealed workspace container.
    Shared by ``KeeperDesk.exec`` (which really sends it) and
    ``FakeDesk.exec`` (which records it, so a test can assert on the
    exact shape without a real keeper)."""
    return ["/bin/sh", "-c", command]


async def _no_wait_line(bot_id: str) -> None:
    return None


def _never_held(bot_id: str) -> ControlMark:
    return ControlMark(epoch=0, held=False)


async def _no_boot_hook(bot_id: str) -> None:
    return None


@dataclass(frozen=True)
class RoomHooks:
    """What the gateway tells a Linux desk about the room: which bots are On it (the keeper never evicts those)
    and how to say "Waiting for a free computer" for one bot."""

    busy: Callable[[], frozenset[str]] = frozenset
    on_wait: Callable[[str], Awaitable[None]] = _no_wait_line
    control_mark: Callable[[str], ControlMark] = _never_held   # Take control / Give it back, per bot


class DeskFactory:
    """Builds and caches one ``Desk`` per (bot id, computer kind) for the lifetime of the
    gateway app -- matching ``roost.keeper.browsers.BraveLauncher`` and
    ``roost.keeper.workspaces.WorkspaceManager``'s "one per bot id"
    pattern. Caching matters here specifically because a real ``Desk``
    (``KeeperDesk``) holds a stateful CDP connection for the bot's one
    persistent browser tab -- handing out a fresh, disconnected instance
    on every call would silently reopen that tab on every single tool
    call.
    """

    def __init__(self, config: RoostConfig) -> None:
        self._config = config
        self._desks: dict[tuple[str, ComputerKind], Desk] = {}
        self.room_hooks = RoomHooks()
        self.boot_hook: Callable[[str], Awaitable[None]] = _no_boot_hook

    def set_boot_hook(self, hook: Callable[[str], Awaitable[None]]) -> None:
        """Install an app: told about every Linux computer the keeper created fresh (its apps go back). Read live."""
        self.boot_hook = hook

    def set_room_hooks(self, hooks: RoomHooks) -> None:
        """The runner's view of the room, set once at start-up. A desk built later reads it live."""
        self.room_hooks = hooks

    def for_bot(self, bot_id: str, computer: ComputerKind = "mac_brave") -> Desk:
        key = (bot_id, computer)
        existing = self._desks.get(key)
        if existing is not None:
            return existing

        if self._config.desk_mode == "fake":
            from roost.desk.fake import FakeDesk

            desk: Desk = FakeDesk(bot_id, computer=computer)
        else:
            from roost.desk.client import KeeperDesk

            desk = KeeperDesk(
                self._config, bot_id, computer=computer,
                busy=lambda: self.room_hooks.busy(),
                on_wait=lambda: self.room_hooks.on_wait(bot_id),
                control_mark=lambda: self.room_hooks.control_mark(bot_id),
                on_fresh=lambda: self.boot_hook(bot_id),
            )

        self._desks = {**self._desks, key: desk}
        return desk

    def forget(self, bot_id: str) -> None:
        """Drop both kinds of ``bot_id``'s cached ``Desk``, if any -- called by ``delete_bot`` right
        after a desk retire, so a later ``for_bot`` call builds a fresh instance instead of reusing
        one this process already retired. A safe no-op when nothing is cached for ``bot_id``."""
        self._desks = {key: desk for key, desk in self._desks.items() if key[0] != bot_id}
