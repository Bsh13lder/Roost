"""A page's plain address (owner, 2026-11-01, "gigs still problem"): some sites hand out addresses that only open
inside their own lists. Upwork's ``/nx/search/jobs/details/~ID`` is the search list's popup: opened on its own it
answers 500 every time, while the job's plain page ``/jobs/~ID`` answers 200. ``open_page`` tries the plain address
when the page answers a server error (``roost/talk/server_error.py``).

Pure. A fixed table; the plain address keeps the scheme and host, so it never leads anywhere new."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

# (hosts, path pattern, plain path): https only, the pattern's group fills the plain path.
_PLAIN_FORMS: tuple[tuple[frozenset[str], re.Pattern[str], str], ...] = (
    (frozenset({"www.upwork.com", "upwork.com"}), re.compile(r"^/nx/(?:[\w-]+/)*details/(~[0-9a-z]+)/?$"), "/jobs/{}"),
)


def plain_address(url: str) -> str | None:
    """The plain address for ``url``, or None when it has no plain form."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    for hosts, pattern, plain in _PLAIN_FORMS:
        match = pattern.match(parts.path) if parts.hostname in hosts else None
        if match:
            return urlunsplit(("https", parts.netloc, plain.format(match.group(1)), "", ""))
    return None


# Owner, 2026-11-01: Grok's Upwork bot opened a job's apply form by its address. A job's own page names it.
_APPLY_FORMS: tuple[tuple[frozenset[str], re.Pattern[str], str], ...] = (
    (frozenset({"www.upwork.com", "upwork.com"}), re.compile(r"^/jobs/(?:[^/]*_)?(~[0-9a-z]+)/?$"),
     "/nx/proposals/job/{}/apply/"),
)


def apply_address(url: str) -> str | None:
    """The apply form's address for a job page ``url``, or None when it is no job page Roost knows."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    for hosts, pattern, form in _APPLY_FORMS:
        match = pattern.match(parts.path) if parts.hostname in hosts else None
        if match:
            return urlunsplit(("https", parts.netloc, form.format(match.group(1)), "", ""))
    return None
