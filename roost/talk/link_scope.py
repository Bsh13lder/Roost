"""Links a guarded run may open (M1 D4, rulings R2/R3).

A guarded run may open a URL only if it appears verbatim in the user's own
messages or on a page read earlier in the same chain. ``LinkScope`` is that
set: seeded from the user's messages and the scope a handoff carried in,
grown by every page the run reads, handed down with ``ask_bot`` and back up
with the answer. ``match`` returns the STORED entry and the run opens that,
never the model's string. A request may differ from an entry only by one
trailing slash or by the ``&amp;`` the model sees in ``<untrusted_page>``
text; nothing is trimmed off a request, so no suffix rides along."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from roost.constants import LINK_SCOPE_MAX_URLS, NAMED_SITES

_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}"
# A domain typed without a scheme: ``upwork.com``, ``www.upwork.com``, ``upwork.com/jobs``.
_BARE = re.compile(
    r"(?<![\w@./:\\-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24})(?![\w@-])(/[^\s<>\"'`]*)?", re.IGNORECASE,
)
HOST_PREFIX = "host:"


def urls_in(text: str) -> tuple[str, ...]:
    """Links in free text. Sentence punctuation after a link is not part of
    it — trimmed HERE only, never from a requested URL (``LinkScope.match``)."""
    found = (match.group(0).rstrip(_TRAILING) for match in _URL.finditer(text))
    return tuple(dict.fromkeys(url for url in found if url))


def _bare_host(host: str) -> str:
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def bare_entries_in(text: str) -> tuple[str, ...]:
    """Domains the user typed without ``https://``. A bare ``upwork.com`` opens its
    whole site (a ``host:`` entry); ``upwork.com/jobs`` is that exact page, with
    or without ``www.``. Text inside a full link is not read again."""
    rest = _URL.sub(" ", text)
    found: list[str] = []
    for match in _BARE.finditer(rest):
        host, path = _bare_host(match.group(1)), (match.group(2) or "").rstrip(_TRAILING)
        if path in ("", "/"):
            found.append(f"{HOST_PREFIX}{host}")
        else:
            found.extend((f"https://{host}{path}", f"https://www.{host}{path}"))
    return tuple(dict.fromkeys(found))


def named_site_entries(text: str) -> tuple[str, ...]:
    """Well-known sites the user names in plain words ("sign in to Google"): each opens that
    site's own hosts (``NAMED_SITES``). Read only from the user's own messages, never from a page."""
    plain = _BARE.sub(" ", _URL.sub(" ", text))       # a name inside a typed link is that link, not a word
    words = {word.lower() for word in re.findall(r"[A-Za-z]+", plain)}
    hosts = (host for name, site_hosts in NAMED_SITES.items() if name in words for host in site_hosts)
    return tuple(dict.fromkeys(f"{HOST_PREFIX}{host}" for host in hosts))


def _same_site(host: str, site: str) -> bool:
    """The site itself, its ``www.``, or any subdomain of it (DNS for those goes to the site's owner)."""
    host = _bare_host(host)
    return host == site or host.endswith(f".{site}")


def _host_allows(entry: str, url: str) -> bool:
    """A ``host:`` entry lets through an http(s) link to that host (or its ``www.``),
    never one with credentials, a backslash or a port."""
    if not entry.startswith(HOST_PREFIX) or "\\" in url:
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme in ("http", "https") and parts.username is None and parts.port is None
                and parts.hostname is not None and _same_site(parts.hostname, entry[len(HOST_PREFIX):]))
    except ValueError:
        return False


def _forms(url: str) -> frozenset[str]:
    """The spellings a request may use for a stored link: itself, plus or minus one trailing slash."""
    bare = url[:-1] if url.endswith("/") else url
    return frozenset({url, bare, f"{bare}/"})


@dataclass(frozen=True)
class LinkScope:
    urls: frozenset[str] = frozenset()

    @classmethod
    def of(cls, urls: Iterable[str]) -> "LinkScope":
        """Entries are kept as given (``urls_in`` output, a page's real URL,
        a scope handed over); only empty strings are dropped."""
        return cls(frozenset(url for url in urls if url))

    @classmethod
    def from_texts(cls, texts: Iterable[str]) -> "LinkScope":
        return cls.of(
            url for text in texts
            for url in (*urls_in(text), *bare_entries_in(text), *named_site_entries(text))
        )

    def with_page(self, url: str, text: str) -> "LinkScope":
        return self.merge(LinkScope.of((url, *urls_in(text))))

    def merge(self, other: "LinkScope") -> "LinkScope":
        """``self`` first: the user's own links can't be pushed out by a page full of links."""
        room = max(0, LINK_SCOPE_MAX_URLS - len(self.urls))
        added = sorted(other.urls - self.urls)[:room]
        return LinkScope(self.urls | frozenset(added))

    def match(self, url: str) -> str | None:
        """The stored entry ``url`` names, or None. Accepted: the entry,
        the entry plus or minus one trailing slash, and either of those with
        ``&amp;`` written for ``&``. Anything else — a suffix like ``.,;:``,
        an entity like ``&comma;``, surrounding space — is another link."""
        wanted = {url, url.replace("&amp;", "&")} - {""}
        exact = next((known for known in sorted(self.urls) if wanted & _forms(known)), None)
        if exact is not None:
            return exact
        host_entry = next((known for known in sorted(self.urls) if _host_allows(known, url)), None)
        return url if host_entry else None

    def allows(self, url: str) -> bool:
        return self.match(url) is not None

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(sorted(self.urls))
