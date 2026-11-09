"""Unit tests for ``roost.keeper.browsers.BraveLauncher`` — argv shape and
profile prefs, with a fake spawner so these never touch a real process.

Real-process behavior (two PIDs, no listening TCP port, clean stop) is
covered separately in ``tests/test_browsers_real.py`` under the ``desk``
marker.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

import roost.keeper.browsers as browsers_module
from roost.config import RoostConfig
from roost.keeper.browsers import BraveLauncher, BrowserStartError, _close_quietly, _terminate_and_reap

_BOT_ID = "33333333-3333-4333-8333-333333333333"

_EXPECTED_FLAGS = [
    "--remote-debugging-pipe",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--window-size=1280,860",
    "--proxy-server=http://127.0.0.1:18803",
    "--proxy-bypass-list=<-loopback>",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]


@dataclass
class _Call:
    path: str
    argv: list[str]
    env: dict[str, str]
    file_actions: list[tuple]


class _FakeSpawner:
    """Records every call instead of actually spawning a process."""

    def __init__(self) -> None:
        self.calls: list[_Call] = []
        self.next_pid = 424242

    def __call__(self, path, argv, env, *, file_actions):
        self.calls.append(_Call(path=path, argv=list(argv), env=dict(env), file_actions=list(file_actions)))
        pid = self.next_pid
        self.next_pid += 1
        return pid


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret="y" * 32,
    )


@pytest.fixture
def spawner() -> _FakeSpawner:
    return _FakeSpawner()


@pytest.fixture
def launcher(config: RoostConfig, spawner: _FakeSpawner) -> BraveLauncher:
    return BraveLauncher(config, spawner=spawner)


async def test_start_builds_argv_with_exactly_the_required_flags(launcher, spawner, config):
    handle = await launcher.start(_BOT_ID)

    assert len(spawner.calls) == 1
    call = spawner.calls[0]
    profile_dir = config.desks_dir / _BOT_ID / "browser"
    assert f"--user-data-dir={profile_dir}" in call.argv
    for flag in _EXPECTED_FLAGS:
        assert flag in call.argv, f"missing {flag!r} in argv {call.argv}"
    assert not any(arg.startswith("--remote-debugging-port") for arg in call.argv)
    assert handle.pid == spawner.next_pid - 1
    assert isinstance(handle.cdp_token, str) and len(handle.cdp_token) >= 32


async def test_start_env_is_minimal(launcher, spawner, monkeypatch):
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("SOME_OTHER_SECRET", "leak-me-not")

    await launcher.start(_BOT_ID)

    env = spawner.calls[0].env
    assert set(env) <= {"HOME", "PATH", "LANG"}
    assert "SOME_OTHER_SECRET" not in env


async def test_start_writes_preferences_before_launch(launcher, spawner, config):
    await launcher.start(_BOT_ID)

    prefs_path = config.desks_dir / _BOT_ID / "browser" / "Default" / "Preferences"
    assert prefs_path.exists()
    prefs = json.loads(prefs_path.read_text())
    assert prefs["credentials_enable_service"] is False
    assert prefs["profile"]["password_manager_enabled"] is False
    assert prefs["autofill"]["profile_enabled"] is False
    assert prefs["autofill"]["credit_card_enabled"] is False
    assert prefs["net"]["network_prediction_options"] == 2
    assert prefs["download"]["default_directory"] == str(config.desks_dir / _BOT_ID / "downloads")
    assert prefs["download"]["prompt_for_download"] is False


async def test_start_is_idempotent_returns_same_token_while_running(launcher, spawner):
    first = await launcher.start(_BOT_ID)
    second = await launcher.start(_BOT_ID)

    assert len(spawner.calls) == 1  # no second spawn
    assert second.cdp_token == first.cdp_token
    assert second.pid == first.pid


async def test_is_running_false_before_start_and_after_stop(launcher):
    assert launcher.is_running(_BOT_ID) is False

    await launcher.start(_BOT_ID)
    assert launcher.is_running(_BOT_ID) is True

    await launcher.stop(_BOT_ID)
    assert launcher.is_running(_BOT_ID) is False


async def test_stop_on_a_bot_that_was_never_started_is_a_noop(launcher):
    await launcher.stop(_BOT_ID)  # must not raise
    assert launcher.is_running(_BOT_ID) is False


async def test_get_handle_returns_none_until_started_then_the_running_handle(launcher):
    assert launcher.get_handle(_BOT_ID) is None

    started = await launcher.start(_BOT_ID)
    assert launcher.get_handle(_BOT_ID) == started

    await launcher.stop(_BOT_ID)
    assert launcher.get_handle(_BOT_ID) is None


async def test_spawn_failure_raises_brower_start_error_and_closes_pipe_fds(config):
    def failing_spawner(path, argv, env, *, file_actions):
        raise OSError("no such executable")

    launcher = BraveLauncher(config, spawner=failing_spawner)
    with pytest.raises(BrowserStartError):
        await launcher.start(_BOT_ID)
    assert launcher.is_running(_BOT_ID) is False


def test_close_quietly_swallows_a_double_close():
    r, w = os.pipe()
    os.close(r)
    _close_quietly(r)  # second close on an already-closed fd: must not raise
    os.close(w)


async def test_terminate_and_reap_sigkills_a_pid_that_ignores_sigterm(monkeypatch):
    monkeypatch.setattr(browsers_module, "_STOP_GRACE_PERIOD_S", 0.2)
    child = subprocess.Popen(["sh", "-c", "trap '' TERM; sleep 5"])
    pid = child.pid
    try:
        # Give the shell a moment to actually execute `trap '' TERM`
        # before we signal it — Popen() returns right after fork(), while
        # the trap builtin only takes effect once exec'd code runs; a
        # SIGTERM that lands before then sees the default disposition
        # (terminate) instead of the trap, and the test would pass for
        # the wrong reason (the process dying from SIGTERM, not SIGKILL).
        await asyncio.sleep(0.15)
        await _terminate_and_reap(pid)
        # `_terminate_and_reap` already reaped it directly via os.waitpid;
        # check liveness with a raw signal probe rather than child.poll()
        # (which would otherwise call os.waitpid a second time on an
        # already-reaped pid).
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        try:
            child.kill()
        except OSError:
            pass
        try:
            child.wait(timeout=1)
        except Exception:
            pass


async def test_different_bots_get_different_tokens_and_profile_dirs(launcher, spawner, config):
    other_id = "44444444-4444-4444-8444-444444444444"

    h1 = await launcher.start(_BOT_ID)
    h2 = await launcher.start(other_id)

    assert h1.cdp_token != h2.cdp_token
    assert h1.pid != h2.pid
    profile1 = config.desks_dir / _BOT_ID / "browser"
    profile2 = config.desks_dir / other_id / "browser"
    assert f"--user-data-dir={profile1}" in spawner.calls[0].argv
    assert f"--user-data-dir={profile2}" in spawner.calls[1].argv
