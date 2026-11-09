"""Is the page ready? (C3 Task 7, design §5.)

A page is ready when it is not navigating, its network has been quiet for ``CU_READY_STABLE_MS``, no busy mark
(``aria-busy``, a progress bar, a skeleton or a spinner) shows in the viewport, and two small probe screenshots taken
``CU_READY_STABLE_MS`` apart differ in at most ``CU_READY_DIFF_MAX`` of their pixels. ``wait_ready`` polls until
that holds or the timeout passes, and then says "still changing" (the bot looks anyway, and says so).

The lifecycle is read in an **isolated world** (``roost-ready``): ``document.readyState`` and the browser's own
resource timing, so the page's script cannot redefine what is read. A hostile page can only keep itself "still
changing", which costs the bot a wait and nothing else.
"""

from __future__ import annotations

import io
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from PIL import Image, ImageChops

from roost.constants import (
    CU_READY_DIFF_MAX,
    CU_READY_POLL_MS,
    CU_READY_PROBE_H,
    CU_READY_PROBE_W,
    CU_READY_STABLE_MS,
)
from roost.desk.cdp import CdpReplyError
from roost.desk.page_geometry import CdpSender

if TYPE_CHECKING:
    from roost.desk.page_targets import PageDriver

ReadyWord = Literal["ready", "still changing"]
READY_WORLD = "roost-ready"
# A grey level change under this is JPEG noise, not a change on the page.
_PIXEL_NOISE = 24
_MS = 1000.0
# [readyState, ms since the last resource finished (or the load ended)]; reduce() keeps a huge page off the stack.
_LIFECYCLE_EXPRESSION = (
    "(() => { const ends = performance.getEntriesByType('resource').map(e => e.responseEnd);"
    " const nav = performance.getEntriesByType('navigation')[0]; if (nav) ends.push(nav.loadEventEnd);"
    " const last = ends.reduce((a, b) => (b > a ? b : a), 0);"
    " return [document.readyState, performance.now() - last]; })()"
)
BUSY_SELECTOR = (
    '[aria-busy="true"], [role="progressbar"], progress, [class*="skeleton"], [class*="spinner"]'
)
_BUSY_CHECK_MAX = 50            # a page with more marks than this is busy whatever their boxes say
_COMPLETE = "complete"


@dataclass(frozen=True)
class LifecycleView:
    navigating: bool
    idle_since_ms: float | None     # how long the network has been quiet; None while unknown


NOT_READY = LifecycleView(navigating=True, idle_since_ms=None)


def _probe(jpeg: bytes) -> Image.Image:
    with Image.open(io.BytesIO(jpeg)) as image:
        return image.convert("L").resize((CU_READY_PROBE_W, CU_READY_PROBE_H))


def probes_differ(a: bytes, b: bytes) -> float:
    """The share of probe pixels (0..1) whose grey level moved more than JPEG noise does."""
    diff = ImageChops.difference(_probe(a), _probe(b))
    changed = sum(count for level, count in enumerate(diff.histogram()) if level > _PIXEL_NOISE)
    return changed / (CU_READY_PROBE_W * CU_READY_PROBE_H)


def ready_now(view: LifecycleView, busy: int, diff: float | None) -> bool:
    return (not view.navigating and view.idle_since_ms is not None and view.idle_since_ms >= CU_READY_STABLE_MS
            and busy == 0 and diff is not None and diff <= CU_READY_DIFF_MAX)


async def wait_ready(page: "PageDriver", timeout_s: float, *, clock: Callable[[], float],
                     sleep: Callable[[float], Awaitable[None]]) -> ReadyWord:
    """Poll until the page is ready or ``timeout_s`` has passed on ``clock`` (seconds)."""
    started = clock()
    while True:
        first = await page.screenshot(probe=True)
        await sleep(CU_READY_STABLE_MS / _MS)
        second = await page.screenshot(probe=True)
        if ready_now(await page.lifecycle(), await page.busy_marks(), probes_differ(first, second)):
            return "ready"
        if clock() - started >= timeout_s:
            return "still changing"
        await sleep(CU_READY_POLL_MS / _MS)


async def _isolated_value(client: CdpSender, session_id: str, expression: str) -> object:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = (tree.get("result") or {}).get("frameTree", {}).get("frame", {}).get("id")
    if not isinstance(frame_id, str):
        return None
    world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": READY_WORLD},
                              session_id=session_id)
    context_id = (world.get("result") or {}).get("executionContextId")
    if not isinstance(context_id, int):
        return None
    evaluated = await client.send("Runtime.evaluate", {"expression": expression, "contextId": context_id,
                                                       "returnByValue": True}, session_id=session_id)
    return (evaluated.get("result") or {}).get("result", {}).get("value")


async def read_lifecycle(client: CdpSender, session_id: str) -> LifecycleView:
    """Navigating or not, and how long the network has been quiet. Anything unreadable is "not ready"."""
    try:
        value = await _isolated_value(client, session_id, _LIFECYCLE_EXPRESSION)
    except CdpReplyError:
        return NOT_READY                     # a navigation tore the world down mid-read
    if not (isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
            and isinstance(value[1], (int, float))):
        return NOT_READY
    return LifecycleView(navigating=value[0] != _COMPLETE, idle_since_ms=max(float(value[1]), 0.0))


async def count_busy_marks(client: CdpSender, session_id: str, viewport_w: float, viewport_h: float) -> int:
    """Busy marks with a box inside the viewport, found by Chromium's selector engine (no page script)."""
    try:
        document = await client.send("DOM.getDocument", {"depth": 1}, session_id=session_id)
        root = (document.get("result") or {}).get("root", {}).get("nodeId")
        if not isinstance(root, int):
            return 0
        found = await client.send("DOM.querySelectorAll", {"nodeId": root, "selector": BUSY_SELECTOR},
                                  session_id=session_id)
        node_ids = list((found.get("result") or {}).get("nodeIds") or ())
        if len(node_ids) > _BUSY_CHECK_MAX:
            return len(node_ids)
        return sum([await _shows(client, session_id, n, viewport_w, viewport_h) for n in node_ids])
    finally:
        try:
            await client.send("DOM.disable", {}, session_id=session_id)
        except CdpReplyError:
            pass


async def _shows(client: CdpSender, session_id: str, node_id: int, width: float, height: float) -> bool:
    try:
        reply = await client.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)
    except CdpReplyError:
        return False                         # display: none
    quad = ((reply.get("result") or {}).get("model") or {}).get("border") or []
    if len(quad) != 8:
        return False
    xs, ys = quad[0::2], quad[1::2]
    return max(xs) > 0 and max(ys) > 0 and min(xs) < width and min(ys) < height and max(xs) > min(xs)
