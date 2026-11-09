#!/usr/bin/python3
"""roost-input <verb> <ints>: one click, move, key, type or scroll on the computer's screen, or a question about it.

The keeper runs this with `docker exec -i --user 10002:10002 roost-computer-<id> /usr/local/bin/roost-input`.
It is the second check on the input path (C3 design meets code 6): it parses the argv again, finds the one
Chromium window whose place and size match the bot's window as the desk read it over CDP (``--window``), makes
it the active one (raising it when it is minimized or covered, refusing when it won't come up, when no window
matches or when two do), checks that a point falls inside it, then runs xdotool argv lists with no shell, all
within one deadline that gives typing time for its length. Text to type arrives only on stdin, never in the argv. On any refusal or failure it
prints one fixed word to stderr and nothing else: never the text, the keysym or the coordinates.

    click X Y [1|2]   move X Y   key KEYSYM   type (text on stdin)   scroll X Y NOTCHES (-10..10, not 0;
    negative scrolls up), each followed by --window LEFT TOP WIDTH HEIGHT

Full computer (Step 1): ``front`` prints ``brave L T W H`` when Brave's window is the active one, else ``other``
(never a title or a class: a title can carry page text); ``browsers`` prints the rect of every visible Brave
window, one per line; ``open <app>`` raises Brave (``browser``) or starts one fixed app (``files``, ``terminal``,
``images``) or an installed package's first ``.desktop`` entry, detached with ``setsid -f``, as an argv with no
shell. ``<verb> <ints> --screen`` acts anywhere on the screen except in Brave: the point must not fall inside a
visible Brave window and Brave must not be the active window (``in_browser``).

Exit codes: 0 done, 2 bad arguments, 3 refused (not_chromium / outside / in_browser / no_window), 4 input failed.
Standard library only (Debian's python3); xdotool is Debian's package (BSD-3), unmodified.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import re
import shlex
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, replace
from typing import BinaryIO, Callable, Mapping, Sequence

VERBS = ("click", "move", "key", "type", "scroll")
QUERY_VERBS = ("front", "browsers", "open")
# The xdotool keysyms of roost.constants.CU_KEYS (a test keeps the two equal). No modifiers, ever.
KEYSYMS = frozenset({
    "Return", "Tab", "ISO_Left_Tab", "Escape", "BackSpace", "Delete", "Up", "Down", "Left", "Right",
    "Page_Up", "Page_Down", "Home", "End", "space", "XF86Back",
})
XDOTOOL = "/usr/bin/xdotool"
SCREEN_W, SCREEN_H = 1280, 800          # Xvnc's screen (CU_VIEW_MAX_W x CU_VIEW_MAX_H)
MAX_TEXT_CHARS = 5000                   # CU_TYPE_MAX_CHARS
MAX_NOTCHES = 10                        # CU_SCROLL_MAX_NOTCHES
MOVE_STEPS = 8                          # CU_MOVE_STEPS
MOVE_STEP_S = 0.012                     # CU_MOVE_STEP_MS
TYPE_DELAY_MS = "35"                    # CU_TYPE_DELAY_MS
TIMEOUT_S = 10.0                        # CU_INPUT_TIMEOUT_S
TYPE_TIMEOUT_FACTOR = 2.0               # CU_TYPE_TIMEOUT_FACTOR
WINDOW_FLAG = "--window"
SCREEN_FLAG = "--screen"
MAX_BROWSER_WINDOWS = 16                # CU_BROWSER_WINDOWS_MAX
WINDOW_MATCH_PX = 24                    # CU_WINDOW_MATCH_PX
MAX_WINDOW_W, MAX_WINDOW_H = 2 * SCREEN_W, 2 * SCREEN_H
RAISE_TIMEOUT_S = 2.0                   # one try at bringing a Chromium window up
RAISE_TRIES = 4                         # Chromium windows tried, newest first
ENV = {"DISPLAY": ":1", "HOME": "/home/comp", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
# The browser is Brave, a Chromium build: its windows are WM_CLASS ("brave-browser (<profile>)", "Brave-browser"),
# and its hidden leader window ("brave", "Brave"). Only the class "Brave-browser" is the bot's browser.
CHROMIUM_CLASSES = frozenset({"Brave-browser", "brave-browser"})
CHROMIUM_SEARCH = "^brave-browser$"     # xdotool's search is case-insensitive
_CHROMIUM_CLASS = "Brave-browser"
_OTHER_CLASS = "other"
_WHEEL = {True: "4", False: "5"}        # button 4 scrolls up, 5 scrolls down

EXIT_OK, EXIT_BAD, EXIT_REFUSED, EXIT_FAILED = 0, 2, 3, 4
BAD_ARGUMENTS, NOT_CHROMIUM, OUTSIDE, INPUT_FAILED = "bad arguments", "not_chromium", "outside", "input failed"
IN_BROWSER, NO_WINDOW = "in_browser", "no_window"
ERROR_WORDS = (BAD_ARGUMENTS, NOT_CHROMIUM, OUTSIDE, INPUT_FAILED, IN_BROWSER, NO_WINDOW)

# open: the fixed apps (CU_OPEN_APPS), and where an installed package's windows are described.
SETSID = "/usr/bin/setsid"
DPKG = "/usr/bin/dpkg"
BROWSER_APP = "browser"
FIXED_APPS = {
    "files": ("/usr/bin/pcmanfm", "/home/comp"),
    "terminal": ("/usr/bin/lxterminal",),
    "images": ("/usr/bin/gpicview",),
}
BROWSER_ARGV = ("/usr/local/bin/roost-browser",)
APP_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]{1,62}")     # a Debian package name (CU_APP_NAME_RE)
APPLICATIONS_DIR = "/usr/share/applications/"
DESKTOP_MAX_BYTES = 64 * 1024
LAUNCH_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/games"
LAUNCH_ENV = {**ENV, "PATH": LAUNCH_PATH}
LAUNCH_TIMEOUT_S = 5.0
_FIELD_CODE = re.compile(r"%[fFuUdDnNickvm]")

Run = Callable[..., "subprocess.CompletedProcess[bytes]"]


class BadArguments(Exception):
    """The argv or the stdin text is not one of the accepted shapes (exit 2)."""


class InputRefused(Exception):
    """Exit 3; the message is a fixed word, never the text."""


@dataclass(frozen=True)
class Action:
    verb: str
    x: int = 0
    y: int = 0
    count: int = 1
    keysym: str = ""
    notches: int = 0
    window: tuple[int, int, int, int] = (0, 0, 0, 0)    # the bot's window (left, top, width, height), from the desk
    screen: bool = False                                # --screen: anywhere but Brave
    app: str = ""                                       # open: the app's id

    @property
    def point(self) -> tuple[int, int] | None:
        return (self.x, self.y) if self.verb in ("click", "move", "scroll") else None


def _int(text: str, low: int, high: int) -> int:
    """A plain decimal integer in [low, high]: no sign but a leading minus, no spaces."""
    body = text[1:] if text.startswith("-") else text
    if not body.isdigit() or not body.isascii():
        raise BadArguments
    value = int(text)
    if not low <= value <= high:
        raise BadArguments
    return value


def _point(args: Sequence[str]) -> tuple[int, int]:
    return _int(args[0], 0, SCREEN_W - 1), _int(args[1], 0, SCREEN_H - 1)


def _window(args: Sequence[str]) -> tuple[int, int, int, int]:
    return (_int(args[0], -SCREEN_W, SCREEN_W), _int(args[1], -SCREEN_H, SCREEN_H),
            _int(args[2], 1, MAX_WINDOW_W), _int(args[3], 1, MAX_WINDOW_H))


def _app(name: str) -> str:
    if name == BROWSER_APP or name in FIXED_APPS or APP_NAME.fullmatch(name):
        return name
    raise BadArguments


def parse_argv(argv: Sequence[str]) -> Action:
    """``front``, ``browsers``, ``open <app>``, ``<verb> <ints> --screen`` or
    ``<verb> <ints> --window LEFT TOP WIDTH HEIGHT``; anything else is ``BadArguments``."""
    argv = list(argv)
    if argv in (["front"], ["browsers"]):
        return Action(argv[0])
    if len(argv) == 2 and argv[0] == "open":
        return Action("open", app=_app(argv[1]))
    if argv and argv[-1] == SCREEN_FLAG:
        return replace(_parse_verb(argv[:-1]), screen=True)
    if len(argv) < 6 or argv[-5] != WINDOW_FLAG:
        raise BadArguments
    return replace(_parse_verb(argv[:-5]), window=_window(argv[-4:]))


def budget_s(text_chars: int) -> float:
    """The whole input's deadline: roost.computer_use.timing.input_budget_s, mirrored."""
    return TIMEOUT_S + text_chars * int(TYPE_DELAY_MS) / 1000 * TYPE_TIMEOUT_FACTOR


def _parse_verb(argv: Sequence[str]) -> Action:
    if not argv or argv[0] not in VERBS:
        raise BadArguments
    verb, args = argv[0], list(argv[1:])
    if verb == "click" and len(args) in (2, 3):
        x, y = _point(args)
        return Action("click", x, y, count=_int(args[2], 1, 2) if len(args) == 3 else 1)
    if verb == "move" and len(args) == 2:
        return Action("move", *_point(args))
    if verb == "key" and len(args) == 1 and args[0] in KEYSYMS:
        return Action("key", keysym=args[0])
    if verb == "type" and not args:
        return Action("type")
    if verb == "scroll" and len(args) == 3:
        notches = _int(args[2], -MAX_NOTCHES, MAX_NOTCHES)
        if notches != 0:
            return Action("scroll", *_point(args), notches=notches)
    raise BadArguments


def read_text(stdin: BinaryIO) -> str:
    """The text to type: UTF-8, 1..MAX_TEXT_CHARS characters, with no control characters (a newline or a tab
    would press Enter or Tab: those are their own, separately judged, keys)."""
    raw = stdin.read(MAX_TEXT_CHARS * 4 + 1)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BadArguments from None
    if not 1 <= len(text) <= MAX_TEXT_CHARS or any(unicodedata.category(char) == "Cc" for char in text):
        raise BadArguments
    return text


def move_path(start: tuple[int, int], end: tuple[int, int], steps: int) -> tuple[tuple[int, int], ...]:
    """``steps`` points from just after ``start`` to exactly ``end``, evenly spaced."""
    (x0, y0), (x1, y1) = start, end
    return tuple((round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)) for i in range(1, steps + 1))


def _moves(target: tuple[int, int], step: tuple[int, int] | None) -> list[list[str]]:
    """``mousemove --sync`` to the point the pointer is already on waits for a motion that never comes, so a
    point equal to the one before it (the start included) is left out."""
    path = move_path(step, target, MOVE_STEPS) if step is not None else (target,)
    points = [p for i, p in enumerate(path) if p != (path[i - 1] if i else step)]
    return [[XDOTOOL, "mousemove", "--sync", str(x), str(y)] for x, y in points]


def xdotool_argv(action: Action, step: tuple[int, int] | None = None) -> list[list[str]]:
    """The argv lists for ``action``; ``step`` is where the pointer is now (None: move straight there)."""
    if action.verb == "key":
        return [[XDOTOOL, "key", "--clearmodifiers", action.keysym]]
    if action.verb == "type":
        return [[XDOTOOL, "type", "--clearmodifiers", "--delay", TYPE_DELAY_MS, "--file", "-"]]
    moves = _moves((action.x, action.y), step)
    if action.verb == "click":
        return [*moves, [XDOTOOL, "click", "--repeat", str(action.count), "1"]]
    if action.verb == "scroll":
        return [*moves, [XDOTOOL, "click", "--repeat", str(abs(action.notches)), _WHEEL[action.notches < 0]]]
    return moves


def window_ok(window_class: str, geometry: Mapping[str, int], point: tuple[int, int] | None) -> bool:
    """Chromium's window, and the point (when there is one) inside it."""
    if window_class not in CHROMIUM_CLASSES:
        return False
    if point is None:
        return True
    left, top = geometry["X"], geometry["Y"]
    return left <= point[0] < left + geometry["WIDTH"] and top <= point[1] < top + geometry["HEIGHT"]


def _shell_values(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if value.lstrip("-").isdigit():
            found[key.strip()] = int(value)
    return found


_X_ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_IGNORE_X_ERROR = _X_ERROR_HANDLER(lambda _display, _event: 0)


def _x11_origin(window: str) -> tuple[int, int] | None:
    """The window's top-left on the screen, straight from X (``XTranslateCoordinates`` to the root). xdotool's
    getwindowgeometry adds a window manager frame's offset twice (JWM's border and title: (3, 30) reads as
    (6, 60)), so a framed Brave never matched the place CDP gives. None when X can't answer (no libX11, no
    display, a bad id): the caller keeps xdotool's numbers."""
    if not window.isdigit():
        return None
    path = ctypes.util.find_library("X11")
    if path is None:
        return None
    try:
        return _translate(ctypes.CDLL(path), int(window))
    except (OSError, AttributeError, ctypes.ArgumentError):
        return None


def _translate(lib: ctypes.CDLL, window: int) -> tuple[int, int] | None:
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XDefaultRootWindow.restype = ctypes.c_ulong
    lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
                                          ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                          ctypes.POINTER(ctypes.c_ulong)]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XSetErrorHandler.argtypes = [_X_ERROR_HANDLER]
    lib.XSetErrorHandler(_IGNORE_X_ERROR)    # Xlib's default handler exits on a vanished window
    display = lib.XOpenDisplay(ENV["DISPLAY"].encode())
    if not display:
        return None
    try:
        x, y, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        done = lib.XTranslateCoordinates(display, window, lib.XDefaultRootWindow(display), 0, 0,
                                         ctypes.byref(x), ctypes.byref(y), ctypes.byref(child))
        return (x.value, y.value) if done else None
    finally:
        lib.XCloseDisplay(display)


class _X:
    """xdotool's read and write calls, each one argv list with a timeout and no shell, all before one deadline."""

    def __init__(self, run: Run, deadline: float, clock: Callable[[], float]) -> None:
        self._run, self._deadline, self._clock = run, deadline, clock

    def call(self, argv: list[str], *, data: bytes | None = None, timeout: float = TIMEOUT_S) -> str:
        left = self._deadline - self._clock()
        if left <= 0:
            raise subprocess.TimeoutExpired(argv, 0)
        done = self._run(argv, input=data, capture_output=True, timeout=min(timeout, left), check=True, env=ENV)
        return (done.stdout or b"").decode("utf-8", "replace")

    def active(self) -> str:
        return self.call([XDOTOOL, "getactivewindow"]).strip()

    def active_or_none(self) -> str | None:
        """The active window, or None when there is none (an empty desktop: xdotool exits 1)."""
        try:
            return self.active() or None
        except subprocess.CalledProcessError:
            return None

    def chromium_windows(self, *, visible: bool = False) -> list[str]:
        """Brave's windows (``visible``: only the mapped ones, so a minimized window is left out)."""
        argv = [XDOTOOL, "search", *(["--onlyvisible"] if visible else []), "--class", CHROMIUM_SEARCH]
        try:
            listed = self.call(argv)
        except subprocess.CalledProcessError:
            return []                   # xdotool search exits 1 when nothing matches
        return [line.strip() for line in listed.splitlines() if line.strip().isdigit()]

    def rect(self, window: str) -> tuple[int, int, int, int] | None:
        found = self.geometry(window)
        if not {"X", "Y", "WIDTH", "HEIGHT"} <= set(found):
            return None
        return found["X"], found["Y"], found["WIDTH"], found["HEIGHT"]

    def launch(self, argv: Sequence[str]) -> None:
        """Start ``argv`` detached (``setsid -f``), its own session, no shell, nothing read back."""
        left = self._deadline - self._clock()
        if left <= 0:
            raise subprocess.TimeoutExpired(list(argv), 0)
        self._run([SETSID, "-f", *argv], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, timeout=min(LAUNCH_TIMEOUT_S, left), check=True, env=LAUNCH_ENV,
                  cwd=ENV["HOME"])

    def geometry(self, window: str) -> dict[str, int]:
        """xdotool's size, at the window's true place on the screen when X answers (see ``_x11_origin``)."""
        found = _shell_values(self.call([XDOTOOL, "getwindowgeometry", "--shell", window]))
        origin = _x11_origin(window)
        return found if origin is None else {**found, "X": origin[0], "Y": origin[1]}

    def pointer(self) -> tuple[int, int] | None:
        values = _shell_values(self.call([XDOTOOL, "getmouselocation", "--shell"]))
        return (values["X"], values["Y"]) if "X" in values and "Y" in values else None

    def try_raise(self, window: str) -> bool:
        try:
            self.call([XDOTOOL, "windowactivate", "--sync", window], timeout=RAISE_TIMEOUT_S)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
        return self.active() == window


def window_matches(geometry: Mapping[str, int], window: tuple[int, int, int, int]) -> bool:
    """xdotool's geometry is the desk's window, give or take ``WINDOW_MATCH_PX`` on each side."""
    if not {"X", "Y", "WIDTH", "HEIGHT"} <= set(geometry):
        return False
    seen = (geometry["X"], geometry["Y"], geometry["WIDTH"], geometry["HEIGHT"])
    return all(abs(a - b) <= WINDOW_MATCH_PX for a, b in zip(seen, window))


def _bot_window(x: _X, window: tuple[int, int, int, int]) -> str:
    """The one Chromium window that is the bot's, made the active one. None or two alike: refused."""
    matches = [w for w in x.chromium_windows() if window_matches(x.geometry(w), window)]
    if len(matches) != 1:
        raise InputRefused(NOT_CHROMIUM)
    found = matches[0]
    if x.active() != found and not x.try_raise(found):
        raise InputRefused(NOT_CHROMIUM)
    return found


def _check_window(x: _X, action: Action) -> None:
    found = _bot_window(x, action.window)
    active = x.active()
    window_class = _CHROMIUM_CLASS if active == found and active in x.chromium_windows() else _OTHER_CLASS
    geometry = x.geometry(active)
    if window_class != _CHROMIUM_CLASS or not window_matches(geometry, action.window):
        raise InputRefused(NOT_CHROMIUM)
    if not window_ok(window_class, geometry, action.point):
        raise InputRefused(OUTSIDE)


def _brave_rects(x: _X) -> list[tuple[int, int, int, int]]:
    rects = [x.rect(w) for w in x.chromium_windows(visible=True)[:MAX_BROWSER_WINDOWS]]
    return [r for r in rects if r is not None]


def _inside(point: tuple[int, int], rect: tuple[int, int, int, int]) -> bool:
    left, top, width, height = rect
    return left <= point[0] < left + width and top <= point[1] < top + height


def front_line(x: _X) -> str:
    """``brave L T W H`` when Brave's window is the active one, else ``other``. Nothing else, ever."""
    active = x.active_or_none()
    if active is None or active not in x.chromium_windows():
        return "other"
    rect = x.rect(active)
    return "other" if rect is None else "brave " + " ".join(str(v) for v in rect)


def browsers_lines(x: _X) -> str:
    return "".join(" ".join(str(v) for v in rect) + "\n" for rect in _brave_rects(x))


def _check_screen(x: _X, action: Action) -> None:
    """Anywhere but Brave: Brave is not the active window and the point is in no visible Brave window. A key or
    text with no active window is refused too: nothing can say where it would go."""
    active = x.active_or_none()
    if (active is None and action.point is None) or (active is not None and active in x.chromium_windows()):
        raise InputRefused(IN_BROWSER)
    point = action.point
    if point is not None and any(_inside(point, rect) for rect in _brave_rects(x)):
        raise InputRefused(IN_BROWSER)


Read = Callable[[str], "str | None"]
Which = Callable[[str], "str | None"]


def read_desktop(path: str) -> str | None:
    """A ``.desktop`` file's text, at most ``DESKTOP_MAX_BYTES``; None when it can't be read."""
    try:
        with open(path, "rb") as handle:
            return handle.read(DESKTOP_MAX_BYTES).decode("utf-8", "replace")
    except OSError:
        return None


def which(name: str) -> str | None:
    return shutil.which(name, path=LAUNCH_PATH)


def desktop_exec(text: str) -> list[str] | None:
    """The ``[Desktop Entry]`` group's ``Exec=`` as an argv, field codes removed; None for none, a terminal
    app or a line ``shlex`` can't split."""
    group, found, terminal = "", None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and line.startswith("Exec=") and found is None:
            found = line[len("Exec="):]
        elif group == "[Desktop Entry]" and line.replace(" ", "") == "Terminal=true":
            terminal = True
    if found is None or terminal:
        return None
    try:
        argv = [word.replace("%%", "%") for word in shlex.split(_FIELD_CODE.sub("", found))]
    except ValueError:
        return None
    return argv or None


def package_argv(x: _X, package: str, read: Read) -> list[str]:
    """The first window entry an installed package ships, or ``no_window``."""
    try:
        listed = x.call([DPKG, "-L", package])
    except subprocess.CalledProcessError:
        raise InputRefused(NO_WINDOW) from None
    for path in (line.strip() for line in listed.splitlines()):
        if path.startswith(APPLICATIONS_DIR) and path.endswith(".desktop") and "/../" not in path:
            text = read(path)
            argv = desktop_exec(text) if text is not None else None
            if argv is not None:
                return argv
    raise InputRefused(NO_WINDOW)


def _open(x: _X, app: str, read: Read, find: Which) -> None:
    if app == BROWSER_APP:
        windows = x.chromium_windows()
        if any(x.try_raise(w) for w in reversed(windows[-RAISE_TRIES:])):
            return
        argv = list(BROWSER_ARGV)
    else:
        argv = list(FIXED_APPS[app]) if app in FIXED_APPS else package_argv(x, app, read)
    program = find(argv[0])
    if program is None:
        raise InputRefused(NO_WINDOW)
    x.launch([program, *argv[1:]])


def _perform(x: _X, action: Action, text: str | None, sleep: Callable[[float], None]) -> None:
    start = x.pointer() if action.point is not None else None
    for argv in xdotool_argv(action, start):
        if argv[1] == "type":
            x.call(argv, data=(text or "").encode("utf-8"), timeout=budget_s(len(text or "")))
        else:
            x.call(argv)
        if argv[1] == "mousemove":
            sleep(MOVE_STEP_S)


def _fail(word: str, code: int) -> int:
    sys.stderr.write(word + "\n")
    return code


def _run_action(x: _X, action: Action, text: str | None, sleep: Callable[[float], None], read: Read,
                find: Which) -> None:
    if action.verb == "front":
        sys.stdout.write(front_line(x) + "\n")
    elif action.verb == "browsers":
        sys.stdout.write(browsers_lines(x))
    elif action.verb == "open":
        _open(x, action.app, read, find)
    else:
        (_check_screen if action.screen else _check_window)(x, action)
        _perform(x, action, text, sleep)


def main(argv: Sequence[str], stdin: BinaryIO, run: Run, *, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic, read: Read = read_desktop, which: Which = which) -> int:
    try:
        action = parse_argv(argv)
        text = read_text(stdin) if action.verb == "type" else None
    except BadArguments:
        return _fail(BAD_ARGUMENTS, EXIT_BAD)
    x = _X(run, clock() + budget_s(len(text or "")), clock)
    try:
        _run_action(x, action, text, sleep, read, which)
    except InputRefused as refused:
        return _fail(str(refused), EXIT_REFUSED)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError, KeyError):
        return _fail(INPUT_FAILED, EXIT_FAILED)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin.buffer, subprocess.run))
