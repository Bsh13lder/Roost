"""``ConnectorClient``: the one place a connector request leaves Roost (design §2–§3).

It resolves the host once and refuses unless every address is public, connects only to those checked addresses
(``PinnedTransport``: httpx never resolves the name again, so a DNS answer that changes in between cannot steer the
connection; TLS and the ``Host`` header stay on the hostname), adds the key (the only code that ever touches
it on the way out), never follows a redirect, reads at most ``CONNECTOR_RESPONSE_MAX_BYTES``, and hides the key
in whatever comes back. Errors become fixed sentences: httpx's own messages hold the URL, and with query auth the
URL holds the key, so they are never shown or logged (the log keeps the exception's type name only)."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import quote, quote_plus

import httpcore
import httpx

from roost.connectors import texts
from roost.connectors.address import Base, address_ok, is_public_ip
from roost.connectors.pinned import Pin, PinnedTransport
from roost.constants import CONNECTOR_REDACTED, CONNECTOR_RESPONSE_MAX_BYTES, CONNECTOR_TIMEOUT_S

logger = logging.getLogger(__name__)

Resolver = Callable[[str], Awaitable[list[str]]]
ClientFactory = Callable[[Pin], httpx.AsyncClient]

_TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "csv", "yaml")
_HTTPS_PORT = 443
_ESCAPE = re.compile(r"%[0-9A-F]{2}")


@dataclass(frozen=True)
class Credentials:
    """How the key is sent. Never logged, returned or shown."""
    style: str     # bearer | header | query
    name: str      # the header or query parameter name
    secret: str

    def __repr__(self) -> str:   # a stray log of this object must never print the key
        return f"Credentials(style={self.style!r}, name={self.name!r}, secret=<hidden>)"


@dataclass(frozen=True)
class CallResult:
    status: int | None   # None: nothing was sent, or no answer came back
    body: str            # the answer's text (key hidden), or one of the fixed sentences
    cut: bool = False


async def resolve_host(host: str) -> list[str]:
    """Every address the host resolves to (the system resolver)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, _HTTPS_PORT, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _default_client(pin: Pin, network_backend: httpcore.AsyncNetworkBackend | None = None) -> httpx.AsyncClient:
    # trust_env=False: no proxy or .netrc from the environment may see the key. The transport dials only the pin.
    return httpx.AsyncClient(transport=PinnedTransport(pin, network_backend), trust_env=False, follow_redirects=False,
                             timeout=CONNECTOR_TIMEOUT_S)


def redact(text: str, secret: str) -> str:
    """``text`` with the key, and its URL-encoded forms, replaced by ``CONNECTOR_REDACTED``."""
    if not secret:
        return text
    encoded = {quote(secret, safe=""), quote_plus(secret), quote(secret)}
    lower_hex = {_ESCAPE.sub(lambda m: m.group().lower(), form) for form in encoded}
    for form in sorted({secret, *encoded, *lower_hex}, key=len, reverse=True):
        text = text.replace(form, CONNECTOR_REDACTED)
    return text


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _auth(creds: Credentials, query: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """(headers, params) with the key added."""
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.5"}
    if creds.style == "query":
        return headers, {**query, creds.name: creds.secret}
    value = f"Bearer {creds.secret}" if creds.style == "bearer" else creds.secret
    return {**headers, creds.name: value}, dict(query)


def _body_text(raw: bytes, content_type: str) -> str:
    if not raw:
        return texts.EMPTY_BODY
    if any(kind in content_type.lower() for kind in _TEXT_TYPES):
        return raw.decode("utf-8", errors="replace")
    return texts.BINARY_BODY.format(size=len(raw))


class ConnectorClient:
    def __init__(self, *, client_factory: ClientFactory | None = None, resolver: Resolver | None = None,
                 network_backend: httpcore.AsyncNetworkBackend | None = None) -> None:
        """``network_backend`` is for tests: a fake socket layer under the real pinned transport."""
        self._factory = client_factory or (lambda pin: _default_client(pin, network_backend))
        self._resolve = resolver or resolve_host

    async def send(self, base: Base, creds: Credentials, method: str, url: str, query: Mapping[str, str],
                   body: Any, has_body: bool) -> CallResult:
        """Send one request built by the caller from ``base``. The URL must already have passed ``build_url``."""
        pin = await self._pin(base.host)
        if isinstance(pin, str):
            return CallResult(None, pin)
        headers, params = _auth(creds, query)
        content = None
        if has_body:
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {**headers, "Content-Type": "application/json"}
        try:
            status, raw, content_type, cut = await self._exchange(pin, method, url, headers, params, content)
        except httpx.TimeoutException as exc:
            return self._failed(exc, texts.TIMED_OUT)
        except httpx.ConnectError as exc:
            return self._failed(exc, texts.NO_CONNECT)
        except httpx.HTTPError as exc:
            return self._failed(exc, texts.FAILED)
        if 300 <= status < 400:
            return CallResult(status, texts.REDIRECT)
        return CallResult(status, redact(_body_text(raw, content_type), creds.secret), cut)

    async def _pin(self, host: str) -> Pin | str:
        """The host pinned to its checked addresses (resolved once, here), or the sentence that refuses it."""
        if _is_ip(host):
            return Pin(host, (host,)) if is_public_ip(host) else texts.PRIVATE_ADDRESS
        try:
            addresses = await self._resolve(host)
        except (OSError, UnicodeError) as exc:
            logger.info("A connector host did not resolve: %s", type(exc).__name__)
            return texts.DNS_FAILED
        if not address_ok(addresses):
            return texts.PRIVATE_ADDRESS
        return Pin(host, tuple(dict.fromkeys(addresses)))

    async def _exchange(self, pin: Pin, method: str, url: str, headers: dict[str, str], params: dict[str, str],
                        content: bytes | None) -> tuple[int, bytes, str, bool]:
        async with self._factory(pin) as client:
            request = client.build_request(method, url, headers=headers, params=params, content=content,
                                           timeout=CONNECTOR_TIMEOUT_S)
            response = await client.send(request, stream=True, follow_redirects=False)
            try:
                raw, cut = await _read_capped(response)
            finally:
                await response.aclose()
        return response.status_code, raw, response.headers.get("content-type", ""), cut

    @staticmethod
    def _failed(exc: Exception, text: str) -> CallResult:
        logger.warning("A connector request failed: %s", type(exc).__name__)
        return CallResult(None, text)


async def _read_capped(response: httpx.Response) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size > CONNECTOR_RESPONSE_MAX_BYTES:
            break
    raw = b"".join(chunks)
    if len(raw) <= CONNECTOR_RESPONSE_MAX_BYTES:
        return raw, False
    cut = raw[:CONNECTOR_RESPONSE_MAX_BYTES].decode("utf-8", errors="ignore").encode("utf-8")
    return cut, True
