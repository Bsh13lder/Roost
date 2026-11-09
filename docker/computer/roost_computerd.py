#!/usr/bin/python3
"""roost-computerd: the computer's small supervisor. Standard library only.

It starts Xvnc (on a Unix socket, no TCP) and JWM: an empty desktop. Brave, a Chromium build (DevTools over a pipe
on fds 3 and 4), starts only when something wants it (owner decision 2026-10-23, D5): the first DevTools bytes on
/run/screen/cdp.sock (`roost-pipe cdp`; the keeper's silent boot probe starts nothing), or a connection to
/run/screen/want.sock (`roost-pipe want`, from the Browser shortcut, Super+B and roost-input's `open browser`).
The cdp socket has one client at a time, the newest replaces the older, bytes copied both ways unchanged. When
Brave quits (its last window closed) it is not started again until the next want; a crash loop is cut off by a
small budget. Each start drops the last session's restore files and marks a clean exit, so Brave opens exactly
one window, never the old ones. If Xvnc dies the container ends, because nothing here can show a screen without
it. Its log lines say only which program started or stopped: never a URL, a key, a pointer move or any screen byte.
"""

from __future__ import annotations

import fcntl
import glob
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Callable
from urllib.parse import urlsplit

WIDTH, HEIGHT = 1280, 800
DISPLAY = 1
HOME = "/home/comp"
PROFILE = f"{HOME}/profile"
SCREEN_DIR = "/run/screen"
VNC_SOCKET = f"{SCREEN_DIR}/vnc.sock"
CDP_SOCKET = f"{SCREEN_DIR}/cdp.sock"
WANT_SOCKET = f"{SCREEN_DIR}/want.sock"
# The last session's restore files: Brave would reopen every old window from them.
SESSION_DIR = "Sessions"
SESSION_FILES = ("Current Session", "Current Tabs", "Last Session", "Last Tabs")
PROXY = "http://roost-egress:3128"
RESTART_LIMIT, RESTART_WINDOW_S = 5, 60.0
XVNC_WAIT_S = 10.0
POLL_S = 0.5
CHUNK = 65536
BROWSER = "brave-browser"            # Brave Browser (owner decision 2026-10-22), a Chromium build
SINGLETON_NAMES = ("SingletonLock", "SingletonSocket", "SingletonCookie")


def xvnc_argv(width: int, height: int, socket_path: str) -> list[str]:
    return [
        "Xvnc", f":{DISPLAY}", "-geometry", f"{width}x{height}", "-depth", "24",
        "-rfbport", "-1", "-rfbunixpath", socket_path, "-rfbunixmode", "0600",
        "-SecurityTypes", "None", "-AlwaysShared", "-nolisten", "tcp",
        "-SendCutText=0", "-SendPrimary=0", "-AcceptSetDesktopSize=0",
        "-s", "0",            # never blank: a viewer sends no input, and X goes black after 10 idle minutes
    ]


def chromium_argv(profile_dir: str, proxy: str) -> list[str]:
    proxy_host = urlsplit(proxy).hostname or ""
    return [
        BROWSER,
        "--remote-debugging-pipe",
        # The DevTools pipe alone turns Blink's AutomationControlled on, so navigator.webdriver reads true and
        # Google refuses sign-in; this keeps it false. Never --enable-automation or --headless.
        "--disable-blink-features=AutomationControlled",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-crash-restore-bubble",   # a computer started fresh after a crash shows no "Restore pages?" bubble
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        f"--window-size={WIDTH},{HEIGHT}",
        "--start-maximized",
        "--disk-cache-dir=/tmp/browser-cache",
        f"--proxy-server={proxy}",
        "--proxy-bypass-list=<-loopback>",
        f"--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE {proxy_host}",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "about:blank",
    ]


def stale_files(home: str, display: int) -> tuple[str, ...]:
    """Files a stopped container leaves behind that would stop the next start."""
    profile = os.path.join(home, "profile")
    singleton = tuple(os.path.join(profile, name) for name in SINGLETON_NAMES)
    present = tuple(path for path in sorted(glob.glob(os.path.join(profile, "Singleton*"))) if path not in singleton)
    return (f"/tmp/.X{display}-lock", f"/tmp/.X11-unix/X{display}", VNC_SOCKET, CDP_SOCKET, WANT_SOCKET,
            *singleton, *present)


class RestartBudget:
    """At most ``limit`` restarts in any ``window_s`` seconds: a crash loop is not a thing to keep feeding."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float]) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._stamps: deque[float] = deque()

    def allow(self) -> bool:
        now = self._clock()
        while self._stamps and now - self._stamps[0] >= self._window_s:
            self._stamps.popleft()
        if len(self._stamps) >= self._limit:
            return False
        self._stamps.append(now)
        return True


def log(line: str) -> None:
    sys.stderr.write(f"roost-computerd: {line}\n")
    sys.stderr.flush()


class CdpBridge:
    """Chromium's pipe on one side, at most one socket client on the other. A client's first bytes while no
    Chromium runs call ``want`` (which starts one and attaches its pipe); a no closes that client."""

    def __init__(self, path: str, want: Callable[[], bool] = lambda: False) -> None:
        self._path = path
        self._want = want
        self._lock = threading.Lock()
        self._client: socket.socket | None = None
        self._to_chrome: int | None = None

    def attach(self, to_chrome: int, from_chrome: int) -> None:
        with self._lock:
            self._to_chrome = to_chrome
        threading.Thread(target=self._chrome_to_client, args=(from_chrome,), daemon=True).start()

    def detach(self) -> None:
        with self._lock:
            fd, self._to_chrome = self._to_chrome, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def drop_client(self) -> None:
        """Close the current client (Chromium went away), so the gateway reconnects instead of talking to nothing."""
        with self._lock:
            conn, self._client = self._client, None
        if conn is not None:
            _close_quietly(conn)

    def serve(self) -> None:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self._path)
        os.chmod(self._path, 0o600)
        server.listen(2)
        threading.Thread(target=self._accept_loop, args=(server,), daemon=True).start()

    def _accept_loop(self, server: socket.socket) -> None:
        while True:
            conn, _ = server.accept()
            with self._lock:
                older, self._client = self._client, conn
            if older is not None:
                _close_quietly(older)
            threading.Thread(target=self._client_to_chrome, args=(conn,), daemon=True).start()

    def _client_to_chrome(self, conn: socket.socket) -> None:
        try:
            while True:
                data = conn.recv(CHUNK)
                if not data:
                    break
                with self._lock:
                    current, fd = self._client is conn, self._to_chrome
                if not current:
                    continue
                if fd is None:
                    fd = self._chrome_for_client()
                    if fd is None:
                        break
                os.write(fd, data)
        except OSError:
            pass
        finally:
            with self._lock:
                if self._client is conn:
                    self._client = None
            _close_quietly(conn)

    def _chrome_for_client(self) -> int | None:
        """A client spoke while no Chromium runs: want one (outside the lock: starting attaches its pipe)."""
        if not self._want():
            return None
        with self._lock:
            return self._to_chrome

    def _chrome_to_client(self, from_chrome: int) -> None:
        try:
            while True:
                data = os.read(from_chrome, CHUNK)
                if not data:
                    return
                with self._lock:
                    conn = self._client
                if conn is not None:
                    try:
                        conn.sendall(data)
                    except OSError:
                        pass
        except OSError:
            return
        finally:
            os.close(from_chrome)


def _close_quietly(conn: socket.socket) -> None:
    try:
        conn.close()
    except OSError:
        pass


def _above(fd: int) -> int:
    return fcntl.fcntl(fd, fcntl.F_DUPFD, 10)


def popen_with_fds_3_and_4(argv: list[str], child_in: int, child_out: int, **kwargs) -> subprocess.Popen:
    """Start argv with child_in as fd 3 and child_out as fd 4.

    pass_fds would close fds 3 and 4 again after the preexec dup2 (it only keeps the numbers it is given), so
    this uses close_fds=False: Python's own fds are close-on-exec, and the two sources are closed in the child.
    """
    def to_fds_3_and_4() -> None:
        os.dup2(child_in, 3)
        os.dup2(child_out, 4)
        os.close(child_in)
        os.close(child_out)

    return subprocess.Popen(argv, close_fds=False, preexec_fn=to_fds_3_and_4, **kwargs)


def _update_preferences(profile_dir: str, change: Callable[[dict], dict], what: str) -> None:
    """Rewrite Chromium's Preferences through ``change``, keeping every other key (atomic). A file Chromium
    can't read is left alone."""
    path = os.path.join(profile_dir, "Default", "Preferences")
    try:
        with open(path, encoding="utf-8") as fh:
            prefs = json.load(fh)
    except FileNotFoundError:
        prefs = {}
    except (OSError, ValueError):
        log(f"preferences unreadable; {what} left as is")
        return
    if not isinstance(prefs, dict):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".roost-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(change(prefs), fh)
    os.replace(tmp, path)


def _section(prefs: dict, key: str) -> dict:
    value = prefs.get(key)
    return value if isinstance(value, dict) else {}


def use_system_title_bar(profile_dir: str) -> None:
    """Chromium draws its own frame by default, which the desktop can't minimize or maximize. Ask it for the
    desktop's title bar instead, keeping every other preference."""
    _update_preferences(
        profile_dir,
        lambda prefs: {**prefs, "browser": {**_section(prefs, "browser"), "custom_chrome_frame": False}},
        "title bar",
    )


def mark_clean_exit(profile_dir: str) -> None:
    """The last run ended cleanly as far as Brave knows, so it neither offers nor does a restore."""
    _update_preferences(
        profile_dir,
        lambda prefs: {**prefs, "profile": {**_section(prefs, "profile"), "exit_type": "Normal",
                                            "exited_cleanly": True}},
        "exit state",
    )


def drop_last_session(profile_dir: str) -> None:
    """Remove the last session's restore files (never cookies or logins), so Brave opens one fresh window."""
    default = os.path.join(profile_dir, "Default")
    paths = [*glob.glob(os.path.join(default, SESSION_DIR, "*")),
             *(os.path.join(default, name) for name in SESSION_FILES)]
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError:
            log("a session file could not be removed")


def fresh_profile(profile_dir: str) -> None:
    """Before each start: the desktop's title bar, no old windows, no restore offer."""
    for step in (use_system_title_bar, drop_last_session, mark_clean_exit):
        try:
            step(profile_dir)
        except OSError:
            log(f"could not prepare the profile ({step.__name__})")


def start_chromium(bridge: CdpBridge) -> subprocess.Popen:
    """Chromium reads DevTools commands on fd 3 and writes answers on fd 4."""
    fresh_profile(PROFILE)
    in_r, in_w = os.pipe()
    out_r, out_w = os.pipe()
    child_in, child_out = _above(in_r), _above(out_w)
    proc = popen_with_fds_3_and_4(chromium_argv(PROFILE, PROXY), child_in, child_out, stdout=subprocess.DEVNULL)
    for fd in (in_r, out_w, child_in, child_out):
        os.close(fd)
    bridge.attach(in_w, out_r)
    log("chromium started")
    return proc


class BrowserProcess:
    """Brave on demand (D5): started by ``want``, never at boot and never again just because it quit. ``reap``
    (the supervisor's poll) notices a quit and lets the bridge's client go; the budget cuts off a crash loop."""

    def __init__(self, bridge, start: Callable[[CdpBridge], subprocess.Popen], budget: RestartBudget) -> None:
        self._bridge = bridge
        self._start = start
        self._budget = budget
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def want(self) -> bool:
        """True once a Brave runs (it was running, or it was started now)."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            self._forget()
            if not self._budget.allow():
                log("chromium keeps stopping; not starting it again for now")
                return False
            try:
                self._proc = self._start(self._bridge)
            except OSError:
                log("chromium could not start")
                return False
            return True

    def reap(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is not None:
                log("chromium stopped")
                self._forget()

    def running(self) -> list[subprocess.Popen]:
        with self._lock:
            return [self._proc] if self._proc is not None else []

    def _forget(self) -> None:
        if self._proc is None:
            return
        self._proc = None
        self._bridge.detach()
        self._bridge.drop_client()


def serve_want(path: str, want: Callable[[], bool]) -> None:
    """/run/screen/want.sock: each connection wants the browser and is told "ok" or "no", then closed."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, 0o600)
    server.listen(4)

    def answer(conn: socket.socket) -> None:
        try:
            conn.sendall(b"ok\n" if want() else b"no\n")
        except OSError:
            pass
        finally:
            _close_quietly(conn)

    def loop() -> None:
        while True:
            conn, _ = server.accept()
            threading.Thread(target=answer, args=(conn,), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()


def start_xvnc() -> subprocess.Popen:
    proc = subprocess.Popen(xvnc_argv(WIDTH, HEIGHT, VNC_SOCKET), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + XVNC_WAIT_S
    while not os.path.exists(VNC_SOCKET):
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("xvnc did not start")
        time.sleep(0.1)
    log("xvnc started")
    return proc


def _stop(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def supervise() -> int:
    """Xvnc and JWM now; Brave when wanted (D5)."""
    os.environ.update(DISPLAY=f":{DISPLAY}", HOME=HOME)
    browser: BrowserProcess | None = None
    bridge = CdpBridge(CDP_SOCKET, want=lambda: browser is not None and browser.want())
    browser = BrowserProcess(bridge, start_chromium, RestartBudget(RESTART_LIMIT, RESTART_WINDOW_S, time.monotonic))
    try:
        xvnc = start_xvnc()
    except RuntimeError:
        log("xvnc stopped")
        return 1
    jwm = subprocess.Popen(["jwm"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("jwm started")
    bridge.serve()
    serve_want(WANT_SOCKET, browser.want)
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    code = 0
    while not stopping.is_set():
        time.sleep(POLL_S)
        if xvnc.poll() is not None:
            log("xvnc stopped")
            code = 1
            break
        browser.reap()
    _stop([*browser.running(), jwm, xvnc])
    return code


if __name__ == "__main__":
    sys.exit(supervise())
