"""Connectors: the connection is pinned to the address that was checked (design §2, DNS rebinding).

Fakes only: a fake httpcore network backend stands in for the socket layer, so no test touches the network. The
real ``PinnedTransport`` and httpcore's real HTTP/1.1 and TLS-start code run on top of it."""

from __future__ import annotations

import asyncio
import socket
import ssl

import httpcore
import httpx
import pytest

from roost.connectors import texts
from roost.connectors.address import check_base_url
from roost.connectors.http import ConnectorClient, Credentials
from roost.connectors.pinned import Pin, PinnedBackend, PinnedTransport

SECRET = "sk-live-0123456789abcdef"
BASE = check_base_url("https://api.example.com/v1")
PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"
_REPLY = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\n\r\n{\"ok\":true}"


class FakeStream(httpcore.AsyncNetworkStream):
    """A socket that records what TLS start was asked for and what was written, and answers once."""

    def __init__(self, record: dict) -> None:
        self._record = record
        self._reply = [_REPLY]

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._reply.pop(0) if self._reply else b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._record["written"] = self._record.get("written", b"") + buffer

    async def aclose(self) -> None:
        return None

    async def start_tls(self, ssl_context: ssl.SSLContext, server_hostname: str | None = None,
                        timeout: float | None = None) -> httpcore.AsyncNetworkStream:
        self._record["tls"] = (ssl_context, server_hostname)
        return self

    def get_extra_info(self, info: str):
        return None


class FakeBackend(httpcore.AsyncNetworkBackend):
    """Records every address it is asked to dial; ``refuse`` lists addresses that fail like an unreachable route."""

    def __init__(self, refuse: tuple[str, ...] = ()) -> None:
        self.dialed: list[str] = []
        self.record: dict = {}
        self._refuse = refuse

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.dialed.append(host)
        self.record["port"] = port
        if host in self._refuse:
            raise httpcore.ConnectError("unreachable")
        return FakeStream(self.record)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):  # pragma: no cover
        raise AssertionError("never a unix socket")

    async def sleep(self, seconds: float) -> None:
        return None


class Flipping:
    """A rebinding DNS server: a public answer the first time, a private one every time after."""

    def __init__(self, first: str = PUBLIC_V4, after: str = "127.0.0.1") -> None:
        self.calls = 0
        self._first, self._after = first, after

    def answer(self) -> list[str]:
        self.calls += 1
        return [self._first] if self.calls == 1 else [self._after]

    async def resolve(self, host: str) -> list[str]:
        return self.answer()


def _client(backend: FakeBackend, resolver) -> ConnectorClient:
    return ConnectorClient(resolver=resolver, network_backend=backend)


async def _send(client: ConnectorClient, base=BASE, path="/sites"):
    return await client.send(base, Credentials("bearer", "Authorization", SECRET), "GET", base.url + path, {}, None,
                             False)


async def test_a_rebinding_answer_never_reaches_the_connect(monkeypatch):
    dns = Flipping()

    def system_lookup(*args, **kwargs):  # any second lookup, by anyone, would get the private answer
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (dns.answer()[0], 443))]

    async def loop_lookup(*args, **kwargs):
        return system_lookup()

    monkeypatch.setattr(socket, "getaddrinfo", system_lookup)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", loop_lookup)
    backend = FakeBackend()
    result = await _send(_client(backend, dns.resolve))
    assert result.status == 200
    assert backend.dialed == [PUBLIC_V4] and dns.calls == 1


async def test_sni_host_header_and_certificate_check_stay_on_the_hostname():
    backend = FakeBackend()
    result = await _send(_client(backend, Flipping().resolve))
    assert result.status == 200 and backend.record["port"] == 443
    context, server_hostname = backend.record["tls"]
    assert server_hostname == "api.example.com"
    assert context.check_hostname is True and context.verify_mode == ssl.CERT_REQUIRED
    head = backend.record["written"].split(b"\r\n\r\n")[0].split(b"\r\n")
    assert head[0] == b"GET /v1/sites HTTP/1.1" and b"Host: api.example.com" in head


async def test_a_private_answer_is_refused_and_nothing_is_dialed():
    for answer in (["10.0.0.5"], [PUBLIC_V4, "192.168.1.2"], ["fd00::1"], ["fe80::1"], ["::1"],
                   ["::ffff:10.0.0.1"], ["169.254.169.254"], ["100.64.0.1"], []):
        async def resolve(host: str, answer=answer) -> list[str]:
            return answer

        backend = FakeBackend()
        result = await _send(_client(backend, resolve))
        assert result.status is None and result.body == texts.PRIVATE_ADDRESS, answer
        assert backend.dialed == []


async def test_ipv6_answers_are_dialed_as_checked():
    async def resolve(host: str) -> list[str]:
        return [PUBLIC_V6, PUBLIC_V4]

    backend = FakeBackend()
    result = await _send(_client(backend, resolve))
    assert result.status == 200 and backend.dialed == [PUBLIC_V6]
    assert backend.record["tls"][1] == "api.example.com"


async def test_an_unreachable_checked_address_falls_to_the_next_checked_one_only():
    async def resolve(host: str) -> list[str]:
        return [PUBLIC_V6, PUBLIC_V4, PUBLIC_V6]

    backend = FakeBackend(refuse=(PUBLIC_V6,))
    result = await _send(_client(backend, resolve))
    assert result.status == 200 and backend.dialed == [PUBLIC_V6, PUBLIC_V4]
    backend = FakeBackend(refuse=(PUBLIC_V6, PUBLIC_V4))
    result = await _send(_client(backend, resolve))
    assert result.status is None and result.body == texts.NO_CONNECT
    assert backend.dialed == [PUBLIC_V6, PUBLIC_V4]


async def test_an_ip_literal_base_is_dialed_as_itself():
    base = check_base_url(f"https://[{PUBLIC_V6}]/v1")
    backend = FakeBackend()

    async def no_dns(host: str) -> list[str]:
        raise AssertionError("an IP literal needs no lookup")

    result = await _send(_client(backend, no_dns), base=base)
    assert result.status == 200 and backend.dialed == [PUBLIC_V6]


async def test_the_backend_dials_only_the_pinned_host():
    backend = FakeBackend()
    pinned = PinnedBackend(Pin("api.example.com", (PUBLIC_V4,)), inner=backend)
    with pytest.raises(httpcore.ConnectError):
        await pinned.connect_tcp("evil.example.org", 443)
    with pytest.raises(httpcore.ConnectError):
        await pinned.connect_unix_socket("/tmp/x.sock")
    assert backend.dialed == []
    await pinned.connect_tcp("API.example.com", 443)
    assert backend.dialed == [PUBLIC_V4]


async def test_the_backend_refuses_an_unchecked_address_even_if_handed_one():
    backend = FakeBackend()
    for addresses in ((), ("10.0.0.1",), (PUBLIC_V4, "127.0.0.1")):
        with pytest.raises(ValueError):
            PinnedBackend(Pin("api.example.com", addresses), inner=backend)
    assert backend.dialed == []


async def test_the_transport_verifies_certificates():
    transport = PinnedTransport(Pin("api.example.com", (PUBLIC_V4,)), network_backend=FakeBackend())
    assert transport.ssl_context.check_hostname is True
    assert transport.ssl_context.verify_mode == ssl.CERT_REQUIRED
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://api.example.com/v1/x")
    assert response.status_code == 200


async def test_the_client_factory_is_handed_the_pin():
    pins: list[Pin] = []

    def factory(pin: Pin) -> httpx.AsyncClient:
        pins.append(pin)
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(204)))

    async def resolve(host: str) -> list[str]:
        return [PUBLIC_V4, PUBLIC_V4, PUBLIC_V6]

    client = ConnectorClient(client_factory=factory, resolver=resolve)
    assert (await _send(client)).status == 204
    assert pins == [Pin("api.example.com", (PUBLIC_V4, PUBLIC_V6))]
