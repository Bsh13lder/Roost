"""The computer container's docker argv, built by small pure functions (no docker)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from roost.keeper import computers

BOT = str(uuid.uuid4())
SECCOMP = Path("/opt/roost/chromium.json")


def test_run_argv_is_exactly_the_hardened_one():
    assert computers.build_run_argv(BOT, SECCOMP) == [
        "docker", "run", "-d", "--name", f"roost-computer-{BOT}", "--hostname", "computer",
        "--label", f"app.roost.bot={BOT}", "--network", f"roost-net-{BOT}",
        "--user", "10002:10002", "--cap-drop", "ALL",
        # Install an app: apt, run as root by the keeper only, needs these three; uid 10002 holds none of them.
        "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
        "--security-opt", "no-new-privileges", "--security-opt", f"seccomp={SECCOMP}",
        "--tmpfs", "/tmp:rw,size=256m", "--tmpfs", "/var/tmp:rw,size=64m",
        "--tmpfs", "/run/screen:rw,mode=0700,uid=10002,gid=10002,size=1m",
        "--tmpfs", "/home/comp:rw,uid=10002,gid=10002,size=64m",
        "--mount", f"type=volume,src=roost-profile-{BOT},dst=/home/comp/profile",
        "--memory", "1500m", "--memory-swap", "1500m", "--shm-size", "512m", "--cpus", "1.5",
        "--pids-limit", "512", "roost-computer:dev",
    ]


def _every_argv() -> list[list[str]]:
    return [
        computers.build_run_argv(BOT, SECCOMP), computers.build_pipe_argv(BOT, "cdp"),
        computers.build_pipe_argv(BOT, "vnc"), computers.build_probe_argv(BOT),
        computers.build_pause_argv(BOT), computers.build_unpause_argv(BOT), computers.build_stop_argv(BOT),
        computers.build_start_existing_argv(BOT), computers.build_remove_argv(BOT),
        computers.build_volume_remove_argv(BOT), computers.build_list_argv(),
    ]


def test_no_argv_publishes_a_port():
    for argv in _every_argv():
        assert not {"-p", "--publish", "-P", "--publish-all"} & set(argv)
        assert not any(a.startswith("--publish") for a in argv)


def test_never_unconfined_never_privileged_never_no_sandbox():
    for argv in _every_argv():
        text = " ".join(argv)
        for banned in ("unconfined", "--privileged", "--no-sandbox", "host.docker.internal",
                       "docker.sock", "type=bind", "SYS_ADMIN", "NET_ADMIN", "ALL --cap-add ALL"):
            assert banned not in text
        added = [argv[i + 1] for i, a in enumerate(argv) if a == "--cap-add"]
        assert added in ([], ["CHOWN", "DAC_OVERRIDE", "FOWNER"])
        assert not {"--pid", "--ipc", "--uts", "--device", "--userns"} & set(argv)
        assert "host" not in argv


def test_every_resource_is_named_roost():
    for argv in _every_argv()[:-1]:
        names = [a for a in argv if BOT in a and not a.startswith(("app.roost", "--"))]
        assert names and all(
            n.startswith(("roost-", "app.roost.bot=", "type=volume,src=roost-", "seccomp=")) for n in names)


def test_pipe_argv_execs_as_10002_and_only_cdp_or_vnc():
    for which in ("cdp", "vnc"):
        assert computers.build_pipe_argv(BOT, which) == [
            "docker", "exec", "-i", "--user", "10002:10002", f"roost-computer-{BOT}",
            "/usr/local/bin/roost-pipe", which]
    for bad in ("shell", "", "cdp; sh", "../x"):
        with pytest.raises(ValueError):
            computers.build_pipe_argv(BOT, bad)


@pytest.mark.parametrize("bad", ["", "x", "../etc", "1234", str(uuid.uuid1()), BOT + "; rm", BOT.upper() + "x"])
def test_a_bad_bot_id_builds_no_argv(bad):
    with pytest.raises(ValueError):
        computers.build_run_argv(bad, SECCOMP)
    with pytest.raises(ValueError):
        computers.build_pipe_argv(bad, "cdp")
    with pytest.raises(ValueError):
        computers.container_name(bad)
    with pytest.raises(ValueError):
        computers.build_stop_argv(bad)


def test_parse_list_output_reads_paused_and_exited():
    other = str(uuid.uuid4())
    third = str(uuid.uuid4())
    out = (
        f"roost-computer-{BOT}\trunning\n"
        f"roost-computer-{other}\tpaused\n"
        f"roost-computer-{third}\texited\n"
        "roost-computer-test-abc\trunning\n"
        "roost-desk-zzz\trunning\n"
        "garbage\n"
    )
    assert computers.parse_list_output(out) == {BOT: "running", other: "paused", third: "stopped"}


def test_the_seccomp_profile_ships_with_the_package():
    assert computers.DEFAULT_SECCOMP_PATH.is_file()
