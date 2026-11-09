"""Pinning a connector's connection to the address that was checked (design §2, DNS rebinding closed).

``ConnectorClient`` resolves the host once and checks every answer. ``PinnedTransport`` then makes sure httpx
never resolves it again: it is httpx's own transport with httpcore's connection pool given ``PinnedBackend`` as its
network backend. httpcore asks the backend to ``connect_tcp(<hostname>, 443)``; the backend refuses any other host
and dials one of the checked IP addresses instead (in the resolver's order, the next only when one cannot be
reached). Everything above the socket stays on the hostname: the URL, the ``Host`` header, TLS SNI
(``server_hostname``) and certificate verification, which uses httpx's default context (``CERT_REQUIRED``,
``check_hostname``) and is never turned off."""

from __future__ import annotations

import typing
from dataclasses import dataclass

import httpcore
import httpx

from roost.connectors.address import is_public_ip

_NOT_PINNED = "connection refused: not the checked host"


def _bare(host: str) -> str:
    return host.strip("[]").lower()


@dataclass(frozen=True)
class Pin:
    """The checked host and the addresses it may be dialed at (every one already found public)."""
    host: str
    addresses: tuple[str, ...]


class PinnedBackend(httpcore.AsyncNetworkBackend):
    """A network backend that dials only ``pin.addresses``, and only for ``pin.host``."""

    def __init__(self, pin: Pin, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        if not pin.addresses or not all(is_public_ip(a) for a in pin.addresses):
            raise ValueError("a pin needs at least one address, every one public")
        self._host = _bare(pin.host)
        self._addresses = pin.addresses
        self._inner = inner if inner is not None else httpcore.AnyIOBackend()

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                          local_address: str | None = None,
                          socket_options: typing.Iterable[typing.Any] | None = None) -> httpcore.AsyncNetworkStream:
        if _bare(host) != self._host:
            raise httpcore.ConnectError(_NOT_PINNED)
        unreachable: httpcore.ConnectError | None = None
        for address in self._addresses:
            try:
                return await self._inner.connect_tcp(address, port, timeout=timeout, local_address=local_address,
                                                     socket_options=socket_options)
            except httpcore.ConnectError as exc:   # a timeout is not retried: the time limit stays as it was
                unreachable = exc
        raise httpcore.ConnectError("no checked address could be reached") from unreachable

    async def connect_unix_socket(self, path: str, timeout: float | None = None,
                                  socket_options: typing.Iterable[typing.Any] | None = None
                                  ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError(_NOT_PINNED)

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedTransport(httpx.AsyncHTTPTransport):
    """httpx's transport (its request mapping and error mapping) over a pool that connects through ``PinnedBackend``.

    No proxy and nothing from the environment; no retries, so a connect is never tried again behind our back."""

    def __init__(self, pin: Pin, network_backend: httpcore.AsyncNetworkBackend | None = None) -> None:
        super().__init__(verify=True, trust_env=False, retries=0)
        if not isinstance(getattr(self, "_pool", None), httpcore.AsyncConnectionPool):
            raise RuntimeError("httpx's transport changed shape; refusing to send unpinned")
        self.ssl_context = httpx.create_ssl_context(verify=True, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(ssl_context=self.ssl_context, retries=0,
                                                  network_backend=PinnedBackend(pin, network_backend))
