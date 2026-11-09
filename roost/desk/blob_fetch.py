"""Read a ``blob:`` file inside the page that owns it (fast pages, slice 5): a PDF WhatsApp Web shows in a chat.

A ``blob:`` address has no web address the browser could fetch again (``Network.loadNetworkResource`` refuses it):
its bytes live only in the page that made it. So they are read there, in an **isolated world** named ``roost-blob``
(the page's own script cannot redefine ``fetch`` or ``btoa`` in it): ``fetch(blob)`` → its size checked against the
cap before any copy → base64 → returned by value over CDP into memory. Nothing is written to any disk.

The caller (``roost/computer_use/runner_read.py``) reads only a blob whose origin is the page's own; this module also
refuses any blob without a web (http/https) origin, and refuses an answer past the cap before decoding it."""

from __future__ import annotations

import base64
import binascii
import json
import math
from typing import Any
from urllib.parse import urlsplit

from roost.constants import CU_BLOB_B64_CHUNK
from roost.desk.cdp import CdpReplyError
from roost.desk.page_fetch import FetchFailed, FileTooBig
from roost.desk.page_geometry import CdpSender

BLOB_WORLD = "roost-blob"
BLOB_PREFIX = "blob:"
_WEB_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_NOT_A_BLOB = "not a blob address of a web page"
_NO_FRAME = "the page has no main frame"
_REFUSED = "the browser refused to read it"
_UNREADABLE = "the page could not read it"
_BAD_ANSWER = "the page gave no file"

# Page-side: the cap is checked on the blob's size before its bytes are copied or encoded.
_EXPRESSION = """(async () => {{
  const response = await fetch({url});
  if (!response.ok) return {{failed: true}};
  const blob = await response.blob();
  if (blob.size > {max_bytes}) return {{tooBig: true}};
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += {chunk}) {{
    text += String.fromCharCode.apply(null, bytes.subarray(i, i + {chunk}));
  }}
  return {{data: btoa(text)}};
}})()"""


def is_blob_url(url: str) -> bool:
    return url.lower().startswith(BLOB_PREFIX)


def _web_origin(url: str) -> str:
    """``scheme://host[:port]`` of an http(s) address, lowercased, the default port dropped; "" for anything else."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return ""
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    if scheme not in _WEB_SCHEMES or not host:
        return ""
    shown_port = f":{port}" if port is not None and port != _DEFAULT_PORTS[scheme] else ""
    return f"{scheme}://{host}{shown_port}"


def blob_origin(url: str) -> str:
    """The web origin a ``blob:`` address belongs to ("" when it is no blob, or its origin is not http/https)."""
    return _web_origin(url[len(BLOB_PREFIX):]) if is_blob_url(url) else ""


def page_origin(url: str) -> str:
    """The origin of the page at ``url``: its own, or its blob's when the tab shows a blob ("" for any other)."""
    return blob_origin(url) if is_blob_url(url) else _web_origin(url)


def _expression(url: str, max_bytes: int) -> str:
    return _EXPRESSION.format(url=json.dumps(url), max_bytes=int(max_bytes), chunk=int(CU_BLOB_B64_CHUNK))


async def _isolated_context(client: CdpSender, session_id: str) -> int:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = (((tree.get("result") or {}).get("frameTree") or {}).get("frame") or {}).get("id")
    if not isinstance(frame_id, str) or not frame_id:
        raise FetchFailed(_NO_FRAME)
    world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": BLOB_WORLD},
                              session_id=session_id)
    context_id = (world.get("result") or {}).get("executionContextId")
    if not isinstance(context_id, int):
        raise FetchFailed(_REFUSED)
    return context_id


def _decoded(reply: dict[str, Any], max_bytes: int) -> bytes:
    """The bytes in the page's answer; the cap is checked on the base64 length before decoding, and again after."""
    result = reply.get("result") or {}
    if result.get("exceptionDetails"):
        raise FetchFailed(_UNREADABLE)
    value = (result.get("result") or {}).get("value")
    if not isinstance(value, dict):
        raise FetchFailed(_BAD_ANSWER)
    if value.get("tooBig") is True:
        raise FileTooBig("the file is larger than the cap")
    data = value.get("data")
    if not isinstance(data, str):
        raise FetchFailed(_UNREADABLE)
    if len(data) > 4 * math.ceil(max_bytes / 3):
        raise FileTooBig("the file is larger than the cap")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FetchFailed(_BAD_ANSWER) from exc
    if len(raw) > max_bytes:
        raise FileTooBig("the file is larger than the cap")
    return raw


async def read_blob(client: CdpSender, session_id: str, url: str, max_bytes: int) -> bytes:
    """The bytes of the ``blob:`` file at ``url``, read inside the tab whose session is ``session_id``, at most
    ``max_bytes`` (``FileTooBig`` past that). ``CdpReplyError`` (the browser refused a call) is a ``FetchFailed``."""
    if not blob_origin(url):
        raise FetchFailed(_NOT_A_BLOB)
    try:
        context_id = await _isolated_context(client, session_id)
        reply = await client.send("Runtime.evaluate", {
            "expression": _expression(url, max_bytes), "contextId": context_id,
            "awaitPromise": True, "returnByValue": True,
        }, session_id=session_id)
    except CdpReplyError as exc:
        raise FetchFailed(_REFUSED) from exc
    return _decoded(reply, max_bytes)
