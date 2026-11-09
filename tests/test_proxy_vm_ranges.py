"""The egress proxy lives inside the VM, so Docker's and the VM's own ranges must be refused too:
no computer reaches another computer, the gateway or the keeper through it."""

from __future__ import annotations

import ipaddress

import pytest

from roost.keeper.proxy import is_blocked_address


@pytest.mark.parametrize("address", [
    "172.16.0.1", "172.17.0.2", "172.18.0.5", "172.31.255.254",   # Docker bridges and per-bot networks
    "192.168.65.1", "192.168.65.2", "192.168.65.254",             # the VM; .254 is host.docker.internal
    "10.0.0.1", "10.255.255.254",
    "fd00::1", "fd12:3456::1", "::ffff:172.17.0.2", "::ffff:192.168.65.254",
    "127.0.0.1", "::1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
])
@pytest.mark.parametrize("port", [80, 443, 3128])
def test_private_and_vm_addresses_are_refused(address, port):
    assert is_blocked_address(ipaddress.ip_address(address), port)


@pytest.mark.parametrize("address", ["93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed_on_web_ports(address):
    assert not is_blocked_address(ipaddress.ip_address(address), 443)
