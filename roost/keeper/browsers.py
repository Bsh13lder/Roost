"""Per-bot Brave launcher — spawns Brave Browser with CDP wired to a pair
of pipes (never a TCP debug port) and a locked-down profile.

Each bot gets its own ``--user-data-dir`` under ``<desks_dir>/<bot_id>/browser``,
its own egress through the keeper's proxy (``--proxy-server``, with
``--proxy-bypass-list=<-loopback>`` so even loopback addresses are forced
through it — the home-network block lives in the proxy and the URL
policy, both later tasks; this flag is what makes Brave actually route
loopback traffic there instead of special-casing it away), and CDP framed
as UTF-8 JSON + a trailing ``\\0`` byte over two pipes instead of a
``--remote-debugging-port`` (so there is never a debug port on the host
for anything else to find or collide with).

``BraveLauncher`` takes an injectable ``spawner`` (defaulting to
``os.posix_spawn``) so unit tests (``tests/test_browsers.py``) can capture
the exact argv/env/file_actions without ever starting a real process; the
real thing is exercised separately in ``tests/test_browsers_real.py``
(marker ``desk``).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from roost.config import RoostConfig
from roost.keeper.paths import browser_dir, downloads_dir

# Chrome/Brave accepts this as a window-size string, not a tuple; stays a
# single constant so nothing downstream hardcodes "1280,860" again.
_WINDOW_SIZE = "1280,860"

# The literal Chromium proxy-bypass-list token that means "bypass nothing,
# including loopback" — the opposite of Chromium's normal default, which
# quietly exempts loopback addresses from the configured proxy.
_PROXY_BYPASS_NONE = "<-loopback>"

_CDP_TOKEN_BYTES = 32

# Env vars passed through to the child; everything else (API keys,
# session secrets, ...) is withheld on purpose — see the module docstring.
_PASSTHROUGH_ENV_VARS = ("HOME", "PATH", "LANG")

_STOP_POLL_INTERVAL_S = 0.05
_STOP_GRACE_PERIOD_S = 3.0

Spawner = Callable[..., int]


@dataclass(frozen=True)
class BrowserHandle:
    pid: int
    cdp_token: str
    read_fd: int
    write_fd: int


class BrowserStartError(RuntimeError):
    """Raised when Brave fails to spawn for a bot."""


def _build_argv(config: RoostConfig, profile_dir: Path) -> list[str]:
    return [
        config.brave_path,
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-pipe",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        f"--window-size={_WINDOW_SIZE}",
        f"--proxy-server=http://127.0.0.1:{config.proxy_port}",
        f"--proxy-bypass-list={_PROXY_BYPASS_NONE}",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]


def _build_env() -> dict[str, str]:
    return {name: os.environ[name] for name in _PASSTHROUGH_ENV_VARS if name in os.environ}


def _write_preferences(profile_dir: Path, downloads_dir: Path) -> None:
    """Write ``Default/Preferences`` before every launch (Chromium merges
    this into its real prefs on startup): password saving, address/card
    autofill and network-prediction off; downloads land in the bot's own
    downloads dir instead of the shared default."""
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs = {
        "credentials_enable_service": False,
        "credentials_enable_autosignin": False,
        "profile": {"password_manager_enabled": False},
        "autofill": {"profile_enabled": False, "credit_card_enabled": False},
        # 2 == Chromium's NETWORK_PREDICTION_NEVER.
        "net": {"network_prediction_options": 2},
        "download": {
            "default_directory": str(downloads_dir),
            "prompt_for_download": False,
        },
    }
    (default_dir / "Preferences").write_text(json.dumps(prefs))


def _spawn_file_actions(r_cmd: int, w_evt: int, log_path: Path) -> list[tuple]:
    return [
        (os.POSIX_SPAWN_DUP2, r_cmd, 3),
        (os.POSIX_SPAWN_DUP2, w_evt, 4),
        (os.POSIX_SPAWN_OPEN, 0, "/dev/null", os.O_RDONLY, 0),
        (os.POSIX_SPAWN_OPEN, 1, str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600),
        (os.POSIX_SPAWN_DUP2, 1, 2),
    ]


def _close_quietly(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


async def _terminate_and_reap(pid: int) -> None:
    """SIGTERM, wait up to ``_STOP_GRACE_PERIOD_S`` for a clean exit, then
    SIGKILL and reap. Tolerates the pid already being gone (fake-spawner
    unit tests use pids nothing ever actually started)."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = asyncio.get_event_loop().time() + _STOP_GRACE_PERIOD_S
    while asyncio.get_event_loop().time() < deadline:
        try:
            reaped_pid, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if reaped_pid == pid:
            return
        await asyncio.sleep(_STOP_POLL_INTERVAL_S)

    try:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass


class BraveLauncher:
    """One per keeper process. Tracks at most one running Brave per bot id."""

    def __init__(self, config: RoostConfig, *, spawner: Spawner | None = None) -> None:
        self._config = config
        self._spawn: Spawner = spawner if spawner is not None else os.posix_spawn
        self._handles: dict[str, BrowserHandle] = {}

    def is_running(self, bot_id: str) -> bool:
        return bot_id in self._handles

    def get_handle(self, bot_id: str) -> BrowserHandle | None:
        """The running bot's handle (for the CDP relay to attach to), or
        ``None`` if its browser isn't running."""
        return self._handles.get(bot_id)

    async def start(self, bot_id: str) -> BrowserHandle:
        """Idempotent: a bot already running gets back its existing handle
        (same pid, same ``cdp_token``) instead of a second Brave window."""
        existing = self._handles.get(bot_id)
        if existing is not None:
            return existing

        handle = self._spawn_brave(bot_id)
        self._handles[bot_id] = handle
        return handle

    def _spawn_brave(self, bot_id: str) -> BrowserHandle:
        profile_dir = browser_dir(self._config.desks_dir, bot_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        dl_dir = downloads_dir(self._config.desks_dir, bot_id)
        dl_dir.mkdir(parents=True, exist_ok=True)
        _write_preferences(profile_dir, dl_dir)

        argv = _build_argv(self._config, profile_dir)
        env = _build_env()
        log_path = profile_dir.parent / "brave.log"

        r_cmd, w_cmd = os.pipe()  # keeper writes commands -> child reads fd 3
        r_evt, w_evt = os.pipe()  # child writes events -> fd 4, keeper reads
        file_actions = _spawn_file_actions(r_cmd, w_evt, log_path)
        try:
            pid = self._spawn(self._config.brave_path, argv, env, file_actions=file_actions)
        except OSError as exc:
            for fd in (r_cmd, w_cmd, r_evt, w_evt):
                _close_quietly(fd)
            raise BrowserStartError(f"failed to spawn Brave for bot {bot_id}: {exc}") from exc

        # Spawn succeeded: the child now owns fds 3/4 (dup'd from these),
        # so the keeper's copies of the *child's* ends are closed here;
        # `read_fd`/`write_fd` below are the keeper's own ends, kept open.
        _close_quietly(r_cmd)
        _close_quietly(w_evt)

        return BrowserHandle(
            pid=pid,
            cdp_token=secrets.token_urlsafe(_CDP_TOKEN_BYTES),
            read_fd=r_evt,
            write_fd=w_cmd,
        )

    async def stop(self, bot_id: str) -> None:
        handle = self._handles.pop(bot_id, None)
        if handle is None:
            return
        _close_quietly(handle.read_fd)
        _close_quietly(handle.write_fd)
        await _terminate_and_reap(handle.pid)
