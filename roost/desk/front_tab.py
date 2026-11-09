"""Which tab is in front of a bot's browser (owner request 2026-10-22: the bot works with the whole browser).

The bot's tab is the tab in front: the active tab of the focused window. CDP has no field for it, and
``Target.getTargets`` lists pages in creation order (newest first) whichever one is in front, so its order is
only a tie-break here, never the answer. Each page is asked instead, in an **isolated world** named
``roost-front-tab`` so a page cannot fake the answer by redefining anything in its own world:

- ``document.visibilityState === "visible"``: the active tab of its window (a background tab is "hidden");
- ``document.hasFocus()``: that window is the focused one.

Proved on a real ``roost-computer:dev`` (Brave, Xvnc, JWM) with the owner's own keys sent through xdotool:
after Ctrl+T, Ctrl+1, Ctrl+9, Ctrl+N and ``Target.activateTarget`` the front tab alone read
``["visible", true]``, a second window's active tab read ``["visible", false]``, and the target order never
changed. At boot no window has focus, so the visible tab is taken; a page that cannot be read (a browser page,
a tab closing meanwhile) counts as hidden. Each probe attaches its own session and detaches it again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Protocol

from roost.desk.cdp import CdpReplyError

logger = logging.getLogger(__name__)

FRONT_WORLD = "roost-front-tab"
_FRONT_EXPRESSION = "[document.visibilityState === 'visible', document.hasFocus()]"
_PAGE = "page"
_SKIPPED_PREFIXES = ("devtools://",)
_RANK_FRONT, _RANK_VISIBLE, _RANK_HIDDEN = 2, 1, 0


class CdpSender(Protocol):
    async def send(self, method: str, params: dict[str, Any] | None = None,
                   session_id: str | None = None) -> dict: ...


@dataclass(frozen=True)
class Tab:
    target_id: str
    url: str
    title: str
    visible: bool = False
    focused: bool = False

    @property
    def rank(self) -> int:
        if self.visible and self.focused:
            return _RANK_FRONT
        return _RANK_VISIBLE if self.visible else _RANK_HIDDEN


async def page_tabs(client: CdpSender) -> tuple[Tab, ...]:
    """The browser's pages in ``Target.getTargets`` order, unread. DevTools pages and workers are left out."""
    reply = await client.send("Target.getTargets")
    infos = (reply.get("result") or {}).get("targetInfos") or []
    return tuple(
        Tab(target_id=str(info.get("targetId", "")), url=str(info.get("url", "")), title=str(info.get("title", "")))
        for info in infos
        if info.get("type") == _PAGE and info.get("targetId")
        and not str(info.get("url", "")).startswith(_SKIPPED_PREFIXES)
    )


async def front_tab(client: CdpSender) -> Tab | None:
    """The tab in front, or None when no page is open. Ties keep ``Target.getTargets`` order."""
    tabs = [await _read(client, tab) for tab in await page_tabs(client)]
    if not tabs:
        return None
    return max(tabs, key=lambda tab: tab.rank)          # ``max`` keeps the first of equals


async def _read(client: CdpSender, tab: Tab) -> Tab:
    try:
        attached = await client.send("Target.attachToTarget", {"targetId": tab.target_id, "flatten": True})
    except CdpReplyError as exc:
        logger.warning("a tab could not be read for the front tab: %s", exc)
        return tab
    session_id = (attached.get("result") or {}).get("sessionId")
    if not isinstance(session_id, str):
        return tab
    try:
        value = await _isolated_value(client, session_id)
    except CdpReplyError:
        value = None                                    # a browser page or a closing tab: hidden
    finally:
        await _detach(client, session_id)
    if not (isinstance(value, list) and len(value) == 2):
        return tab
    return replace(tab, visible=value[0] is True, focused=value[1] is True)


async def _isolated_value(client: CdpSender, session_id: str) -> object:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = (tree.get("result") or {}).get("frameTree", {}).get("frame", {}).get("id")
    if not isinstance(frame_id, str):
        return None
    world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": FRONT_WORLD},
                              session_id=session_id)
    context_id = (world.get("result") or {}).get("executionContextId")
    if not isinstance(context_id, int):
        return None
    evaluated = await client.send("Runtime.evaluate", {"expression": _FRONT_EXPRESSION, "contextId": context_id,
                                                       "returnByValue": True}, session_id=session_id)
    return (evaluated.get("result") or {}).get("result", {}).get("value")


async def _detach(client: CdpSender, session_id: str) -> None:
    try:
        await client.send("Target.detachFromTarget", {"sessionId": session_id})
    except CdpReplyError as exc:
        logger.warning("a front-tab probe session could not be detached: %s", exc)
