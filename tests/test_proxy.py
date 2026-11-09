"""Tests for ``roost.keeper.proxy.EgressProxy`` -- the forward proxy every
bot's Brave is launched with (``--proxy-server=http://127.0.0.1:<port>``).

Policy-table coverage lives in ``test_proxy_policy.py``; this file covers
the proxy's own wire behavior: a local, plain ``asyncio`` HTTP server
stands in for "something listening on the host's own network" per
Ruling 7 (no aiohttp dependency) --

  * a request for that local server, by loopback IP or by the hostname
    ``localhost``, is refused through the proxy with 403, and the
    refusal is logged as one JSON line at ``<database_dir>/proxy.log``;
  * the request never actually reaches the local server (it stays at
    zero connections) -- proving the block happens before any dial-out,
    not that the server merely replied 403 itself;
  * with the policy function monkeypatched open (isolating the
    forwarding/relay mechanics from the policy decision, since every
    real reachable test server necessarily lives on loopback, which the
    policy always blocks), both the plain-HTTP absolute-URI path and the
    CONNECT-tunnel path actually carry bytes end to end.

The ``network``-marked test hits the real internet and is excluded from
the default run (see ``pyproject.toml`` ``addopts``).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from roost.keeper import proxy as proxy_module
from roost.keeper.proxy import EgressProxy


class _EchoServer:
    """A plain ``asyncio`` TCP server on 127.0.0.1 that answers any HTTP
    request with a fixed 200 body and counts how many connections it
    actually accepted -- the local "something on the host network" that
    a blocked request must never reach."""

    def __init__(self) -> None:
        self.connections = 0
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        body = b"OK"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%b"
            % (len(body), body)
        )
        await writer.drain()
        writer.close()


@pytest.fixture
async def echo_server():
    server = _EchoServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture
async def proxy(tmp_path: Path):
    instance = EgressProxy(host="127.0.0.1", port=0, database_dir=tmp_path)
    await instance.start()
    try:
        yield instance
    finally:
        await instance.stop()


def _proxy_url(instance: EgressProxy) -> str:
    return f"http://{instance.host}:{instance.bound_port}"


def _read_log_lines(database_dir: Path) -> list[dict]:
    log_path = database_dir / "proxy.log"
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line]


async def test_start_and_stop_bind_and_release_the_port(tmp_path: Path) -> None:
    instance = EgressProxy(host="127.0.0.1", port=0, database_dir=tmp_path)
    await instance.start()
    bound_port = instance.bound_port
    _reader, writer = await asyncio.open_connection("127.0.0.1", bound_port)
    writer.close()
    await instance.stop()
    with pytest.raises(ConnectionRefusedError):
        await asyncio.open_connection("127.0.0.1", bound_port)


async def test_local_server_by_loopback_ip_is_not_reachable_through_the_proxy(
    proxy: EgressProxy, echo_server: _EchoServer, tmp_path: Path
) -> None:
    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get(f"http://127.0.0.1:{echo_server.port}/")

    assert response.status_code == 403
    assert echo_server.connections == 0

    lines = _read_log_lines(tmp_path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["bot"] is None
    assert entry["host"] == "127.0.0.1"
    assert entry["port"] == echo_server.port
    assert entry["ip"] == "127.0.0.1"
    assert entry["reason"] == "loopback"
    assert "ts" in entry


async def test_hostname_resolving_to_loopback_is_blocked(
    proxy: EgressProxy, echo_server: _EchoServer
) -> None:
    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get(f"http://localhost:{echo_server.port}/")

    assert response.status_code == 403
    assert echo_server.connections == 0


async def test_sensitive_port_is_blocked_even_though_nothing_is_private(
    proxy: EgressProxy, echo_server: _EchoServer
) -> None:
    # Port 18789 (the old app) is on the sensitive-port list regardless
    # of the address; the echo server isn't actually bound there, but
    # the proxy must refuse before ever attempting to dial it.
    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get("http://127.0.0.1:18789/")

    assert response.status_code == 403


async def test_allowed_plain_http_request_is_forwarded_end_to_end(
    proxy: EgressProxy, echo_server: _EchoServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every real, reachable test server lives on loopback, which the
    # policy always blocks -- so to exercise the actual forward/relay
    # mechanics (as opposed to the refusal path, covered above) this one
    # test opens the policy, isolating "does the proxy correctly forward
    # bytes" from "does the proxy correctly decide what to forward".
    monkeypatch.setattr(proxy_module, "is_blocked_address", lambda ip, port: False)

    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get(f"http://127.0.0.1:{echo_server.port}/")

    assert response.status_code == 200
    assert response.content == b"OK"
    assert echo_server.connections == 1


async def test_allowed_connect_tunnel_relays_bytes_end_to_end(
    proxy: EgressProxy, echo_server: _EchoServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proxy_module, "is_blocked_address", lambda ip, port: False)

    reader, writer = await asyncio.open_connection(proxy.host, proxy.bound_port)
    writer.write(f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    await writer.drain()

    connect_response = await reader.readline()
    assert connect_response.startswith(b"HTTP/1.1 200")
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break

    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    await writer.drain()

    raw = await reader.read(-1)
    writer.close()

    assert b"200 OK" in raw
    assert b"OK" in raw
    assert echo_server.connections == 1


async def test_malformed_request_line_gets_400_not_a_crash(proxy: EgressProxy) -> None:
    reader, writer = await asyncio.open_connection(proxy.host, proxy.bound_port)
    writer.write(b"not a valid request line at all\r\n\r\n")
    await writer.drain()

    response = await reader.readline()
    writer.close()

    assert response.startswith(b"HTTP/1.1 400")


async def test_unresolvable_hostname_is_refused_and_logged(
    proxy: EgressProxy, tmp_path: Path
) -> None:
    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get("http://this-host-does-not-exist.invalid/")

    assert response.status_code == 403

    lines = _read_log_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["host"] == "this-host-does-not-exist.invalid"
    assert lines[0]["ip"] is None
    assert lines[0]["reason"] == "dns_error"


@pytest.mark.network
async def test_real_https_site_through_the_proxy_returns_200(proxy: EgressProxy) -> None:
    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get("https://example.com")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Resolve/connect timeouts (night 1 fix): neither DNS resolution nor the
# upstream TCP connect may hang indefinitely -- each gets its own short
# ceiling, and a target that blows past it gets a fast 504 instead of the
# caller riding out the OS's own (much longer) timeout.
# ---------------------------------------------------------------------------


async def test_resolve_timeout_returns_504_and_logs_reason(
    proxy: EgressProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proxy_module, "PROXY_RESOLVE_TIMEOUT_S", 0.05)

    loop = asyncio.get_running_loop()
    real_getaddrinfo = loop.getaddrinfo

    async def _slow_getaddrinfo(*args, **kwargs):
        await asyncio.sleep(1.0)
        return await real_getaddrinfo(*args, **kwargs)

    monkeypatch.setattr(loop, "getaddrinfo", _slow_getaddrinfo)

    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        response = await client.get("http://example.com/")

    assert response.status_code == 504

    lines = _read_log_lines(tmp_path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["host"] == "example.com"
    assert entry["reason"] == "resolve-timeout"


async def test_connect_timeout_returns_504_and_logs_reason(
    proxy: EgressProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Open the policy (same technique as the forwarding tests above) so
    # resolution actually succeeds and the connect step is what's under
    # test here -- every real, reachable test address lives on loopback,
    # which the policy always blocks.
    monkeypatch.setattr(proxy_module, "is_blocked_address", lambda ip, port: False)
    monkeypatch.setattr(proxy_module, "PROXY_CONNECT_TIMEOUT_S", 0.05)

    real_open_connection = asyncio.open_connection

    async def _slow_open_connection(*args, **kwargs):
        await asyncio.sleep(1.0)
        return await real_open_connection(*args, **kwargs)

    monkeypatch.setattr(proxy_module.asyncio, "open_connection", _slow_open_connection)

    async with httpx.AsyncClient(proxy=_proxy_url(proxy)) as client:
        # Port 9 (discard) is never actually dialed -- open_connection is
        # patched to sleep past the timeout before it would be.
        response = await client.get("http://127.0.0.1:9/")

    assert response.status_code == 504

    lines = _read_log_lines(tmp_path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["host"] == "127.0.0.1"
    assert entry["port"] == 9
    assert entry["reason"] == "connect-timeout"
