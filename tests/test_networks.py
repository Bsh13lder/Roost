"""roost-egress and the per-bot internal networks: argv builders and the idempotent ensure/remove calls."""

from __future__ import annotations

import uuid

import pytest

from roost.keeper import networks
from roost.keeper.networks import EgressNetworks, NetworkError
from roost.keeper.workspaces import _RunOutcome

BOT = str(uuid.uuid4())


def _ok(out: str = "") -> _RunOutcome:
    return _RunOutcome(0, out.encode(), b"", False)


def _fail(err: str, code: int = 1) -> _RunOutcome:
    return _RunOutcome(code, b"", err.encode(), False)


class FakeRunner:
    def __init__(self, *answers: _RunOutcome | tuple[str, _RunOutcome]) -> None:
        self.calls: list[list[str]] = []
        self._by_key = {a[0]: a[1] for a in answers if isinstance(a, tuple)}

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        self.calls.append(list(argv))
        for key, outcome in self._by_key.items():
            if key in " ".join(argv):
                return outcome
        return _ok()


def _all_builders() -> list[list[str]]:
    return [
        networks.build_network_create_argv(BOT), networks.build_network_remove_argv(BOT),
        networks.build_egress_connect_argv(BOT), networks.build_egress_disconnect_argv(BOT),
        networks.build_egress_run_argv(), networks.build_out_network_create_argv(),
    ]


def test_a_bot_network_is_internal_and_labelled():
    argv = networks.build_network_create_argv(BOT)
    assert argv[:3] == ["docker", "network", "create"]
    assert "--internal" in argv
    assert argv[argv.index("--label") + 1] == f"app.roost.bot={BOT}"
    assert argv[-1] == f"roost-net-{BOT}"


def test_no_argv_publishes_a_port():
    for argv in _all_builders():
        assert not {"-p", "--publish", "-P", "--publish-all"} & set(argv)
        assert not any(a.startswith("--publish=") for a in argv)


def test_every_name_starts_with_roost():
    assert networks.network_name(BOT).startswith("roost-")
    assert networks.build_out_network_create_argv()[-1] == "roost-out"
    run = networks.build_egress_run_argv()
    assert run[run.index("--name") + 1] == "roost-egress"
    assert run[run.index("--network") + 1] == "roost-out"
    assert networks.build_egress_connect_argv(BOT)[-2:] == [f"roost-net-{BOT}", "roost-egress"]


@pytest.mark.parametrize("bad", ["", "x", "../etc", BOT.upper(), BOT + " ; rm -rf /", "1234", str(uuid.uuid1())])
def test_a_bad_bot_id_builds_no_argv(bad):
    for build in (networks.network_name, networks.build_network_create_argv, networks.build_network_remove_argv,
                  networks.build_egress_connect_argv, networks.build_egress_disconnect_argv):
        with pytest.raises(ValueError):
            build(bad)


def test_the_egress_runs_read_only_without_capabilities():
    argv = networks.build_egress_run_argv()
    assert "--read-only" in argv
    assert "--cpus" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert argv[argv.index("--user") + 1] == "10003:10003"
    assert argv[argv.index("--memory") + 1] == "128m"
    assert argv[argv.index("--pids-limit") + 1] == "64"
    assert argv[argv.index("--label") + 1] == "app.roost.part=egress"
    assert argv[-1] == "roost-egress:dev"


async def test_ensure_bot_network_creates_then_connects_the_egress():
    runner = FakeRunner()
    await EgressNetworks(runner=runner).ensure_bot_network(BOT)
    assert runner.calls == [networks.build_network_create_argv(BOT), networks.build_egress_connect_argv(BOT)]


async def test_ensure_bot_network_is_idempotent():
    runner = FakeRunner(
        ("network create", _fail(f"Error response from daemon: network with name roost-net-{BOT} already exists")),
        ("network connect", _fail("Error response from daemon: endpoint with name roost-egress already exists in network")),
    )
    await EgressNetworks(runner=runner).ensure_bot_network(BOT)
    await EgressNetworks(runner=runner).ensure_bot_network(BOT)
    assert len(runner.calls) == 4


async def test_another_docker_error_is_a_plain_sentence():
    runner = FakeRunner(("network create", _fail("Cannot connect to the Docker daemon at unix:///var/run/docker.sock")))
    with pytest.raises(NetworkError) as err:
        await EgressNetworks(runner=runner).ensure_bot_network(BOT)
    assert "Docker" in str(err.value) and "unix://" not in str(err.value)


async def test_a_timeout_is_a_network_error():
    async def slow(argv, timeout_s):
        return _RunOutcome(-1, b"", b"", True)
    with pytest.raises(NetworkError):
        await EgressNetworks(runner=slow).ensure_bot_network(BOT)


async def test_remove_disconnects_then_removes_and_not_found_is_fine():
    runner = FakeRunner(("network disconnect", _fail("Error: No such container: roost-egress")),
                        ("network rm", _fail(f"Error: No such network: roost-net-{BOT}")))
    await EgressNetworks(runner=runner).remove_bot_network(BOT)
    assert runner.calls == [networks.build_egress_disconnect_argv(BOT), networks.build_network_remove_argv(BOT)]


async def test_ensure_egress_creates_the_out_network_and_runs_the_proxy_when_missing():
    runner = FakeRunner(("container inspect", _fail("Error: No such container: roost-egress")))
    await EgressNetworks(runner=runner).ensure_egress()
    assert networks.build_out_network_create_argv() in runner.calls
    assert networks.build_egress_run_argv() in runner.calls


async def test_ensure_egress_starts_a_stopped_proxy_and_leaves_a_running_one():
    stopped = FakeRunner(("container inspect", _ok("false")))
    await EgressNetworks(runner=stopped).ensure_egress()
    assert networks.build_egress_start_argv() in stopped.calls
    assert networks.build_egress_run_argv() not in stopped.calls
    running = FakeRunner(("container inspect", _ok("true")))
    await EgressNetworks(runner=running).ensure_egress()
    assert networks.build_egress_start_argv() not in running.calls


async def test_ensure_egress_tolerates_an_existing_out_network():
    runner = FakeRunner(("network create", _fail("network with name roost-out already exists")),
                        ("container inspect", _ok("true")))
    await EgressNetworks(runner=runner).ensure_egress()
