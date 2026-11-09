"""Getting the public models page. One fixed host, nothing about the user goes in the request."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from roost.constants import MODEL_CHECK_HOST, MODEL_CHECK_MAX_BYTES, MODEL_CHECK_TIMEOUT_S, MODEL_CHECK_URL

_MAX_REDIRECTS = 3
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_HEADERS = {"User-Agent": "roost-model-check", "Accept": "text/html"}


class FetchRefused(Exception):
    """The page was not read: a redirect off the host, a bad status, or a body that is too big."""


class PageFetcher(Protocol):
    async def fetch(self) -> str: ...


class FilePageFetcher:
    """The E2E's page: a file on disk (scripted mode only; the config decides)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def fetch(self) -> str:
        return self._path.read_text(encoding="utf-8", errors="replace")


class HttpPageFetcher:
    """An anonymous GET of ``MODEL_CHECK_URL``: no cookies, no auth, no proxy settings from the environment,
    redirects only within the same host, a time cap and a size cap."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch(self) -> str:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(MODEL_CHECK_TIMEOUT_S), follow_redirects=False,
            trust_env=False, headers=_HEADERS,
        ) as client:
            url = MODEL_CHECK_URL
            for _ in range(_MAX_REDIRECTS + 1):
                async with client.stream("GET", url) as response:
                    if response.status_code in _REDIRECT_CODES:
                        url = self._same_host(urljoin(url, response.headers.get("location", "")))
                        continue
                    if response.status_code != 200:
                        raise FetchRefused(f"status {response.status_code}")
                    return await self._read_capped(response)
        raise FetchRefused("too many redirects")

    @staticmethod
    def _same_host(url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != MODEL_CHECK_HOST:
            raise FetchRefused("redirect to another host")
        return url

    @staticmethod
    async def _read_capped(response: httpx.Response) -> str:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MODEL_CHECK_MAX_BYTES:
                raise FetchRefused("page too large")
        return body.decode("utf-8", errors="replace")
