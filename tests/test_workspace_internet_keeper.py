"""Internet in the workspace, keeper side (owner, 2026-10-23, A4).

Off (the default): the workspace container has no network, exactly as before. On: it runs on the bot's own
``roost-net-<id>`` network (internal: its only way out is ``roost-egress``, which refuses private ranges and
Roost's ports) with HTTP(S)_PROXY pointing there. Switching recreates the container; the files live in the bind
mount and stay. The keeper remembers the switch (and reads it back from the container's label after a restart)."""

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
    WorkspaceManager, WorkspaceStartError, _build_run_argv, _parse_internet, _parse_list_output, _RunOutcome,
)

_BOT_ID = "88888888-8888-4888-8888-888888888888"
_OTHER_BOT_ID = "99999999-9999-4999-8999-999999999999"
_SECRET = "k" * 32
_PROXY = "http://roost-egress:3128"


class _Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail_on: str | None = None

    async def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        failed = self.fail_on is not None and self.fail_on in argv
        return _RunOutcome(returncode=1 if failed else 0, stdout=b"", stderr=b"boom" if failed else b"",
                           timed_out=False)


class _Networks:
    def __init__(self) -> None:
        self.ensured: list[str] = []
        self.fail = False

    async def ensure_egress(self) -> None:
        if self.fail:
            from roost.keeper.networks import NetworkError
            raise NetworkError("no docker")
        self.ensured.append("egress")

    async def ensure_bot_network(self, bot_id: str) -> None:
        self.ensured.append(bot_id)


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


def test_off_is_no_network_and_no_proxy(config):
    argv = _build_run_argv(config, _BOT_ID)
    assert argv[argv.index("--network") + 1] == "none"
    assert not any("PROXY" in part or "proxy" in part for part in argv)


def test_on_is_the_bots_own_network_through_the_egress_proxy(config):
    argv = _build_run_argv(config, _BOT_ID, internet=True)
    assert argv[argv.index("--network") + 1] == f"roost-net-{_BOT_ID}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert f"{name}={_PROXY}" in argv
    assert "app.roost.internet=1" in argv
    assert "none" not in argv and argv[-1] == "roost-workspace:dev"
    assert "--cap-drop" in argv and "--read-only" in argv


async def test_switching_on_recreates_a_running_workspace_on_its_network(config):
    runner, networks = _Runner(), _Networks()
    manager = WorkspaceManager(config, runner=runner, networks=networks)
    await manager.start(_BOT_ID)
    runner.calls.clear()
    await manager.set_internet(_BOT_ID, True)
    assert runner.calls[0] == ["docker", "rm", "-f", f"roost-desk-{_BOT_ID}"]
    assert runner.calls[1][:2] == ["docker", "run"] and f"roost-net-{_BOT_ID}" in runner.calls[1]
    assert networks.ensured == ["egress", _BOT_ID]
    assert manager.status(_BOT_ID) == "running" and manager.internet(_BOT_ID) is True


async def test_switching_off_again_goes_back_to_no_network(config):
    runner = _Runner()
    manager = WorkspaceManager(config, runner=runner, networks=_Networks())
    await manager.set_internet(_BOT_ID, True)
    await manager.start(_BOT_ID)
    await manager.set_internet(_BOT_ID, False)
    assert runner.calls[-1][runner.calls[-1].index("--network") + 1] == "none"


async def test_a_workspace_not_there_is_only_remembered_and_the_same_value_does_nothing(config):
    runner, networks = _Runner(), _Networks()
    manager = WorkspaceManager(config, runner=runner, networks=networks)
    await manager.set_internet(_BOT_ID, True)
    assert runner.calls == [] and manager.status(_BOT_ID) == "absent"
    await manager.start(_BOT_ID)
    assert f"roost-net-{_BOT_ID}" in runner.calls[0] and networks.ensured == ["egress", _BOT_ID]
    runner.calls.clear()
    await manager.set_internet(_BOT_ID, True)
    assert runner.calls == []


async def test_a_stopped_workspace_is_recreated_but_left_stopped(config):
    runner = _Runner()
    manager = WorkspaceManager(config, runner=runner, networks=_Networks())
    await manager.start(_BOT_ID)
    await manager.stop(_BOT_ID)
    runner.calls.clear()
    await manager.set_internet(_BOT_ID, True)
    assert runner.calls == [["docker", "rm", "-f", f"roost-desk-{_BOT_ID}"]]
    assert manager.status(_BOT_ID) == "absent"


async def test_a_network_that_cannot_be_set_up_fails_the_start(config):
    networks = _Networks()
    networks.fail = True
    manager = WorkspaceManager(config, runner=_Runner(), networks=networks)
    await manager.set_internet(_BOT_ID, True)
    with pytest.raises(WorkspaceStartError):
        await manager.start(_BOT_ID)


async def test_without_networks_on_is_refused(config):
    manager = WorkspaceManager(config, runner=_Runner())
    await manager.set_internet(_BOT_ID, True)
    with pytest.raises(WorkspaceStartError):
        await manager.start(_BOT_ID)


def test_reconcile_reads_the_internet_label_back():
    stdout = f"roost-desk-{_BOT_ID}\trunning\t1\nroost-desk-{_OTHER_BOT_ID}\texited\t\n"
    assert _parse_internet(stdout) == frozenset({_BOT_ID})
    assert _parse_list_output(stdout) == {_BOT_ID: "running", _OTHER_BOT_ID: "stopped"}


async def test_reconcile_remembers_the_label(config):
    class Listing(_Runner):
        async def __call__(self, argv, timeout_s):
            return _RunOutcome(returncode=0, stdout=f"roost-desk-{_BOT_ID}\trunning\t1\n".encode(), stderr=b"",
                               timed_out=False)

    manager = WorkspaceManager(config, runner=Listing())
    await manager.reconcile()
    assert manager.internet(_BOT_ID) is True and manager.status(_BOT_ID) == "running"


# --- the keeper route -------------------------------------------------------------------------------------------

async def _no_docker(argv, timeout_s):
    return _RunOutcome(returncode=0, stdout=b"", stderr=b"", timed_out=False)


@pytest.fixture
def client(config):
    app = create_app(config)
    app.state.launcher = BraveLauncher(config, spawner=lambda *a, **k: 4242)
    app.state.workspaces = WorkspaceManager(config, runner=_Runner(), networks=_Networks())
    app.state.computers = ComputerManager(config, EgressNetworks(runner=_no_docker), runner=_no_docker)
    return TestClient(app)


def _signed(client, path: str, body: bytes):
    return client.request("POST", path, headers=signed_headers(_SECRET, "POST", path, body), content=body)


def test_the_route_sets_the_switch(client):
    response = _signed(client, f"/desks/{_BOT_ID}/workspace/internet", b'{"internet": true}')
    assert response.status_code == 200 and response.json() == {"internet": True}
    assert client.app.state.workspaces.internet(_BOT_ID) is True


@pytest.mark.parametrize("body", [b"{}", b'{"internet": "yes"}', b'{"internet": true, "x": 1}', b"nope"])
def test_the_route_takes_exactly_one_boolean(client, body):
    assert _signed(client, f"/desks/{_BOT_ID}/workspace/internet", body).status_code == 422


def test_the_route_refuses_a_bad_bot_id(client):
    assert _signed(client, "/desks/..etc/workspace/internet", b'{"internet": true}').status_code == 400


def test_a_docker_failure_is_a_clean_500(client):
    runner = _Runner()
    runner.fail_on = "rm"
    client.app.state.workspaces = WorkspaceManager(client.app.state.config, runner=runner, networks=_Networks())
    _signed(client, f"/desks/{_BOT_ID}/workspace/start", b"{}")
    response = _signed(client, f"/desks/{_BOT_ID}/workspace/internet", b'{"internet": true}')
    assert response.status_code == 500
