"""ComputerManager against a fake docker runner: which argv runs, in which order."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from roost.config import RoostConfig
from roost.keeper import computers
from roost.keeper.computers import ComputerManager, ComputerStartError
from roost.keeper.workspaces import _RunOutcome

BOT = str(uuid.uuid4())
SECCOMP = Path("/opt/roost/chromium.json")


def _ok(out: str = "") -> _RunOutcome:
    return _RunOutcome(0, out.encode(), b"", False)


def _fail(err: str = "boom") -> _RunOutcome:
    return _RunOutcome(1, b"", err.encode(), False)


class FakeRunner:
    def __init__(self, *, probe_ok_after: int = 0, probe_error: str = "no socket") -> None:
        self.calls: list[list[str]] = []
        self._probe_error = probe_error
        self.answers: dict[str, _RunOutcome] = {}
        self._probe_ok_after = probe_ok_after
        self._probes = 0

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["docker", "exec"] and "-i" not in argv:      # the boot probe
            self._probes += 1
            return _ok() if self._probes > self._probe_ok_after else _fail(self._probe_error)
        text = " ".join(argv)
        for key, outcome in self.answers.items():
            if key in text:
                return outcome
        return _ok()

    def verbs(self) -> list[str]:
        return [" ".join(c[1:3]) for c in self.calls]


class FakeNetworks:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def ensure_egress(self) -> None:
        self.log.append("ensure_egress")

    async def ensure_bot_network(self, bot_id: str) -> None:
        self.log.append(f"ensure_net {bot_id}")

    async def remove_bot_network(self, bot_id: str) -> None:
        self.log.append(f"remove_net {bot_id}")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _manager(tmp_path, runner, clock=None):
    clock = clock or Clock()
    log: list[str] = []
    config = RoostConfig(server_secret="s" * 32, database_dir=tmp_path, desks_dir=tmp_path / "desks",
                         keeper_secret="k" * 32)
    mgr = ComputerManager(config, FakeNetworks(log), runner=runner, clock=clock, sleep=clock.sleep,
                          seccomp_path=SECCOMP)
    return mgr, log, clock


async def test_start_runs_an_absent_computer_after_its_network(tmp_path):
    runner = FakeRunner()
    mgr, log, _ = _manager(tmp_path, runner)
    handle = await mgr.start(BOT)
    assert log == ["ensure_egress", f"ensure_net {BOT}"]
    assert runner.calls[0] == computers.build_run_argv(BOT, SECCOMP)
    assert mgr.state(BOT) == "running"
    assert handle.bot_id == BOT and handle.cdp_token and handle.vnc_token and handle.cdp_token != handle.vnc_token
    assert mgr.handle(BOT) == handle


async def test_start_unpauses_a_paused_one(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    await mgr.pause(BOT)
    assert mgr.state(BOT) == "paused" and mgr.handle(BOT) is None
    runner.calls.clear()
    await mgr.start(BOT)
    assert computers.build_unpause_argv(BOT) in runner.calls
    assert not any(c[:2] == ["docker", "run"] for c in runner.calls)
    assert mgr.state(BOT) == "running"


async def test_start_starts_a_stopped_one(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    await mgr.stop(BOT)
    assert mgr.state(BOT) == "stopped"
    runner.calls.clear()
    await mgr.start(BOT)
    assert computers.build_start_existing_argv(BOT) in runner.calls
    assert not any(c[:2] == ["docker", "run"] for c in runner.calls)


async def test_start_of_a_running_one_runs_nothing_but_the_probe(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    runner.calls.clear()
    await mgr.start(BOT)
    assert all(c[:2] == ["docker", "exec"] for c in runner.calls)


async def test_start_fails_cleanly_when_it_never_boots(tmp_path):
    runner = FakeRunner(probe_ok_after=10_000)
    mgr, _, clock = _manager(tmp_path, runner)
    with pytest.raises(ComputerStartError) as caught:
        await mgr.start(BOT)
    assert "did not start" in str(caught.value)
    assert clock.now - 1000.0 >= 20
    assert mgr.handle(BOT) is None


async def test_a_failed_docker_run_is_a_plain_start_error(tmp_path):
    runner = FakeRunner()
    runner.answers["docker run"] = _fail("secret detail")
    mgr, _, _ = _manager(tmp_path, runner)
    with pytest.raises(ComputerStartError) as caught:
        await mgr.start(BOT)
    assert "secret detail" not in str(caught.value)


async def test_tokens_stay_the_same_while_running_and_change_after_stop(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    first = await mgr.start(BOT)
    await mgr.pause(BOT)
    assert (await mgr.start(BOT)) == first
    await mgr.stop(BOT)
    assert mgr.handle(BOT) is None
    second = await mgr.start(BOT)
    assert second.cdp_token != first.cdp_token and second.vnc_token != first.vnc_token


async def test_stop_of_a_gone_container_is_fine_but_a_real_failure_raises(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    runner.answers["docker stop"] = _fail("Error: No such container: x")
    await mgr.stop(BOT)
    assert mgr.state(BOT) == "stopped"
    await mgr.start(BOT)
    runner.answers["docker stop"] = _fail("permission denied")
    with pytest.raises(computers.ComputerControlError):
        await mgr.stop(BOT)


async def test_remove_deletes_container_volume_and_network(tmp_path):
    runner = FakeRunner()
    mgr, log, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    runner.calls.clear()
    log.clear()
    await mgr.remove(BOT)
    assert runner.calls == [computers.build_remove_argv(BOT), computers.build_volume_remove_argv(BOT)]
    assert log == [f"remove_net {BOT}"]
    assert mgr.state(BOT) == "absent" and mgr.handle(BOT) is None


async def test_remove_tolerates_no_such_but_raises_on_a_real_failure(tmp_path):
    runner = FakeRunner()
    runner.answers["docker rm"] = _fail("Error: No such container")
    runner.answers["docker volume rm"] = _fail("Error: No such volume")
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.remove(BOT)
    runner.answers["docker volume rm"] = _fail("volume is in use")
    with pytest.raises(computers.ComputerControlError):
        await mgr.remove(BOT)


async def test_reconcile_reads_existing_computers(tmp_path):
    other = str(uuid.uuid4())
    runner = FakeRunner()
    runner.answers["docker ps"] = _ok(f"roost-computer-{BOT}\trunning\nroost-computer-{other}\tpaused\n")
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.reconcile()
    assert mgr.state(BOT) == "running" and mgr.state(other) == "paused"
    assert mgr.state(str(uuid.uuid4())) == "absent"
    assert runner.calls[0] == computers.build_list_argv()
    # tokens are minted per process: a computer found at boot has none until the next start
    assert mgr.handle(BOT) is None


async def test_reconcile_never_raises_when_docker_is_down(tmp_path):
    runner = FakeRunner()
    runner.answers["docker ps"] = _fail("Cannot connect")
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.reconcile()
    assert mgr.state(BOT) == "absent"


async def test_touch_and_last_used(tmp_path):
    runner = FakeRunner()
    mgr, _, clock = _manager(tmp_path, runner)
    assert mgr.last_used(BOT) is None
    await mgr.start(BOT)
    assert mgr.last_used(BOT) == clock.now
    clock.now += 50
    mgr.touch(BOT)
    assert mgr.last_used(BOT) == clock.now


async def test_a_vnc_ticket_is_one_time_and_expires(tmp_path):
    mgr, _, clock = _manager(tmp_path, FakeRunner())
    await mgr.start(BOT)
    first, second = mgr.mint_vnc_ticket(BOT), mgr.mint_vnc_ticket(BOT)
    assert first != second
    assert mgr.consume_vnc_ticket(BOT, first) is True
    assert mgr.consume_vnc_ticket(BOT, first) is False
    clock.now += 3600
    assert mgr.consume_vnc_ticket(BOT, second) is False


async def test_a_ticket_for_another_bot_is_refused(tmp_path):
    mgr, _, _ = _manager(tmp_path, FakeRunner())
    await mgr.start(BOT)
    ticket = mgr.mint_vnc_ticket(BOT)
    assert mgr.consume_vnc_ticket("someone-else", ticket) is False


async def test_start_rechecks_docker_and_runs_a_computer_removed_behind_its_back(tmp_path):
    runner = FakeRunner(probe_ok_after=1, probe_error="Error response from daemon: No such container")
    runner.answers["docker ps"] = _ok(f"roost-computer-{BOT}\trunning\n")
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.reconcile()
    runner.answers["docker ps"] = _ok("")            # removed by hand after the keeper started
    await mgr.start(BOT)
    assert computers.build_run_argv(BOT, SECCOMP) in runner.calls
    assert mgr.state(BOT) == "running"


async def test_a_missing_container_fails_fast_instead_of_waiting_out_the_boot_time(tmp_path):
    runner = FakeRunner(probe_ok_after=10_000, probe_error="No such container")
    mgr, _, clock = _manager(tmp_path, runner)
    with pytest.raises(ComputerStartError):
        await mgr.start(BOT)
    assert clock.now == 1000.0



async def test_a_stopped_computer_removed_by_hand_is_run_fresh(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    await mgr.stop(BOT)
    runner.answers["docker start"] = _fail("Error response from daemon: No such container: x")
    runner.calls.clear()
    await mgr.start(BOT)
    assert computers.build_run_argv(BOT, SECCOMP) in runner.calls
    assert mgr.state(BOT) == "running"


async def test_pausing_a_computer_removed_by_hand_marks_it_absent(tmp_path):
    runner = FakeRunner()
    mgr, _, _ = _manager(tmp_path, runner)
    await mgr.start(BOT)
    runner.answers["docker pause"] = _fail("Error response from daemon: No such container: x")
    await mgr.pause(BOT)
    assert mgr.state(BOT) == "absent" and mgr.handle(BOT) is None
