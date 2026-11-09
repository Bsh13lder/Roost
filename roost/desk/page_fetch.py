"""Fetch one file through the bot's own browser (fast pages, slice 5): ``Network.loadNetworkResource``.

The request goes out from the bot's Chromium, with its cookies and through its egress, exactly as if the page had
asked for it, and the bytes come back over CDP's ``IO`` stream into memory: nothing is written to any disk. The
caller checks the address first (``check_url``, and the page's own site or the run's fence); this module only
fetches, caps the size and always closes the stream. No page script runs."""

from __future__ import annotations

import base64
import contextlib

from roost.constants import CU_FETCH_CHUNK_BYTES
from roost.desk.cdp import CdpReplyError
from roost.desk.page_geometry import CdpSender

_OK_STATUS, _REDIRECT_STATUS = 200, 300


class FetchFailed(Exception):
    """The browser could not fetch the file (an HTTP error, a refused address, a stream that broke)."""


class FileTooBig(FetchFailed):
    """The file is larger than the cap; the stream was closed without reading the rest."""


async def _frame_id(client: CdpSender, session_id: str) -> str:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = (((tree.get("result") or {}).get("frameTree") or {}).get("frame") or {}).get("id")
    if not isinstance(frame_id, str) or not frame_id:
        raise FetchFailed("the page has no main frame")
    return frame_id


async def _open_stream(client: CdpSender, session_id: str, url: str) -> str:
    reply = await client.send("Network.loadNetworkResource", {
        "frameId": await _frame_id(client, session_id), "url": url,
        "options": {"disableCache": False, "includeCredentials": True},
    }, session_id=session_id)
    resource = (reply.get("result") or {}).get("resource") or {}
    status = resource.get("httpStatusCode")
    if not resource.get("success") or not isinstance(status, int) or not _OK_STATUS <= status < _REDIRECT_STATUS:
        raise FetchFailed(f"the browser could not fetch it ({status or resource.get('netErrorName', 'error')})")
    stream = resource.get("stream")
    if not isinstance(stream, str) or not stream:
        raise FetchFailed("the browser gave no stream")
    return stream


async def _read_stream(client: CdpSender, session_id: str, stream: str, max_bytes: int) -> bytes:
    data = b""
    while True:
        reply = (await client.send("IO.read", {"handle": stream, "size": CU_FETCH_CHUNK_BYTES},
                                   session_id=session_id)).get("result") or {}
        chunk = str(reply.get("data", ""))
        data += base64.b64decode(chunk) if reply.get("base64Encoded") else chunk.encode("utf-8")
        if len(data) > max_bytes:
            raise FileTooBig("the file is larger than the cap")
        if reply.get("eof") or not chunk:
            return data


async def fetch_through_browser(client: CdpSender, session_id: str, url: str, max_bytes: int) -> bytes:
    """The bytes at ``url`` as the bot's browser fetches them, at most ``max_bytes`` (``FileTooBig`` past that).
    The stream is always closed. ``CdpReplyError`` (the browser refused the call) is a ``FetchFailed``."""
    try:
        stream = await _open_stream(client, session_id, url)
    except CdpReplyError as exc:
        raise FetchFailed("the browser refused the fetch") from exc
    try:
        return await _read_stream(client, session_id, stream, max_bytes)
    except CdpReplyError as exc:
        raise FetchFailed("the browser's stream broke") from exc
    finally:
        with contextlib.suppress(CdpReplyError):
            await client.send("IO.close", {"handle": stream}, session_id=session_id)
