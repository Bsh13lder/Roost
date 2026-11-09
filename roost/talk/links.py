"""The Links tab (S1.9): every http(s) link in a bot's chats, with its real
host. Roost never fetches them; the web opens one only on a click, in a new tab
with ``noopener noreferrer``.

Fix round 1: ``_host`` must report the host a *browser* would actually open,
not whatever Python's ``urlsplit`` parses, and must never hand back a label
that visually impersonates another domain. Two refusals mirror
``roost.desk.url_policy.check_url``'s own reasoning for the bot's browser:
a backslash in an http(s) URL is read as a forward slash by every
WHATWG-compliant browser (so ``evil.example\\@bank.com`` opens
``evil.example``, not the ``bank.com`` ``urlsplit`` would report -- the
whole link is dropped rather than guessed at), and userinfo
(``user:pass@host``) is refused outright, the same credential-smuggling
vector ``check_url`` already refuses. The surviving host is returned in its
IDNA/ASCII (punycode) form via ``roost.desk.url_policy.to_ascii_host``, so a
homograph host (Cyrillic ``а`` in ``аpple.com``) is shown as
``xn--pple-43d.com``, never as a label that reads identically to a trusted
one."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit

from roost.desk.url_policy import UrlBlocked, to_ascii_host
from roost.talk.store import Message

_LINK = re.compile(r"https?://[^\s<>\"')\]]+")
_TRAILING = ".,;:!?"


@dataclass(frozen=True)
class LinkSeen:
    url: str
    host: str
    message_id: str
    thread_id: str
    created_at: str


def _host(url: str) -> str | None:
    if "\\" in url:
        # A WHATWG-compliant browser reads "\" as "/" in an http(s) URL,
        # so "evil.example\@bank.com/login" actually opens evil.example --
        # urlsplit would report "bank.com" instead. Drop the whole link
        # rather than show a host the browser might not actually open.
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.username is not None or parts.password is not None:
        # Credentials embedded in a URL (user:pass@host) are a classic
        # phishing vector -- same outright refusal as url_policy.check_url.
        return None
    hostname = parts.hostname
    if not hostname:
        return None
    try:
        return to_ascii_host(hostname)
    except UrlBlocked:
        return None


def links_in(text: str) -> tuple[str, ...]:
    found = (match.group(0).rstrip(_TRAILING) for match in _LINK.finditer(text))
    return tuple(dict.fromkeys(url for url in found if _host(url)))


def collect_links(messages: Iterable[Message], limit: int) -> tuple[LinkSeen, ...]:
    """``messages`` arrive newest first; each URL keeps its newest sighting."""
    seen = tuple(LinkSeen(url, _host(url) or "", m.id, m.thread_id, m.created_at)
                 for m in messages for url in links_in(m.body))
    newest = {link.url: link for link in reversed(seen)}
    return tuple(sorted(newest.values(), key=lambda link: link.created_at, reverse=True))[:limit]


def link_out(link: LinkSeen) -> dict[str, Any]:
    return {"url": link.url, "host": link.host, "message_id": link.message_id,
            "thread_id": link.thread_id, "created_at": link.created_at}
