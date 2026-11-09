"""EgressNetworks against a real Docker daemon. Docker only; the default run skips it. Needs `make egress-image`."""

from __future__ import annotations

import json
import subprocess
import uuid

import pytest

from roost.keeper.networks import EgressNetworks, network_name

pytestmark = pytest.mark.docker


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


async def test_a_bot_network_is_internal_and_the_egress_joins_it_and_leaves_cleanly():
    bot = str(uuid.uuid4())
    nets = EgressNetworks()
    try:
        await nets.ensure_egress()
        await nets.ensure_bot_network(bot)
        await nets.ensure_bot_network(bot)   # again: a no-op
        info = json.loads(_docker("network", "inspect", network_name(bot)).stdout)[0]
        assert info["Internal"] is True
        assert info["Labels"]["app.roost.bot"] == bot
        assert any(c["Name"] == "roost-egress" for c in info["Containers"].values())
        egress = json.loads(_docker("inspect", "roost-egress").stdout)[0]
        assert egress["HostConfig"]["PortBindings"] in ({}, None)
        assert egress["HostConfig"]["ReadonlyRootfs"] is True
    finally:
        await nets.remove_bot_network(bot)
        await nets.remove_bot_network(bot)   # gone already: fine
    assert _docker("network", "inspect", network_name(bot)).returncode != 0
