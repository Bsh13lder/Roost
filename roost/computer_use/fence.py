"""The site fence: the hosts a computer-use run may go to.

It is built only from your own messages (links and bare domains, the same reading as ``LinkScope``)
and from hosts you OK'd on a new-site card; never from a page. A fence host lets through itself and
its subdomains, never a look-alike (``upwork.com`` allows ``www.upwork.com``, not
``upwork.com.evil.io`` or ``notupwork.com``). Hosts are compared in their IDNA (punycode) form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from roost.desk.url_policy import UrlBlocked, to_ascii_host
from roost.talk.link_scope import HOST_PREFIX, LinkScope

_WWW = "www."


def normalise_host(host: str) -> str:
    """The host in lower-case IDNA form with no trailing dot, or "" when it isn't a usable host name."""
    cleaned = host.strip().rstrip(".").lower()
    if not cleaned or any(char.isspace() or char in "/\\@:" for char in cleaned):
        return ""
    try:
        return to_ascii_host(cleaned).lower()
    except UrlBlocked:
        return ""


def _site_of(host: str) -> str:
    """A host you named stands for its site: ``www.`` is dropped so ``upwork.com`` and its pages both count."""
    found = normalise_host(host)
    return found[len(_WWW):] if found.startswith(_WWW) and found.count(".") > 1 else found


def _entry_host(entry: str) -> str:
    if entry.startswith(HOST_PREFIX):
        return entry[len(HOST_PREFIX):]
    try:
        return urlsplit(entry).hostname or ""
    except ValueError:
        return ""


@dataclass(frozen=True)
class SiteFence:
    hosts: frozenset[str]

    def allows(self, host: str) -> bool:
        wanted = normalise_host(host)
        if not wanted:
            return False
        return any(wanted == known or wanted.endswith(f".{known}") for known in self.hosts)

    def with_host(self, host: str) -> "SiteFence":
        """A new fence with ``host`` added (an OK on a new-site card); an unusable host changes nothing."""
        site = _site_of(host)
        return SiteFence(self.hosts | {site}) if site else self


def fence_from(user_texts: Iterable[str], approved_hosts: Iterable[str]) -> SiteFence:
    """The fence for a run: the hosts in your messages plus the hosts you approved on cards."""
    scope = LinkScope.from_texts(user_texts)
    named = (_site_of(_entry_host(entry)) for entry in scope.urls)
    approved = (_site_of(host) for host in approved_hosts)
    return SiteFence(frozenset(host for host in (*named, *approved) if host))
