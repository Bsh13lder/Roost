"""roost-apt in the built image, really run. Docker and the network only; the default run skips it.

It starts a throwaway egress proxy (from the roost-egress image, aliased roost-egress on a throwaway internal
network) and a throwaway computer with the keeper's own run flags (``build_run_argv``), then runs roost-apt as root
the way the keeper does. Every name is roost-*-test-*, removed at the end; the live gateway, keeper, egress and
computers are never touched. Pick the candidate image with ROOST_TEST_COMPUTER_IMAGE (e.g. roost-computer:apps)."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from roost.constants import EGRESS_IMAGE
from roost.keeper import computers

pytestmark = [pytest.mark.docker, pytest.mark.network]

IMAGE = os.environ.get("ROOST_TEST_COMPUTER_IMAGE", "roost-computer:dev")
SECCOMP = Path(__file__).resolve().parents[1] / "roost" / "keeper" / "seccomp" / "chromium.json"


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _computer_run_argv(name: str, net: str, volume: str) -> list[str]:
    """The keeper's own run argv, with only the names, the network and the image changed."""
    bot = str(uuid.uuid4())
    argv = computers.build_run_argv(bot, SECCOMP)
    swap = {computers.container_name(bot): name, f"roost-net-{bot}": net,
            f"type=volume,src={computers.profile_volume(bot)},dst=/home/comp/profile":
                f"type=volume,src={volume},dst=/home/comp/profile"}
    argv = [swap.get(a, a) for a in argv[1:]]
    return [*argv[:-1], IMAGE]


@pytest.fixture
def computer():
    tag = uuid.uuid4().hex[:8]
    name, proxy, net, volume = (f"roost-computer-test-{tag}", f"roost-egress-test-{tag}", f"roost-net-test-{tag}",
                                f"roost-profile-test-{tag}")
    assert _docker("network", "create", "--internal", net).returncode == 0
    try:
        started = _docker("run", "-d", "--name", proxy, "--read-only", "--cap-drop", "ALL",
                          "--security-opt", "no-new-privileges", EGRESS_IMAGE)
        assert started.returncode == 0, started.stderr
        assert _docker("network", "connect", "--alias", "roost-egress", net, proxy).returncode == 0
        run = _docker(*_computer_run_argv(name, net, volume))
        assert run.returncode == 0, run.stderr
        yield name
    finally:
        _docker("rm", "-f", name, proxy)
        _docker("network", "rm", net)
        _docker("volume", "rm", volume)


def _apt(name: str, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return _docker("exec", "--user", "0:0", name, "/usr/local/bin/roost-apt", *args, timeout=timeout)


def test_roost_apt_installs_and_removes_from_debian_only(computer):
    described = _apt(computer, "describe", "jq")
    assert described.returncode == 0, described.stderr
    assert "JSON" in described.stdout
    assert _apt(computer, "install", "jq").returncode == 0
    assert _docker("exec", computer, "/usr/bin/jq", "--version").returncode == 0
    assert _apt(computer, "install", "jq").stderr.strip() == "already_installed"
    assert _apt(computer, "remove", "jq").returncode == 0
    assert _apt(computer, "install", "sudo").stderr.strip() == "denied"
    assert _apt(computer, "install", "nosuchpackage-roost").stderr.strip() == "not_found"


def test_the_computers_own_user_cannot_use_apt_or_write_usr(computer):
    as_comp = _docker("exec", computer, "/usr/local/bin/roost-apt", "install", "jq", timeout=300)
    assert as_comp.returncode != 0
    assert _docker("exec", computer, "touch", "/usr/roost-test").returncode != 0
    caps = _docker("exec", computer, "grep", "CapEff", "/proc/self/status").stdout
    assert caps.split()[-1] == "0000000000000000"
