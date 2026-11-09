"""Tests for ``scripts/smoke.py``'s own resource-lifecycle contract.

Not the full real-desk run (that needs a real Brave window, real Docker
and real internet, and is deliberately never imported by pytest -- see
that module's own docstring and ``tests/conftest.py``'s tripwire). This
file covers one narrower, purely mechanical guarantee instead: a failure
partway through ``_setup()`` must never leave an already-started port
bound.

Fix round 1, finding 1: ``_setup()`` used to start the egress proxy and
the keeper's/gateway's real ``uvicorn.Server`` one at a time with no
cleanup on a partial failure -- a timed-out ``_wait_until_listening``
propagated straight out of ``_setup()``, ``main()``'s
``except SmokeFailure`` branch never got a ``_Ctx`` to call
``_teardown()`` on, and the already-bound ports/processes leaked with no
record anywhere. These tests load the real module (not a reimplementation)
and drive its real ``_setup()``/``AsyncExitStack`` plumbing -- creating a
gateway/keeper app does not itself spawn a browser or a container (those
only happen when a desk route is actually called), so this needs nothing
beyond loopback sockets.

They point the module's port globals at free ephemeral ports
(``_free_smoke_ports``) instead of the real fixed 18800/18801/18803: the
always-on stack (``make deploy`` -- the gateway container and the
launchd desk keeper) holds those real ports by design, and what's under
test here is the teardown, not the port numbers.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SMOKE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "smoke.py"


def _load_smoke_module() -> ModuleType:
    """Loads ``scripts/smoke.py`` as its own module object, fresh per
    test, under a name that can never collide with anything on
    ``sys.path`` (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("roost_smoke_under_test", _SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _free_smoke_ports(monkeypatch, smoke: ModuleType) -> None:
    """Repoint ``smoke``'s gateway/keeper/proxy port globals (read at call
    time by ``_setup()`` and ``_require_ports_free()``) at three distinct
    free ephemeral loopback ports."""
    sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM) for _ in range(3)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        gateway, keeper, proxy = (sock.getsockname()[1] for sock in sockets)
    finally:
        for sock in sockets:
            sock.close()
    monkeypatch.setattr(smoke, "GATEWAY_PORT", gateway)
    monkeypatch.setattr(smoke, "KEEPER_PORT", keeper)
    monkeypatch.setattr(smoke, "PROXY_PORT", proxy)
    monkeypatch.setattr(smoke, "_PORTS_TO_CHECK", (gateway, keeper, proxy))


@pytest.mark.parametrize(
    "failing_port_attr",
    ["KEEPER_PORT", "GATEWAY_PORT"],
    ids=["keeper-wait-times-out", "gateway-wait-times-out"],
)
async def test_setup_tears_down_already_started_resources_on_failure(monkeypatch, failing_port_attr):
    smoke = _load_smoke_module()
    _free_smoke_ports(monkeypatch, smoke)
    failing_port = getattr(smoke, failing_port_attr)

    assert _port_is_free(smoke.KEEPER_PORT), "keeper port must be free before this test starts"
    assert _port_is_free(smoke.PROXY_PORT), "proxy port must be free before this test starts"
    assert _port_is_free(smoke.GATEWAY_PORT), "gateway port must be free before this test starts"

    real_wait = smoke._wait_until_listening
    waited_ports: list[int] = []

    async def _wait_that_fails_for_one_port(host: str, port: int, timeout: float) -> None:
        waited_ports.append(port)
        if port == failing_port:
            raise smoke.SmokeFailure(f"simulated: {host}:{port} never started listening")
        await real_wait(host, port, timeout)

    monkeypatch.setattr(smoke, "_wait_until_listening", _wait_that_fails_for_one_port)

    with pytest.raises(smoke.SmokeFailure):
        await smoke._setup()

    # Proves the simulated step was actually reached (never a vacuous
    # pass because nothing was started in the first place).
    assert failing_port in waited_ports

    # The fix: whatever _setup() started before the simulated failure
    # (the proxy always; the keeper too, when the gateway is the one
    # that fails) must already be torn down by the time _setup() raises
    # -- never left bound for main() to leak.
    assert _port_is_free(smoke.KEEPER_PORT), "keeper server leaked after a failed _setup()"
    assert _port_is_free(smoke.PROXY_PORT), "egress proxy leaked after a failed _setup()"
    assert _port_is_free(smoke.GATEWAY_PORT), "gateway server was never meant to start here"


async def test_setup_removes_its_temp_dirs_on_failure(monkeypatch):
    """Same failure as above, checked from a different angle: the temp
    data/desks dirs ``_setup()`` creates up front must not survive a
    partial failure either."""
    smoke = _load_smoke_module()
    _free_smoke_ports(monkeypatch, smoke)
    created_dirs: list[Path] = []
    real_mkdtemp = smoke.tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = Path(real_mkdtemp(*args, **kwargs))
        created_dirs.append(path)
        return str(path)

    monkeypatch.setattr(smoke.tempfile, "mkdtemp", _tracking_mkdtemp)

    async def _always_fails(host: str, port: int, timeout: float) -> None:
        raise smoke.SmokeFailure(f"simulated: {host}:{port} never started listening")

    monkeypatch.setattr(smoke, "_wait_until_listening", _always_fails)

    with pytest.raises(smoke.SmokeFailure):
        await smoke._setup()

    assert len(created_dirs) == 2, "expected _setup() to create exactly the data dir and the desks dir"
    for path in created_dirs:
        assert not path.exists(), f"{path} should have been removed when _setup() failed"

    assert _port_is_free(smoke.PROXY_PORT), "egress proxy leaked after a failed _setup()"


def test_smoke_url_and_expect_default_to_example_dot_com(monkeypatch):
    """No overrides set -- the module keeps its original real-example.com
    behavior (``ROOST_SMOKE_URL``/``ROOST_SMOKE_EXPECT``, module docstring)."""
    monkeypatch.delenv("ROOST_SMOKE_URL", raising=False)
    monkeypatch.delenv("ROOST_SMOKE_EXPECT", raising=False)

    smoke = _load_smoke_module()

    assert smoke._SMOKE_URL == "https://example.com"
    assert smoke._SMOKE_EXPECT == "Example Domain"


def test_smoke_url_and_expect_are_overridable_via_env(monkeypatch):
    """Both knobs flow into the scripted turn itself, not just the
    module-level constants -- ``_build_script``'s ``open_page`` call must
    use the overridden URL, never a baked-in example.com."""
    monkeypatch.setenv("ROOST_SMOKE_URL", "https://example.org")
    monkeypatch.setenv("ROOST_SMOKE_EXPECT", "Example Org Domain")

    smoke = _load_smoke_module()

    assert smoke._SMOKE_URL == "https://example.org"
    assert smoke._SMOKE_EXPECT == "Example Org Domain"

    tool_call = smoke._build_script()[0][0]
    assert tool_call.arguments == {"url": "https://example.org"}
