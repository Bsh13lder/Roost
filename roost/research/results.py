"""The search results page as results (A3): DuckDuckGo's plain HTML page, parsed with the standard library.

``parse_results`` reads each ``a.result__a`` (its title and link) and the ``.result__snippet`` after it. A
DuckDuckGo redirect link (``//duckduckgo.com/l/?uddg=<url>``) becomes the address it points to; an ad (a link back
to DuckDuckGo), a link that is not plain http(s), one with credentials, a port or a backslash, and anything past
``WEB_SEARCH_MAX_RESULTS`` are left out. The text is plain (entities decoded, spaces collapsed, cut short); the
caller escapes it. Nothing here runs a page's script or fetches anything."""

from __future__ import annotations

from dataclasses import dataclass, replace
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from roost.constants import (
    WEB_SEARCH_ENGINE_HOSTS, WEB_SEARCH_HTML_MAX_CHARS, WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_SNIPPET_MAX,
    WEB_SEARCH_TITLE_MAX,
)
from roost.desk import PageText

_TITLE_CLASS = "result__a"
_SNIPPET_CLASS = "result__snippet"
_REDIRECT_PATH = "/l/"
_REDIRECT_KEY = "uddg"
_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class SearchPage:
    """What a desk's ``search_page`` returns: the results page as read, and its HTML (cut to a fixed size)."""

    page: PageText
    html: str


def _plain(text: str, limit: int) -> str:
    words = " ".join(text.split())
    return words if len(words) <= limit else words[:limit].rstrip() + "…"


def _host(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        ok = (parts.scheme in _SCHEMES and parts.hostname is not None and parts.username is None
              and parts.port is None and "\\" not in url)
    except ValueError:
        return None
    return parts.hostname if ok else None


def result_url(href: str) -> str | None:
    """The address a result link points to, or ``None`` for an ad, a DuckDuckGo page or a link Roost won't keep."""
    link = f"https:{href}" if href.startswith("//") else href
    host = _host(link)
    if host in WEB_SEARCH_ENGINE_HOSTS and urlsplit(link).path == _REDIRECT_PATH:
        link = (parse_qs(urlsplit(link).query).get(_REDIRECT_KEY) or [""])[0]
        host = _host(link)
    if host is None or host in WEB_SEARCH_ENGINE_HOSTS:
        return None
    return link


class _ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._capture: str | None = None      # "title" or "snippet" while inside such a link
        self._href = ""
        self._text: list[str] = []
        self._kept = False                    # the last title link became a result (its snippet may follow)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self._capture is not None:
            return
        named = dict(attrs)
        classes = (named.get("class") or "").split()
        if _TITLE_CLASS in classes:
            self._capture, self._href, self._text = "title", named.get("href") or "", []
        elif _SNIPPET_CLASS in classes:
            self._capture, self._text = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._capture is None:
            return
        text, kind = "".join(self._text), self._capture
        self._capture = None
        if kind == "title":
            url = result_url(self._href)
            self._kept = url is not None
            if url is not None:
                self.results.append(SearchResult(title=_plain(text, WEB_SEARCH_TITLE_MAX), url=url))
        elif self._kept and not self.results[-1].snippet:
            self.results[-1] = replace(self.results[-1], snippet=_plain(text, WEB_SEARCH_SNIPPET_MAX))


def parse_results(html: str) -> tuple[SearchResult, ...]:
    """Up to ``WEB_SEARCH_MAX_RESULTS`` results from the page's HTML, in page order."""
    parser = _ResultsParser()
    parser.feed(html[:WEB_SEARCH_HTML_MAX_CHARS])
    parser.close()
    return tuple(parser.results[:WEB_SEARCH_MAX_RESULTS])
