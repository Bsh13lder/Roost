"""Real-Docker integration tests for ``WorkspaceManager`` (marker
``docker``).

Builds on the real ``roost-workspace:dev`` image (``make workspace-image``
must have been run first) and starts actual containers named
``roost-desk-<uuid>`` — expected, per the Task 8 ground rules; only
``roost-*``-named containers/images are ever touched. Each test uses a
throwaway ``tmp_path`` desks dir (never the real ``~/Roost/desks``,
enforced by the session-wide test tripwire in ``tests/conftest.py``) and
always removes its container in a ``finally``.

Excluded from the default test run (``addopts = "-m 'not desk and not
docker and not network'"`` in pyproject.toml); run explicitly with
``uv run pytest -m docker tests/test_workspace_real.py -q``.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from roost.config import RoostConfig
from roost.keeper.workspaces import WorkspaceManager, container_name

pytestmark = pytest.mark.docker

_EXEC_TIMEOUT_S = 15


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret="y" * 32,
    )


@pytest.fixture
def bot_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def manager(config: RoostConfig, bot_id: str):
    mgr = WorkspaceManager(config)
    try:
        yield mgr
    finally:
        _run_sync(["docker", "rm", "-f", container_name(bot_id)])


def _run_sync(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True)


def _docker_top_rows(name: str) -> list[str]:
    result = _run_sync(["docker", "top", name, "-eo", "pid,args"])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[1:]  # drop the "PID COMMAND" header


async def test_echo_returns_exit_code_0_and_stdout(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["echo", "hi"], _EXEC_TIMEOUT_S)

    assert result.exit_code == 0
    assert result.stdout == "hi\n"
    assert result.timed_out is False


async def test_runs_as_uid_10001(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["id", "-u"], _EXEC_TIMEOUT_S)

    assert result.stdout.strip() == "10001"


async def test_no_network_curl_fails(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["curl", "-sS", "https://example.com"], _EXEC_TIMEOUT_S)

    assert result.exit_code != 0


async def test_write_lands_on_the_host_bind_mount(manager: WorkspaceManager, bot_id: str, config: RoostConfig):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["sh", "-c", "echo hello > /workspace/a.txt"], _EXEC_TIMEOUT_S)

    assert result.exit_code == 0
    host_file = config.desks_dir / bot_id / "workspace" / "a.txt"
    assert host_file.read_text() == "hello\n"


async def test_backgrounded_process_is_reaped_after_exec_returns(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["sh", "-c", "setsid -f sleep 600; echo started"], _EXEC_TIMEOUT_S)

    assert result.exit_code == 0
    assert result.stdout == "started\n"
    # The manager's own post-exec reap already ran inside exec() above;
    # this is an independent, outside-the-manager check that only the
    # container's own foreground process is left -- not the backgrounded
    # `sleep 600`.
    rows = _docker_top_rows(container_name(bot_id))
    assert len(rows) == 1
    assert "sleep" in rows[0] and "600" not in rows[0]


async def test_read_only_rootfs_blocks_writes_outside_workspace(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    result = await manager.exec(bot_id, ["sh", "-c", "echo x > /etc/should-fail"], _EXEC_TIMEOUT_S)

    assert result.exit_code != 0


async def test_stop_then_start_restarts_the_same_container(manager: WorkspaceManager, bot_id: str, config: RoostConfig):
    await manager.start(bot_id)
    await manager.exec(bot_id, ["sh", "-c", "echo persisted > /workspace/marker.txt"], _EXEC_TIMEOUT_S)

    await manager.stop(bot_id)
    assert manager.status(bot_id) == "stopped"

    await manager.start(bot_id)
    assert manager.status(bot_id) == "running"

    result = await manager.exec(bot_id, ["cat", "/workspace/marker.txt"], _EXEC_TIMEOUT_S)
    assert result.stdout == "persisted\n"


async def test_remove_deletes_the_container(manager: WorkspaceManager, bot_id: str):
    await manager.start(bot_id)

    await manager.remove(bot_id)

    inspect = _run_sync(["docker", "inspect", container_name(bot_id)])
    assert inspect.returncode != 0
