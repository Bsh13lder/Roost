"""Unit tests for ``roost.keeper.workspaces.WorkspaceManager`` and the
keeper's workspace/retire routes — a fake docker runner records every
argv instead of ever touching a real daemon, so these never need Docker
(real-container behavior is ``tests/test_workspace_real.py``, marker
``docker``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.browsers import BraveLauncher
from roost.keeper.computers import ComputerManager
from roost.keeper.networks import EgressNetworks
from roost.keeper.workspaces import (
    ExecResult,
    WorkspaceManager,
    WorkspaceRemoveError,
    WorkspaceStartError,
    WorkspaceStopError,
    _run_docker,
    _RunOutcome,
    _container_already_gone,
    _has_leftover_process,
    _parse_list_output,
    _truncate,
    container_name,
)

_BOT_ID = "88888888-8888-4888-8888-888888888888"
_OTHER_BOT_ID = "99999999-9999-4999-8999-999999999999"
_SECRET = "k" * 32


class _FakeRunner:
    """Records every call; returns a queued result (success by default)."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self._queue: list[_RunOutcome] = []
        self._default = _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    def queue(self, outcome: _RunOutcome) -> None:
        self._queue.append(outcome)

    async def __call__(self, argv: list[str], timeout_s: float) -> _RunOutcome:
        self.calls.append((list(argv), timeout_s))
        if self._queue:
            return self._queue.pop(0)
        return self._default


def _top_outcome(extra_rows: int = 0) -> _RunOutcome:
    rows = ["PID                 COMMAND", "76058               sleep infinity"]
    rows += [f"{90000 + i}               sleep 600" for i in range(extra_rows)]
    return _RunOutcome(returncode=0, stdout="\n".join(rows).encode(), stderr=b"", timed_out=False)


async def _no_docker(argv, timeout_s):
    return _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)


def _offline_computers(config):
    """A ComputerManager whose docker calls all succeed and run nothing."""
    return ComputerManager(config, EgressNetworks(runner=_no_docker), runner=_no_docker)


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def runner() -> _FakeRunner:
    return _FakeRunner()


@pytest.fixture
def manager(config: RoostConfig, runner: _FakeRunner) -> WorkspaceManager:
    return WorkspaceManager(config, runner=runner)


# -- argv shape ---------------------------------------------------------


async def test_start_builds_the_exact_docker_run_argv(manager, runner, config):
    runner.queue(_top_outcome())  # not consumed by start(), just keeps the queue tidy
    await manager.start(_BOT_ID)

    assert len(runner.calls) == 1
    argv, _timeout = runner.calls[0]
    bind_src = config.desks_dir / _BOT_ID / "workspace"
    assert argv == [
        "docker", "run", "-d",
        "--name", f"roost-desk-{_BOT_ID}",
        "--user", "10001:10001",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", "1g",
        "--cpus", "1",
        "--pids-limit", "256",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "--tmpfs", "/home/desk:rw,size=64m,uid=10001,gid=10001",
        "--mount", f"type=bind,src={bind_src},dst=/workspace",
        "--label", f"app.roost.bot={_BOT_ID}",
        "roost-workspace:dev",
    ]


async def test_start_creates_the_bind_mount_source_dir(manager, config):
    await manager.start(_BOT_ID)
    assert (config.desks_dir / _BOT_ID / "workspace").is_dir()


async def test_container_name_uses_the_roost_desk_prefix():
    assert container_name(_BOT_ID) == f"roost-desk-{_BOT_ID}"


async def test_exec_builds_the_exact_docker_exec_argv(manager, runner):
    runner.queue(_RunOutcome(returncode=0, stdout=b"hi\n", stderr=b"", timed_out=False))
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False))  # kill -9 -1
    runner.queue(_top_outcome())  # docker top, clean

    await manager.exec(_BOT_ID, ["echo", "hi"], 30)

    exec_argv, exec_timeout = runner.calls[0]
    assert exec_argv == [
        "docker", "exec",
        "--user", "10001:10001",
        "--workdir", "/workspace",
        "--env", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"roost-desk-{_BOT_ID}",
        "echo", "hi",
    ]
    assert exec_timeout == 30.0


async def test_exec_always_reaps_with_kill_then_top(manager, runner):
    runner.queue(_RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False))
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False))  # kill -9 -1
    runner.queue(_top_outcome())  # docker top, clean

    await manager.exec(_BOT_ID, ["true"], 10)

    assert len(runner.calls) == 3
    kill_argv, _ = runner.calls[1]
    assert kill_argv == ["docker", "exec", "--user", "10001:10001", f"roost-desk-{_BOT_ID}", "kill", "-9", "-1"]
    top_argv, _ = runner.calls[2]
    assert top_argv == ["docker", "top", f"roost-desk-{_BOT_ID}", "-eo", "pid,args"]


async def test_leftover_process_after_exec_triggers_remove_and_recreate(manager, runner):
    runner.queue(_RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False))  # exec itself
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False))  # kill -9 -1
    runner.queue(_top_outcome(extra_rows=1))  # docker top: one leftover row
    runner.queue(_RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False))  # docker rm -f
    runner.queue(_RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False))  # docker run (recreate)

    await manager.exec(_BOT_ID, ["sh", "-c", "setsid -f sleep 600"], 10)

    assert len(runner.calls) == 5
    rm_argv, _ = runner.calls[3]
    assert rm_argv == ["docker", "rm", "-f", f"roost-desk-{_BOT_ID}"]
    run_argv, _ = runner.calls[4]
    assert run_argv[:3] == ["docker", "run", "-d"]
    assert manager.status(_BOT_ID) == "running"


async def test_no_leftover_process_does_not_trigger_remove(manager, runner):
    runner.queue(_RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False))
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False))
    runner.queue(_top_outcome(extra_rows=0))  # docker top: clean

    await manager.exec(_BOT_ID, ["true"], 10)

    assert len(runner.calls) == 3  # exec, kill, top -- no rm/run


async def test_stop_builds_docker_stop_argv_only_when_running(manager, runner):
    await manager.start(_BOT_ID)
    runner.calls.clear()

    await manager.stop(_BOT_ID)

    assert runner.calls == [(["docker", "stop", f"roost-desk-{_BOT_ID}"], 10.0)]
    assert manager.status(_BOT_ID) == "stopped"


async def test_stop_on_a_bot_never_started_is_a_noop(manager, runner):
    await manager.stop(_BOT_ID)
    assert runner.calls == []
    assert manager.status(_BOT_ID) == "absent"


async def test_remove_builds_docker_rm_force_argv(manager, runner):
    await manager.start(_BOT_ID)
    runner.calls.clear()

    await manager.remove(_BOT_ID)

    # Real-desk smoke (Task 13): `docker rm -f` gets a longer timeout
    # than the other, fast control calls (stop/start/top/kill all stay
    # at 10.0) -- see _CONTAINER_REMOVE_TIMEOUT_S's docstring.
    assert runner.calls == [(["docker", "rm", "-f", f"roost-desk-{_BOT_ID}"], 60.0)]
    assert manager.status(_BOT_ID) == "absent"


async def test_remove_timeout_is_longer_than_stops(manager, runner):
    """Future-proofs the exact values above: whatever they are, remove's
    must stay strictly longer than stop's -- removal is the operation
    real-desk smoke actually caught running long."""
    await manager.start(_BOT_ID)
    runner.calls.clear()
    await manager.stop(_BOT_ID)
    stop_timeout = runner.calls[-1][1]

    await manager.start(_BOT_ID)
    await manager.remove(_BOT_ID)
    remove_timeout = runner.calls[-1][1]

    assert remove_timeout > stop_timeout


async def test_stop_raises_workspace_stop_error_on_a_real_docker_failure(manager, runner):
    await manager.start(_BOT_ID)
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"permission denied", timed_out=False))

    with pytest.raises(WorkspaceStopError):
        await manager.stop(_BOT_ID)
    assert manager.status(_BOT_ID) == "running"  # not falsely marked stopped on a real failure


async def test_stop_treats_already_gone_container_as_success(manager, runner):
    await manager.start(_BOT_ID)
    runner.queue(_RunOutcome(
        returncode=1, stdout=b"", stderr=b"Error response from daemon: No such container: x", timed_out=False
    ))

    await manager.stop(_BOT_ID)  # does not raise
    assert manager.status(_BOT_ID) == "stopped"


async def test_remove_raises_workspace_remove_error_on_a_real_docker_failure(manager, runner):
    await manager.start(_BOT_ID)
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"permission denied", timed_out=False))

    with pytest.raises(WorkspaceRemoveError):
        await manager.remove(_BOT_ID)
    assert manager.status(_BOT_ID) == "running"  # not falsely marked absent on a real failure


async def test_remove_treats_already_gone_container_as_success(manager, runner):
    runner.queue(_RunOutcome(
        returncode=1, stdout=b"", stderr=b"Error response from daemon: No such container: x", timed_out=False
    ))

    await manager.remove(_BOT_ID)  # does not raise
    assert manager.status(_BOT_ID) == "absent"


def test_container_already_gone_true_for_no_such_container_stderr():
    assert _container_already_gone(b"Error response from daemon: No such container: roost-desk-x") is True


def test_container_already_gone_false_for_an_unrelated_docker_error():
    assert _container_already_gone(b"permission denied while trying to connect to the Docker daemon") is False


async def test_start_after_stop_restarts_the_existing_container(manager, runner):
    await manager.start(_BOT_ID)
    await manager.stop(_BOT_ID)
    runner.calls.clear()

    await manager.start(_BOT_ID)

    assert runner.calls == [(["docker", "start", f"roost-desk-{_BOT_ID}"], 10.0)]
    assert manager.status(_BOT_ID) == "running"


async def test_start_is_idempotent_while_already_running(manager, runner):
    await manager.start(_BOT_ID)
    runner.calls.clear()

    await manager.start(_BOT_ID)

    assert runner.calls == []


async def test_start_failure_raises_workspace_start_error(manager, runner):
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"no such image", timed_out=False))

    with pytest.raises(WorkspaceStartError):
        await manager.start(_BOT_ID)
    assert manager.status(_BOT_ID) == "absent"


async def test_different_bots_get_independent_state_and_names(manager, runner):
    await manager.start(_BOT_ID)
    assert manager.status(_OTHER_BOT_ID) == "absent"

    run_argv, _ = runner.calls[0]
    assert f"roost-desk-{_BOT_ID}" in run_argv
    assert f"roost-desk-{_OTHER_BOT_ID}" not in run_argv


# -- pure helpers ---------------------------------------------------------


def test_has_leftover_process_false_for_just_the_foreground_process():
    assert _has_leftover_process("PID                 COMMAND\n76058               sleep infinity") is False


def test_has_leftover_process_true_for_a_second_row():
    top = "PID                 COMMAND\n76058               sleep infinity\n76155               sleep 600"
    assert _has_leftover_process(top) is True


def test_has_leftover_process_false_for_header_only_output():
    assert _has_leftover_process("PID                 COMMAND") is False


def test_truncate_leaves_short_text_untouched():
    text, truncated = _truncate("hi\n")
    assert text == "hi\n"
    assert truncated is False


def test_truncate_keeps_first_and_last_8000_chars_with_a_cut_marker():
    text = "a" * 8000 + "b" * 2000 + "c" * 8000
    truncated_text, truncated = _truncate(text)
    assert truncated is True
    assert truncated_text.startswith("a" * 8000)
    assert truncated_text.endswith("c" * 8000)
    assert "…[cut]…" in truncated_text
    assert "b" not in truncated_text


def test_truncate_boundary_exactly_16000_chars_is_not_truncated():
    text = "x" * 16000
    _text, truncated = _truncate(text)
    assert truncated is False


# -- keeper routes ---------------------------------------------------------



def _fake_spawn(path, argv, env, *, file_actions):
    """Stands in for ``os.posix_spawn`` so no real Brave window opens."""
    return 4242


@pytest.fixture
def client(config: RoostConfig, runner: _FakeRunner) -> TestClient:
    app = create_app(config)
    app.state.launcher = BraveLauncher(config, spawner=_fake_spawn)  # never the real Brave app
    app.state.workspaces = WorkspaceManager(config, runner=runner)
    app.state.computers = _offline_computers(config)
    return TestClient(app)


def _signed_request(client: TestClient, method: str, path: str, body: bytes = b"{}"):
    headers = signed_headers(_SECRET, method, path, body)
    return client.request(method, path, headers=headers, content=body)


def test_get_desk_reports_absent_workspace_before_start(client: TestClient):
    response = _signed_request(client, "GET", f"/desks/{_BOT_ID}", body=b"")
    assert response.json() == {"browser": "stopped", "workspace": "absent", "computer": "absent"}


def test_workspace_start_then_status_then_stop_route(client: TestClient):
    start_resp = _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    assert start_resp.status_code == 200
    assert start_resp.json() == {"workspace": "running"}

    status_resp = _signed_request(client, "GET", f"/desks/{_BOT_ID}", body=b"")
    assert status_resp.json()["workspace"] == "running"

    stop_resp = _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json() == {"workspace": "stopped"}


def test_workspace_exec_route_returns_exec_result_shape(client: TestClient, runner: _FakeRunner):
    runner.queue(_RunOutcome(returncode=0, stdout=b"hi\n", stderr=b"", timed_out=False))
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"", timed_out=False))
    runner.queue(_top_outcome())

    response = _signed_request(
        client, "POST", f"/desks/{_BOT_ID}/workspace/exec", body=b'{"argv": ["echo", "hi"], "timeout_s": 30}'
    )

    assert response.status_code == 200
    assert response.json() == {
        "exit_code": 0,
        "stdout": "hi\n",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
    }


@pytest.mark.parametrize("extra_field", ["user", "privileged", "env", "workdir"])
def test_workspace_exec_rejects_extra_fields_422(client: TestClient, extra_field: str):
    body = f'{{"argv": ["true"], "timeout_s": 10, "{extra_field}": "x"}}'.encode()
    response = _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/exec", body=body)
    assert response.status_code == 422


@pytest.mark.parametrize("bad_timeout", [0, 121])
def test_workspace_exec_rejects_out_of_range_timeout_422(client: TestClient, bad_timeout: int):
    body = f'{{"argv": ["true"], "timeout_s": {bad_timeout}}}'.encode()
    response = _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/exec", body=body)
    assert response.status_code == 422


def test_workspace_exec_rejects_empty_argv_422(client: TestClient):
    body = b'{"argv": [], "timeout_s": 10}'
    response = _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/exec", body=body)
    assert response.status_code == 422


def test_workspace_start_failure_is_a_clean_500(config: RoostConfig):
    class _FailingRunner:
        async def __call__(self, argv, timeout_s):
            return _RunOutcome(returncode=1, stdout=b"", stderr=b"boom", timed_out=False)

    app = create_app(config)
    app.state.workspaces = WorkspaceManager(config, runner=_FailingRunner())
    app.state.computers = _offline_computers(config)
    failing_client = TestClient(app)

    response = _signed_request(failing_client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    assert response.status_code == 500


def test_workspace_stop_failure_is_a_clean_500(config: RoostConfig):
    class _FailStopAfterStartRunner:
        """Succeeds on the start call (so state becomes "running"), then
        fails every call after that -- i.e. the ``docker stop`` triggered
        by the route under test."""

        def __init__(self) -> None:
            self._calls = 0

        async def __call__(self, argv, timeout_s):
            self._calls += 1
            if self._calls == 1:
                return _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)
            return _RunOutcome(returncode=1, stdout=b"", stderr=b"boom", timed_out=False)

    app = create_app(config)
    app.state.workspaces = WorkspaceManager(config, runner=_FailStopAfterStartRunner())
    app.state.computers = _offline_computers(config)
    failing_client = TestClient(app)

    _signed_request(failing_client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    response = _signed_request(failing_client, "POST", f"/desks/{_BOT_ID}/workspace/stop")
    assert response.status_code == 500


def test_delete_desk_failure_is_a_clean_500_and_keeps_the_desk_dir(config: RoostConfig):
    class _FailRemoveRunner:
        """Succeeds on every call except ``docker rm -f`` (the one
        ``remove()`` issues), so the desk's workspace container is
        reported as still there."""

        async def __call__(self, argv, timeout_s):
            if argv[:2] == ["docker", "rm"]:
                return _RunOutcome(returncode=1, stdout=b"", stderr=b"boom", timed_out=False)
            return _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    app = create_app(config)
    app.state.workspaces = WorkspaceManager(config, runner=_FailRemoveRunner())
    app.state.computers = _offline_computers(config)
    failing_client = TestClient(app)

    _signed_request(failing_client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    desk_path = config.desks_dir / _BOT_ID
    assert desk_path.exists()

    response = _signed_request(failing_client, "DELETE", f"/desks/{_BOT_ID}")

    assert response.status_code == 500
    assert desk_path.exists()  # not deleted -- a leaked container must keep its workspace files


def test_delete_desk_retires_both_browser_and_workspace(client: TestClient, config: RoostConfig):
    _signed_request(client, "POST", f"/desks/{_BOT_ID}/browser/start")
    _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    desk_path = config.desks_dir / _BOT_ID
    assert desk_path.exists()

    response = _signed_request(client, "DELETE", f"/desks/{_BOT_ID}")

    assert response.status_code == 200
    assert response.json() == {"retired": True}
    assert not desk_path.exists()

    status_resp = _signed_request(client, "GET", f"/desks/{_BOT_ID}", body=b"")
    body = status_resp.json()
    assert body["browser"] == "stopped"
    assert body["workspace"] == "absent"


def test_delete_desk_retries_a_transiently_locked_dir_removal(
    client: TestClient, config: RoostConfig, monkeypatch
):
    """Real-desk smoke (Task 13) caught this: a Brave helper process it
    itself spawned (the crashpad handler, observed in practice) can still
    hold a file inside the profile dir open for a brief moment after the
    main browser process has already exited and been reaped -- the first
    ``shutil.rmtree`` can land in that window and (since it runs with
    ``ignore_errors=True``) silently leave the directory partially
    behind. Simulates exactly that: the first attempt removes nothing,
    the second (real) attempt succeeds."""
    import shutil as shutil_module

    _signed_request(client, "POST", f"/desks/{_BOT_ID}/workspace/start")
    desk_path = config.desks_dir / _BOT_ID
    assert desk_path.exists()

    real_rmtree = shutil_module.rmtree
    calls = {"n": 0}

    def flaky_rmtree(path, ignore_errors=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return  # as if every removal inside the tree failed and was swallowed
        real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(shutil_module, "rmtree", flaky_rmtree)

    response = _signed_request(client, "DELETE", f"/desks/{_BOT_ID}")

    assert response.status_code == 200
    assert response.json() == {"retired": True}
    assert not desk_path.exists()
    assert calls["n"] >= 2


def test_delete_desk_on_a_bot_never_started_still_succeeds(client: TestClient):
    response = _signed_request(client, "DELETE", f"/desks/{_BOT_ID}")
    assert response.status_code == 200
    assert response.json() == {"retired": True}


def test_delete_desk_rejects_a_non_empty_body_422(client: TestClient):
    response = _signed_request(client, "DELETE", f"/desks/{_BOT_ID}", body=b'{"unexpected": 1}')
    assert response.status_code == 422


def test_delete_desk_bad_bot_id_400(client: TestClient):
    response = _signed_request(client, "DELETE", "/desks/..etc", body=b"")
    assert response.status_code == 400


# -- real subprocess helper (no docker needed -- plain system commands) --


async def test_run_docker_returns_the_process_output_on_success():
    outcome = await _run_docker(["printf", "ok"], 5.0)
    assert outcome.returncode == 0
    assert outcome.stdout == b"ok"
    assert outcome.timed_out is False


async def test_run_docker_kills_and_reports_timed_out_on_a_slow_command():
    outcome = await _run_docker(["sleep", "5"], 0.1)
    assert outcome.timed_out is True
    assert outcome.returncode == -1


def test_exec_result_is_a_frozen_dataclass():
    result = ExecResult(exit_code=0, stdout="x", stderr="", timed_out=False, truncated=False)
    with pytest.raises(AttributeError):
        result.exit_code = 1  # type: ignore[misc]


# -- reconciliation with Docker's real state (controller decision, Task 9) --
#
# Docker containers outlive the keeper process; `WorkspaceManager`'s
# in-memory `_state` dict does not. Without reconciling against Docker's
# own ground truth on startup, GET /desks/{id} would report a bot's
# workspace as "absent" after a keeper restart even though its container
# is still there (running or stopped) -- exactly the gap the brief's
# controller decision flags. `reconcile()` closes it; `manager.py`'s own
# per-call state stays untouched (and untested here) for a bot it has
# never lost track of.


def _ps_outcome(rows: list[tuple[str, str]]) -> _RunOutcome:
    lines = [f"{name}\t{state}" for name, state in rows]
    return _RunOutcome(returncode=0, stdout="\n".join(lines).encode(), stderr=b"", timed_out=False)


def test_parse_list_output_maps_names_to_running_or_stopped():
    stdout = f"roost-desk-{_BOT_ID}\trunning\nroost-desk-{_OTHER_BOT_ID}\texited\n"
    assert _parse_list_output(stdout) == {_BOT_ID: "running", _OTHER_BOT_ID: "stopped"}


def test_parse_list_output_ignores_blank_lines_and_unrelated_names():
    stdout = f"\nroost-desk-{_BOT_ID}\tcreated\nsome-other-container\trunning\n"
    assert _parse_list_output(stdout) == {_BOT_ID: "stopped"}


def test_parse_list_output_empty_is_empty():
    assert _parse_list_output("") == {}


async def test_reconcile_restores_running_state_from_docker(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_ps_outcome([(f"roost-desk-{_BOT_ID}", "running")]))
    manager = WorkspaceManager(config, runner=runner)

    assert manager.status(_BOT_ID) == "absent"  # before reconciling: no memory of this bot at all

    await manager.reconcile()

    assert manager.status(_BOT_ID) == "running"


async def test_reconcile_restores_stopped_state_from_docker(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_ps_outcome([(f"roost-desk-{_BOT_ID}", "exited")]))
    manager = WorkspaceManager(config, runner=runner)

    await manager.reconcile()

    assert manager.status(_BOT_ID) == "stopped"


async def test_reconcile_leaves_an_unknown_bot_absent(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_ps_outcome([]))
    manager = WorkspaceManager(config, runner=runner)

    await manager.reconcile()

    assert manager.status(_BOT_ID) == "absent"


async def test_reconcile_issues_a_single_docker_ps_call(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_ps_outcome([]))
    manager = WorkspaceManager(config, runner=runner)

    await manager.reconcile()

    assert len(runner.calls) == 1
    argv, _timeout = runner.calls[0]
    assert argv[:2] == ["docker", "ps"]


async def test_reconcile_tolerates_docker_being_unreachable(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_RunOutcome(returncode=1, stdout=b"", stderr=b"Cannot connect to the Docker daemon", timed_out=False))
    manager = WorkspaceManager(config, runner=runner)

    await manager.reconcile()  # must not raise

    assert manager.status(_BOT_ID) == "absent"


async def test_reconcile_restored_state_lets_start_reuse_the_existing_container(
    config: RoostConfig, runner: _FakeRunner
):
    """The real-world payoff: after reconciling a "stopped" container
    from Docker, `start()` must issue `docker start` (reuse), never
    `docker run` (which `docker` itself would refuse -- the name is
    already taken by the container reconcile just discovered)."""
    runner.queue(_ps_outcome([(f"roost-desk-{_BOT_ID}", "exited")]))
    manager = WorkspaceManager(config, runner=runner)
    await manager.reconcile()
    runner.calls.clear()

    await manager.start(_BOT_ID)

    assert runner.calls == [(["docker", "start", f"roost-desk-{_BOT_ID}"], 10.0)]


def test_keeper_app_reconciles_workspace_state_on_startup(config: RoostConfig, runner: _FakeRunner):
    runner.queue(_ps_outcome([(f"roost-desk-{_BOT_ID}", "running")]))
    app = create_app(config)
    app.state.workspaces = WorkspaceManager(config, runner=runner)
    app.state.computers = _offline_computers(config)

    # Only a lifespan-aware `with TestClient(app) as c:` actually runs
    # startup -- a bare `TestClient(app)` (used by every other test in
    # this file) never does, matching the gateway's own documented
    # TestClient caveat (roost/gateway/app.py).
    with TestClient(app) as client:
        response = _signed_request(client, "GET", f"/desks/{_BOT_ID}", body=b"")
        assert response.json() == {"browser": "stopped", "workspace": "running", "computer": "absent"}
