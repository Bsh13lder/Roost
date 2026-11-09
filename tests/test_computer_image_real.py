"""The built roost-computer image, really run. Docker only; the default run skips it.

Needs `make computer-image` first. It starts one throwaway container named roost-computer-test-*, with the
same hardening the keeper uses (Task 4 owns the real argv; this mirrors it) and removes it at the end.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

IMAGE = os.environ.get("ROOST_TEST_COMPUTER_IMAGE", "roost-computer:dev")   # a candidate tag, before deploy
SECCOMP = Path(__file__).resolve().parents[1] / "roost" / "keeper" / "seccomp" / "chromium.json"


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


@pytest.fixture
def computer():
    name = f"roost-computer-test-{uuid.uuid4().hex[:8]}"
    net = f"roost-net-test-{uuid.uuid4().hex[:8]}"
    volume = f"roost-profile-test-{uuid.uuid4().hex[:8]}"   # the profile survives a stop, with its Singleton files
    assert _docker("network", "create", "--internal", net).returncode == 0
    run = _docker(
        "run", "-d", "--name", name, "--network", net, "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--security-opt", f"seccomp={SECCOMP}",
        "--tmpfs", "/tmp:rw,size=256m",
        "--tmpfs", "/run/screen:rw,mode=0700,uid=10002,gid=10002",
        "--tmpfs", "/home/comp:rw,mode=0700,uid=10002,gid=10002,size=256m", "--shm-size", "512m", "--memory", "1500m", "--pids-limit", "512",
        "-v", f"{volume}:/home/comp/profile", "--user", "10002:10002", IMAGE)
    assert run.returncode == 0, run.stderr
    try:
        yield name
    finally:
        _docker("rm", "-f", name)
        _docker("network", "rm", net)
        _docker("volume", "rm", volume)


def _wait_for_cdp(name: str) -> bool:
    for _ in range(40):
        probe = _docker("exec", "--user", "10002:10002", name, "test", "-S", "/run/screen/cdp.sock")
        if probe.returncode == 0:
            return True
        time.sleep(0.5)
    return False


def test_chromium_is_up_with_its_sandbox_and_names_do_not_resolve(computer):
    assert _wait_for_cdp(computer)
    logs = _docker("logs", computer)
    assert "No usable sandbox" not in logs.stdout + logs.stderr
    assert _docker("exec", computer, "getent", "hosts", "example.com").returncode != 0


def test_stop_and_start_boots_again_with_the_stale_files_cleared(computer):
    assert _wait_for_cdp(computer)
    assert _docker("stop", "-t", "5", computer).returncode == 0
    assert _docker("start", computer).returncode == 0
    assert _wait_for_cdp(computer)


def test_the_browser_window_is_braves_with_the_class_roost_input_matches(computer):
    assert _wait_for_cdp(computer)
    for _ in range(40):
        found = _docker("exec", "-e", "DISPLAY=:1", computer, "xdotool", "search", "--class", "^brave-browser$")
        if found.returncode == 0 and found.stdout.strip():
            return
        time.sleep(0.5)
    pytest.fail("no Brave-browser window on the computer's screen")
