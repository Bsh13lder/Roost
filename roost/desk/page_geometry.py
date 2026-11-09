"""Viewport points to screen pixels on a bot's Linux computer (C3 Task 5, Design meets code 5).

The model, the summary and the resolver all speak viewport CSS pixels (scale 1: Xvnc 1280x800, device scale 1).
Only ``viewport_to_screen`` turns one into a screen pixel for the keeper's input route and the ``computer_pointer``
event: the window's left edge plus half its side borders, and its top plus the toolbar above the page.

The computer is a desktop with movable windows (amendment 2026-10-21), so ``read_geometry`` is called before every
act and every look: ``Browser.getWindowForTarget`` gives the window's place (a minimized window is restored
first), and the outer and inner sizes are read with ``Runtime.evaluate`` in an **isolated world** named
``roost-geometry``, so a page cannot fake them by redefining ``innerWidth`` in its own world.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from roost.computer_use.models import Box
from roost.constants import CU_VIEW_MAX_H, CU_VIEW_MAX_W

GEOMETRY_WORLD = "roost-geometry"
_SIZES_EXPRESSION = "[outerWidth, outerHeight, innerWidth, innerHeight]"
_MINIMIZED = "minimized"
_UNREADABLE = "The browser window's size could not be read."
_STILL_MINIMIZED = "The browser window is minimized and could not be restored."
_OUTSIDE = "That point is outside the page."
_OFF_SCREEN = "That point of the page is off the screen."


class GeometryUnreadable(RuntimeError):
    """The window's place or sizes were missing, odd, or the window stayed minimized."""


class CdpSender(Protocol):
    async def send(self, method: str, params: dict[str, Any] | None = None,
                   session_id: str | None = None) -> dict: ...


@dataclass(frozen=True)
class WindowGeometry:
    """Chromium's window on the screen (screen pixels) and its page area's size (viewport CSS pixels)."""

    left: int
    top: int
    outer_w: int
    outer_h: int
    inner_w: int
    inner_h: int

    @property
    def border(self) -> int:
        return (self.outer_w - self.inner_w) // 2

    @property
    def window_rect(self) -> tuple[int, int, int, int]:
        """The window's left, top, width and height on the screen: ``roost-input`` acts only in the Chromium window
        that matches it."""
        return self.left, self.top, self.outer_w, self.outer_h

    @property
    def page_top(self) -> int:
        """Screen y of the viewport's top edge: below the tab strip and the address bar."""
        return self.top + (self.outer_h - self.inner_h) - self.border


def viewport_to_screen(point: tuple[int, int], geo: WindowGeometry) -> tuple[int, int]:
    """The screen pixel under viewport ``point``. A point outside the viewport, or one that falls off the screen
    (a window moved partly off it), is a ``ValueError``: never clamped onto another spot of the page."""
    x, y = point
    if not (0 <= x < geo.inner_w and 0 <= y < geo.inner_h):
        raise ValueError(_OUTSIDE)
    screen_x = geo.left + geo.border + x
    screen_y = geo.page_top + y
    if not (0 <= screen_x < CU_VIEW_MAX_W and 0 <= screen_y < CU_VIEW_MAX_H):
        raise ValueError(_OFF_SCREEN)
    return screen_x, screen_y


def viewport_rect(geo: WindowGeometry) -> Box:
    """The viewport's rectangle in screen pixels."""
    return Box(x=geo.left + geo.border, y=geo.page_top, width=geo.inner_w, height=geo.inner_h)


async def _window(client: CdpSender, session_id: str) -> tuple[int, dict[str, Any]]:
    reply = await client.send("Browser.getWindowForTarget", {}, session_id=session_id)
    result = reply.get("result", {})
    window_id, bounds = result.get("windowId"), result.get("bounds")
    if not isinstance(window_id, int) or not isinstance(bounds, dict):
        raise GeometryUnreadable(_UNREADABLE)
    return window_id, bounds


async def _restored_bounds(client: CdpSender, session_id: str) -> dict[str, Any]:
    """The window's bounds, restoring a minimized window first (it would otherwise take no clicks)."""
    window_id, bounds = await _window(client, session_id)
    if bounds.get("windowState") != _MINIMIZED:
        return bounds
    await client.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "normal"}},
                      session_id=session_id)
    _, bounds = await _window(client, session_id)
    if bounds.get("windowState") == _MINIMIZED:
        raise GeometryUnreadable(_STILL_MINIMIZED)
    return bounds


async def _sizes(client: CdpSender, session_id: str) -> list[int]:
    tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
    frame_id = tree.get("result", {}).get("frameTree", {}).get("frame", {}).get("id")
    if not isinstance(frame_id, str):
        raise GeometryUnreadable(_UNREADABLE)
    world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": GEOMETRY_WORLD},
                              session_id=session_id)
    context_id = world.get("result", {}).get("executionContextId")
    if not isinstance(context_id, int):
        raise GeometryUnreadable(_UNREADABLE)
    evaluated = await client.send("Runtime.evaluate", {"expression": _SIZES_EXPRESSION, "contextId": context_id,
                                                       "returnByValue": True}, session_id=session_id)
    value = evaluated.get("result", {}).get("result", {}).get("value")
    if not isinstance(value, list) or len(value) != 4 or not all(type(v) is int and v > 0 for v in value):
        raise GeometryUnreadable(_UNREADABLE)
    return value


def _bounds_size(bounds: dict[str, Any]) -> tuple[int, int] | None:
    """The window's size from CDP's bounds. Brave framed by the window manager reports a wrong
    ``outerWidth``/``outerHeight`` (1276x633 for a 1274x708 window, 2026-10-24), so the bounds win when present."""
    width, height = bounds.get("width"), bounds.get("height")
    if type(width) is int and type(height) is int and width > 0 and height > 0:
        return width, height
    return None


async def read_geometry(client: CdpSender, session_id: str) -> WindowGeometry:
    """Where Chromium's window is and how big its page is, read fresh (before every act and look)."""
    bounds = await _restored_bounds(client, session_id)
    left, top = bounds.get("left"), bounds.get("top")
    if type(left) is not int or type(top) is not int:
        raise GeometryUnreadable(_UNREADABLE)
    js_outer_w, js_outer_h, inner_w, inner_h = await _sizes(client, session_id)
    outer_w, outer_h = _bounds_size(bounds) or (js_outer_w, js_outer_h)
    if inner_w > outer_w or inner_h > outer_h:
        raise GeometryUnreadable(_UNREADABLE)
    return WindowGeometry(left=left, top=top, outer_w=outer_w, outer_h=outer_h, inner_w=inner_w, inner_h=inner_h)
