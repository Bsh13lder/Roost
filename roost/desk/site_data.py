"""Clear one site's cookies and storage in a bot's Chromium (the Sign-in card's "No, this time" and Sign out).

Fixed CDP only, over the keeper's relay (``roost/desk/cdp.py``): ``Storage.getCookies`` reads the jar,
``Network.deleteCookies`` removes each cookie whose domain is the host or a subdomain of it (on the bot's own
tab session), and ``Storage.clearDataForOrigin`` clears every kind of storage for ``https://`` and ``http://`` of
the host and of each subdomain those cookies named. The host is validated first (``valid_host``): a plain DNS
name with at least two labels, never an address, a port, a path, a wildcard, an IP or a public suffix. Nothing
here logs or returns a cookie's value."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from roost.constants import (
    SITE_CLEAR_REFUSED_SUFFIXES, SITE_CLEAR_SCHEMES, SITE_CLEAR_STORAGE_TYPES, SITE_HOST_MAX_CHARS,
)

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class BadHost(ValueError):
    """Not a site Roost will clear."""


class CdpSender(Protocol):
    async def send(self, method: str, params: dict[str, Any] | None = None,
                   session_id: str | None = None) -> dict: ...


@dataclass(frozen=True)
class SiteCleared:
    """What was cleared: the host, how many cookies, and the origins whose storage was emptied."""

    host: str
    cookies: int
    origins: tuple[str, ...]


def valid_host(text: str) -> str:
    """The host, lower case with no trailing dot. ``BadHost`` for anything that is not a plain site name."""
    raw = text or ""
    host = raw.lower().removesuffix(".") if raw == raw.strip() else ""   # no stray whitespace or newline
    labels = host.split(".")
    if (not host or len(host) > SITE_HOST_MAX_CHARS or len(labels) < 2
            or not all(_LABEL.match(label) for label in labels) or labels[-1].isdigit()
            or host in SITE_CLEAR_REFUSED_SUFFIXES):
        raise BadHost(text)
    return host


def cookie_belongs(cookie_domain: str, host: str) -> bool:
    """A cookie set for the host itself or one of its subdomains (a leading dot is ignored)."""
    domain = (cookie_domain or "").lower().lstrip(".")
    return bool(domain) and (domain == host or domain.endswith(f".{host}"))


def origins_for(host: str, cookie_domains: Iterable[str]) -> tuple[str, ...]:
    """``https://`` and ``http://`` of the host, then of every subdomain the cookies named, each once."""
    names = dict.fromkeys([host, *(d.lower().lstrip(".") for d in cookie_domains if cookie_belongs(d, host))])
    return tuple(f"{scheme}://{name}" for name in names for scheme in SITE_CLEAR_SCHEMES)


async def clear_site(client: CdpSender, session_id: str, host: str) -> SiteCleared:
    """Delete the site's cookies and clear its storage. ``BadHost`` before any call when the host is not valid."""
    site = valid_host(host)
    reply = await client.send("Storage.getCookies")
    cookies = [c for c in reply.get("result", {}).get("cookies", []) if cookie_belongs(str(c.get("domain", "")), site)]
    for cookie in cookies:
        await client.send("Network.deleteCookies", {
            "name": str(cookie.get("name", "")), "domain": str(cookie.get("domain", "")),
            "path": str(cookie.get("path", "/")),
        }, session_id=session_id)
    origins = origins_for(site, (str(c.get("domain", "")) for c in cookies))
    for origin in origins:
        await client.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": SITE_CLEAR_STORAGE_TYPES})
    return SiteCleared(host=site, cookies=len(cookies), origins=origins)


@dataclass(frozen=True)
class SignInSignals:
    """What I'm done on a Sign-in card reads (A1): the bot's front page and how many cookies cover the host.
    Never a cookie's name or value."""

    page: Any
    cookies: int


def cookie_covers(cookie_domain: str, host: str) -> bool:
    """A cookie that the host's pages send: set for the host itself or a parent domain, never a public suffix
    (``.co.uk``) or a bare top-level name. A subdomain's cookie is not the site's."""
    domain = (cookie_domain or "").lower().lstrip(".")
    try:
        valid_host(domain)
    except BadHost:
        return False
    return host == domain or host.endswith(f".{domain}")


async def count_site_cookies(client: CdpSender, host: str) -> int:
    """How many cookies in the jar cover the host (``cookie_covers``). ``BadHost`` before any call."""
    site = valid_host(host)
    reply = await client.send("Storage.getCookies")
    return sum(1 for c in reply.get("result", {}).get("cookies", []) if cookie_covers(str(c.get("domain", "")), site))
