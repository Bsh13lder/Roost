"""Real-Brave integration tests for ``BraveLauncher`` (marker ``desk``).

Launches actual Brave Browser windows briefly — expected, per the Task 5
ground rules. Never touches the user's main Brave profile or port 9222:
each bot gets its own ``--user-data-dir`` under a throwaway ``tmp_path``
desks dir (never the real ``~/Roost/desks``, courtesy of the session-wide
test tripwire in ``tests/conftest.py``), and CDP goes over a pipe
(``--remote-debugging-pipe``, no ``--remote-debugging-port``) so there is
never a debug port to collide with the host bridge on 9222.

Excluded from the default test run (``addopts = "-m 'not desk ...'"`` in
pyproject.toml); run explicitly with ``uv run pytest -m desk
tests/test_browsers_real.py -q``.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from roost.config import RoostConfig
from roost.keeper.browsers import BraveLauncher

pytestmark = pytest.mark.desk

_BOT_A = "55555555-5555-4555-8555-555555555555"
_BOT_B = "66666666-6666-4666-8666-666666666666"
_START_TIMEOUT_S = 15
_STOP_TIMEOUT_S = 10


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


def _has_listening_tcp(pid: int) -> bool:
    """True if ``lsof`` reports any LISTEN-state TCP socket for ``pid``."""
    result = subprocess.run(
        ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret="y" * 32,
    )


@pytest.fixture
def launcher(config: RoostConfig) -> BraveLauncher:
    return BraveLauncher(config)


async def test_two_bots_get_two_real_brave_pids_with_no_listening_cdp_port(launcher):
    handle_a = await launcher.start(_BOT_A)
    handle_b = await launcher.start(_BOT_B)

    try:
        assert handle_a.pid != handle_b.pid
        assert _wait_until(lambda: _pid_alive(handle_a.pid), _START_TIMEOUT_S)
        assert _wait_until(lambda: _pid_alive(handle_b.pid), _START_TIMEOUT_S)

        # Give Brave a moment to finish starting up before probing sockets.
        time.sleep(1.5)
        assert not _has_listening_tcp(handle_a.pid)
        assert not _has_listening_tcp(handle_b.pid)
    finally:
        await launcher.stop(_BOT_A)
        await launcher.stop(_BOT_B)

    assert _wait_until(lambda: not _pid_alive(handle_a.pid), _STOP_TIMEOUT_S)
    assert _wait_until(lambda: not _pid_alive(handle_b.pid), _STOP_TIMEOUT_S)
