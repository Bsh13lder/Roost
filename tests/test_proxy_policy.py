"""Table-driven tests for ``roost.keeper.proxy.is_blocked_address`` — the
pure policy function the egress proxy consults for every resolved
address before it is allowed to dial out (Task 7 brief, Review Focus
#3: a bot's browser must never reach the home network).

Every address below is taken verbatim from the brief's table so the
contract and the test stay in lockstep.
"""

from __future__ import annotations

import ipaddress

import pytest

from roost.keeper.proxy import is_blocked_address

_ORDINARY_PORT = 443

# Loopback, RFC1918 private, link-local (incl. the cloud-metadata
# address), CGNAT shared space (RFC 6598), unspecified, multicast, and
# their IPv6 counterparts -- plus an IPv4-mapped IPv6 literal wrapping a
# private IPv4 address, which must be unwrapped and checked, not waved
# through because the outer address "looks" like a routable IPv6 one.
_BLOCKED_ADDRESSES = [
    "127.0.0.1",
    "10.0.0.5",
    "172.16.3.1",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "0.0.0.0",
    "224.0.0.1",
    "::1",
    "fe80::1",
    "fc00::1",
    "::ffff:192.168.1.1",
]

_ALLOWED_ADDRESSES = [
    "93.184.215.14",
    "2606:2800:21f:cb07:6820:80da:af6b:8b2c",
]

# Every one of Roost's own and LazyClaw's ports, plus the Brave CDP and
# Ollama ports -- blocked on ANY address, public or not, so a bot's
# browser can never reach back into the host's own listeners.
_SENSITIVE_PORTS = [9222, 11434, 18789, 18790, 18791, 18800, 18801, 18802, 18803, 18804]


@pytest.mark.parametrize("address", _BLOCKED_ADDRESSES)
def test_blocked_address_is_blocked_on_an_ordinary_port(address: str) -> None:
    ip = ipaddress.ip_address(address)
    assert is_blocked_address(ip, _ORDINARY_PORT) is True


@pytest.mark.parametrize("address", _ALLOWED_ADDRESSES)
def test_allowed_address_is_not_blocked_on_an_ordinary_port(address: str) -> None:
    ip = ipaddress.ip_address(address)
    assert is_blocked_address(ip, _ORDINARY_PORT) is False


@pytest.mark.parametrize("port", _SENSITIVE_PORTS)
def test_sensitive_port_is_blocked_even_on_a_public_address(port: int) -> None:
    ip = ipaddress.ip_address(_ALLOWED_ADDRESSES[0])
    assert is_blocked_address(ip, port) is True


@pytest.mark.parametrize("port", _SENSITIVE_PORTS)
def test_sensitive_port_is_blocked_on_a_public_ipv6_address(port: int) -> None:
    ip = ipaddress.ip_address(_ALLOWED_ADDRESSES[1])
    assert is_blocked_address(ip, port) is True


def test_allowed_address_on_a_non_sensitive_high_port_is_not_blocked() -> None:
    ip = ipaddress.ip_address(_ALLOWED_ADDRESSES[0])
    assert is_blocked_address(ip, 8080) is False
