"""Egress proxy for bot browsers.

Every bot's Brave is launched with ``--proxy-server=http://127.0.0.1:<port>``
(``roost/desk/browser.py``, a later task) pointing at the ``EgressProxy``
started alongside the keeper. It is the only thing standing between a
hostile page's JS and the host's own network once a bot's browser is
compromised (spec Review Focus #3): it refuses to dial loopback, private,
link-local, CGNAT and multicast addresses, and refuses every one of
Roost's and LazyClaw's own ports regardless of address.

``is_blocked_address`` is deliberately a pure function of one resolved
address and a port — no DNS, no sockets — so the policy table is testable
without a running proxy. The proxy itself resolves a host's name at
CONNECT/request time with ``loop.getaddrinfo`` (never trusting a single
cached answer) and checks *every* address that name resolved to before
picking one to dial, so a multi-answer DNS response can't sneak a private
address past a check that only looked at the first one.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from roost.log_rotation import rotating_handler
from roost.constants import PROXY_CONNECT_TIMEOUT_S, PROXY_PORT, PROXY_RESOLVE_TIMEOUT_S
from roost.constants import SENSITIVE_PORTS as _SENSITIVE_PORTS

logger = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# RFC 6598 "shared address space" — CGNAT. Python's ipaddress module
# does not count this as `is_private` (confirmed on the 3.12-3.14 series
# this project targets), so it needs its own explicit check.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

_DEFAULT_SCHEME_PORTS = {"http": 80, "https": 443}

_CRLF = b"\r\n"
_READ_CHUNK = 65536


def _block_reason(ip: IPAddress, port: int) -> str | None:
    """Return why ``ip:port`` must be refused, or ``None`` if it's allowed."""
    if port in _SENSITIVE_PORTS:
        return "sensitive_port"

    candidate: IPAddress = ip
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # An IPv4-mapped IPv6 literal (::ffff:a.b.c.d) must be judged by
        # the IPv4 address it wraps, not by the IPv6 shell around it.
        candidate = ip.ipv4_mapped

    if isinstance(candidate, ipaddress.IPv4Address) and candidate in _CGNAT_NETWORK:
        return "cgnat"
    if candidate.is_loopback:
        return "loopback"
    if candidate.is_link_local:
        return "link_local"
    if candidate.is_multicast:
        return "multicast"
    if candidate.is_unspecified:
        return "unspecified"
    if candidate.is_reserved:
        return "reserved"
    if candidate.is_private:
        return "private"
    return None


def is_blocked_address(ip: IPAddress, port: int) -> bool:
    """True if a bot browser must never be allowed to reach ``ip:port``."""
    return _block_reason(ip, port) is not None


class _ProxyRequestError(ValueError):
    """The client's request line or target couldn't be parsed."""


def _parse_request_line(line: bytes) -> tuple[str, str, bytes]:
    try:
        method, target, version = line.decode("latin-1").rstrip("\r\n").split(" ", 2)
    except ValueError as exc:
        raise _ProxyRequestError(f"malformed request line: {line!r}") from exc
    return method, target, version.encode("latin-1")


def _split_host_port(hostport: str, default_port: int) -> tuple[str, int]:
    if hostport.startswith("["):
        host, _, rest = hostport[1:].partition("]")
        port_text = rest[1:] if rest.startswith(":") else ""
    else:
        host, _, port_text = hostport.rpartition(":")
        if not host:
            host, port_text = hostport, ""
    if not host:
        raise _ProxyRequestError(f"missing host in {hostport!r}")
    try:
        port = int(port_text) if port_text else default_port
    except ValueError as exc:
        raise _ProxyRequestError(f"bad port in {hostport!r}") from exc
    return host, port


def _parse_connect_target(target: str) -> tuple[str, int]:
    return _split_host_port(target, default_port=443)


def _parse_absolute_uri(target: str) -> tuple[str, int, bytes]:
    parsed = urlsplit(target)
    if not parsed.scheme or not parsed.hostname:
        raise _ProxyRequestError(f"not an absolute-URI request target: {target!r}")
    default_port = _DEFAULT_SCHEME_PORTS.get(parsed.scheme, 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.hostname, parsed.port or default_port, path.encode("latin-1")


class EgressProxy:
    """A forward HTTP(S) proxy: ``CONNECT`` tunnels for HTTPS, absolute-URI
    ``GET``/``POST``/... for plain HTTP. Every refusal is logged as one
    JSON line at ``<database_dir>/proxy.log``."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = PROXY_PORT,
        database_dir: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._log_path = database_dir / "proxy.log" if database_dir is not None else None
        self._refusal_handler = rotating_handler(self._log_path) if self._log_path is not None else None
        if self._refusal_handler is not None:
            self._refusal_handler.setFormatter(logging.Formatter("%(message)s"))
        self._server: asyncio.base_events.Server | None = None

    @property
    def bound_port(self) -> int:
        """The actual listening port — differs from ``port`` when it was
        requested as ``0`` (let the OS pick one, used by tests)."""
        if self._server is None:
            return self.port
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    # -- connection handling -------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._serve_one(reader, writer)
        except _ProxyRequestError:
            await self._write_status(writer, 400, "Bad Request")
        except Exception:
            # A connection handler must never take the listening socket
            # down with it — log loudly (never silently swallow) and
            # move on to the next connection.
            logger.exception("egress proxy: unhandled error handling a client connection")
        finally:
            with contextlib.suppress(OSError):
                writer.close()

    async def _serve_one(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        header_lines = await self._read_headers(reader)
        if not header_lines:
            return
        method, target, version = _parse_request_line(header_lines[0])

        path: bytes | None = None
        if method == "CONNECT":
            host, port = _parse_connect_target(target)
        else:
            host, port, path = _parse_absolute_uri(target)

        chosen, resolved_ips, reason = await self._resolve_and_check(host, port)
        if chosen is None:
            if reason == "resolve-timeout":
                self._log_refusal(host, resolved_ips, port, reason)
                await self._write_status(writer, 504, "Gateway Timeout")
                return
            self._log_refusal(host, resolved_ips, port, reason or "unresolvable")
            await self._write_status(writer, 403, "Forbidden")
            return

        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(str(chosen), port), timeout=PROXY_CONNECT_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            self._log_refusal(host, resolved_ips, port, "connect-timeout")
            await self._write_status(writer, 504, "Gateway Timeout")
            return
        except OSError:
            await self._write_status(writer, 502, "Bad Gateway")
            return

        try:
            if method == "CONNECT":
                await self._write_status(writer, 200, "Connection Established")
            else:
                assert path is not None
                await self._forward_request(upstream_writer, method, path, version, header_lines)
            await self._relay(reader, writer, upstream_reader, upstream_writer)
        finally:
            with contextlib.suppress(OSError):
                upstream_writer.close()

    @staticmethod
    async def _read_headers(reader: asyncio.StreamReader) -> list[bytes]:
        first = await reader.readline()
        if not first:
            return []
        lines = [first]
        while lines[-1] not in (b"\r\n", b"\n", b""):
            lines.append(await reader.readline())
        return lines

    async def _resolve_and_check(
        self, host: str, port: int
    ) -> tuple[IPAddress | None, list[str], str | None]:
        loop = asyncio.get_running_loop()
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, port, type=socket.SOCK_STREAM),
                timeout=PROXY_RESOLVE_TIMEOUT_S,
            )
        except socket.gaierror:
            return None, [], "dns_error"
        except asyncio.TimeoutError:
            return None, [], "resolve-timeout"

        resolved: list[IPAddress] = []
        seen: set[str] = set()
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_text = sockaddr[0]
            if ip_text in seen:
                continue
            seen.add(ip_text)
            resolved.append(ipaddress.ip_address(ip_text))

        reason: str | None = "unresolvable"
        for ip in resolved:
            # Goes through the public, overridable policy function (not
            # `_block_reason` directly) so the allow/block decision for
            # every resolved address is the single documented policy
            # entry point -- `_block_reason` below is consulted only to
            # label *why* once an address has already been refused.
            if not is_blocked_address(ip, port):
                return ip, [str(a) for a in resolved], None
            reason = _block_reason(ip, port) or "blocked"
        return None, [str(a) for a in resolved], reason

    @staticmethod
    async def _forward_request(
        upstream_writer: asyncio.StreamWriter,
        method: str,
        path: bytes,
        version: bytes,
        header_lines: list[bytes],
    ) -> None:
        upstream_writer.write(method.encode("latin-1") + b" " + path + b" " + version + _CRLF)
        for line in header_lines[1:]:
            upstream_writer.write(line)
        await upstream_writer.drain()

    @staticmethod
    async def _write_status(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
        writer.write(f"HTTP/1.1 {status} {reason}\r\n\r\n".encode("latin-1"))
        with contextlib.suppress(ConnectionError, OSError):
            await writer.drain()

    @staticmethod
    async def _relay(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    chunk = await src.read(_READ_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                # Best-effort half-close so the other side's reader
                # sees EOF promptly; some transports (already-closed,
                # TLS) don't support it, which is fine to ignore here.
                with contextlib.suppress(Exception):
                    dst.write_eof()

        await asyncio.gather(pump(reader, upstream_writer), pump(upstream_reader, writer))

    # -- audit log ------------------------------------------------------------

    def _log_refusal(self, host: str, resolved_ips: list[str], port: int, reason: str) -> None:
        if self._log_path is None:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "bot": None,
            "host": host,
            "ip": resolved_ips[0] if resolved_ips else None,
            "port": port,
            "reason": reason,
        }
        try:
            record = logging.LogRecord("roost.proxy.refusals", logging.INFO, "", 0, json.dumps(entry), None, None)
            self._refusal_handler.acquire()
            try:
                self._refusal_handler.emit(record)
                self._refusal_handler.flush()
            finally:
                self._refusal_handler.release()
        except OSError:
            # A full disk or missing dir must not crash the connection
            # handler -- but the refusal itself still happened (the 403
            # was already sent), so surface the logging failure loudly
            # instead of swallowing it.
            logger.error("egress proxy: failed to write refusal to %s", self._log_path, exc_info=True)
