"""web_search's words and pure parts (A3): the query, the fixed search address, the escaped results and the scope.

The query is the model's, so it only ever lands in the query string of ``WEB_SEARCH_URL`` (``quote_plus``); the
address is never the model's. The results are page text: escaped and wrapped as ``<untrusted_page>`` like any
page. ``result_scope`` gives each result's own address and its whole host (a ``host:`` entry), so a guarded run
may open a result and other pages on that site, and nothing else the results merely mention."""

from __future__ import annotations

import html
from typing import Any, Iterable
from urllib.parse import quote_plus, urlsplit

from roost.constants import WEB_SEARCH_QUERY_MAX, WEB_SEARCH_URL
from roost.research.results import SearchResult
from roost.talk.link_scope import HOST_PREFIX, LinkScope

BAD_QUERY_TEXT = f"Refused: web_search needs a query of 1 to {WEB_SEARCH_QUERY_MAX} characters."
NO_RESULTS_TEXT = "No results. Try other words, or open a site you know with open_page."
SEARCH_ACTIVITY = "searching the web"
_WWW = "www."


def search_query(arguments: dict[str, Any]) -> str | None:
    """The query with its spaces collapsed, or ``None`` when it is missing, empty or too long."""
    raw = arguments.get("query")
    if not isinstance(raw, str):
        return None
    query = " ".join(raw.split())
    return query if 0 < len(query) <= WEB_SEARCH_QUERY_MAX else None


def search_url(query: str) -> str:
    return f"{WEB_SEARCH_URL}?q={quote_plus(query)}"


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def wrap_results(query: str, results: Iterable[SearchResult]) -> str:
    """The numbered results (title, address, snippet), every part escaped, inside ``<untrusted_page>``."""
    lines = [f"Search results for “{_esc(query)}”:"]
    for number, result in enumerate(results, start=1):
        lines.append(f"{number}. {_esc(result.title)}\n   {_esc(result.url)}")
        if result.snippet:
            lines.append(f"   {_esc(result.snippet)}")
    if len(lines) == 1:
        lines.append(NO_RESULTS_TEXT)
    body = "\n".join(lines)
    return f'<untrusted_page url="{_esc(search_url(query))}">{body}</untrusted_page>'


def _host_entry(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return f"{HOST_PREFIX}{host[len(_WWW):] if host.startswith(_WWW) else host}"


def result_scope(results: Iterable[SearchResult]) -> LinkScope:
    """Each result's address and its host, for the run's link scope."""
    return LinkScope.of(entry for result in results for entry in (result.url, _host_entry(result.url)))
