"""A connector's address rules (design §2), pure: the base URL the user saves, the path a bot asks for, and
whether an address the host resolves to may be called.

The host is fixed when the user saves: https, no user name or password, no port but 443, no query, a DNS name with
an alphabetic top label (so ``localhost`` and the decimal, octal and hex IP tricks are refused) or a global IP
literal. A bot's path is joined to the base by the server only, may not climb out of it, and must sit under one of
the allowed prefixes. ``AddressRefused`` carries a plain sentence that never repeats the address."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import unquote, urlsplit

from roost.constants import CONNECTOR_BLOCKED_SUFFIXES, CONNECTOR_PATH_MAX, CONNECTOR_URL_MAX
from roost.connectors import texts

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TOP_LABEL = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")
_DECODE_ROUNDS = 3


class AddressRefused(ValueError):
    """The address or path is not allowed; ``text`` is the plain sentence to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


@dataclass(frozen=True)
class Base:
    url: str    # https://host[/path], no trailing slash
    host: str   # lower-case, IDNA; an IPv6 literal without brackets
    path: str   # "" or "/v1"


def is_public_ip(text: str) -> bool:
    """True only for a global unicast address; an IPv4-mapped IPv6 address is judged as its IPv4 address."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local)


def address_ok(addresses: Iterable[str]) -> bool:
    """Every address a name resolved to is public (and there is at least one)."""
    found = list(addresses)
    return bool(found) and all(is_public_ip(a) for a in found)


def _has_bad_chars(text: str) -> bool:
    return any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in text) or "\\" in text


def _check_host(hostname: str) -> str:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not is_public_ip(hostname):
            raise AddressRefused(texts.PRIVATE_HOST)
        return hostname
    try:
        host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise AddressRefused(texts.BAD_HOST) from None
    labels = host.split(".")
    if host == "localhost" or host.endswith(CONNECTOR_BLOCKED_SUFFIXES):
        raise AddressRefused(texts.PRIVATE_HOST)
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels) or not _TOP_LABEL.match(labels[-1]):
        raise AddressRefused(texts.BAD_HOST)
    return host


def _segments_ok(path: str) -> bool:
    """No ``.`` or ``..`` segment, also after percent-decoding (a few rounds, for double encoding)."""
    seen = path
    for _ in range(_DECODE_ROUNDS):
        if any(segment in (".", "..") for segment in seen.split("/")):
            return False
        decoded = unquote(seen)
        if decoded == seen:
            return True
        seen = decoded
    return not any(segment in (".", "..") for segment in seen.split("/"))


def check_base_url(raw: str) -> Base:
    """The saved base URL, or ``AddressRefused``."""
    text = raw.strip() if isinstance(raw, str) else ""
    if not text or len(text) > CONNECTOR_URL_MAX or _has_bad_chars(text) or "?" in text or "#" in text:
        raise AddressRefused(texts.BAD_URL)
    parts = urlsplit(text)
    if parts.scheme.lower() != "https":
        raise AddressRefused(texts.HTTPS_ONLY)
    if "@" in parts.netloc or parts.username or parts.password:
        raise AddressRefused(texts.NO_CREDENTIALS)
    try:
        port = parts.port
    except ValueError:
        raise AddressRefused(texts.BAD_URL) from None
    if port not in (None, 443):
        raise AddressRefused(texts.NO_PORT)
    if not parts.hostname:
        raise AddressRefused(texts.BAD_URL)
    host = _check_host(parts.hostname)
    path = parts.path.rstrip("/")
    if path and (not _segments_ok(path) or "//" in path):
        raise AddressRefused(texts.BAD_URL)
    shown = f"[{host}]" if ":" in host else host
    return Base(url=f"https://{shown}{path}", host=host, path=path)


def _check_path(path: object) -> str:
    if not isinstance(path, str) or not path or len(path) > CONNECTOR_PATH_MAX:
        raise AddressRefused(texts.BAD_PATH)
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        raise AddressRefused(texts.BAD_PATH)
    if _has_bad_chars(path) or "?" in path or "#" in path or not _segments_ok(path):
        raise AddressRefused(texts.BAD_PATH)
    return path


def check_prefix(prefix: object) -> str:
    """An allowed path prefix as stored: it starts with ``/`` and follows the path rules."""
    return _check_path(prefix)


def _under(path: str, prefix: str) -> bool:
    root = prefix.rstrip("/")
    return not root or path == root or path.startswith(root + "/")


def build_url(base: Base, path: object, prefixes: Iterable[str]) -> str:
    """``base`` + ``path``, refused unless it stays on the base's host, under its path and one of ``prefixes``."""
    checked = _check_path(path)
    allowed = tuple(prefixes)
    if allowed and not any(_under(checked, p) for p in allowed):
        raise AddressRefused(texts.OUTSIDE_PREFIXES)
    url = base.url + checked
    parts = urlsplit(url)
    same_host = parts.scheme == "https" and parts.hostname == base.host and parts.port in (None, 443)
    if not same_host or parts.username or parts.query or parts.fragment or not _under(parts.path, base.path or "/"):
        raise AddressRefused(texts.BAD_PATH)
    return url
