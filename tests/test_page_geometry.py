"""C3 Task 5: viewport points to screen pixels, and the window's geometry read in an isolated world."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from roost.computer_use.models import Box
from roost.desk.page_geometry import (
    GEOMETRY_WORLD,
    GeometryUnreadable,
    WindowGeometry,
    read_geometry,
    viewport_rect,
    viewport_to_screen,
)

# A Chromium window at (0, 0), 1280x800 outside, with an 87 px toolbar and a 2 px border on each side.
GEO = WindowGeometry(left=0, top=0, outer_w=1280, outer_h=800, inner_w=1276, inner_h=711)
SESSION = "session-1"


def test_viewport_point_maps_below_the_toolbar():
    # border = (1280 - 1276) // 2 = 2; toolbar = (800 - 711) - 2 = 87
    assert viewport_to_screen((0, 0), GEO) == (2, 87)
    assert viewport_to_screen((100, 50), GEO) == (102, 137)
    moved = WindowGeometry(left=40, top=30, outer_w=800, outer_h=600, inner_w=800, inner_h=520)
    assert viewport_to_screen((10, 10), moved) == (50, 120)


def test_a_point_that_falls_off_the_screen_is_refused_never_clamped():
    # Security review (b): clamping would click another spot of the page than the one that was judged.
    off = WindowGeometry(left=900, top=500, outer_w=800, outer_h=600, inner_w=800, inner_h=520)
    with pytest.raises(ValueError):
        viewport_to_screen((799, 519), off)
    assert viewport_to_screen((10, 10), off) == (910, 590)
    left_off = WindowGeometry(left=-300, top=0, outer_w=800, outer_h=600, inner_w=800, inner_h=520)
    with pytest.raises(ValueError):
        viewport_to_screen((10, 10), left_off)


def test_the_window_rect_is_what_roost_input_checks():
    moved = WindowGeometry(left=40, top=30, outer_w=800, outer_h=600, inner_w=800, inner_h=520)
    assert moved.window_rect == (40, 30, 800, 600)


@pytest.mark.parametrize("point", [(-1, 0), (0, -1), (1276, 0), (0, 711), (5000, 5000)])
def test_points_outside_the_viewport_raise(point):
    with pytest.raises(ValueError):
        viewport_to_screen(point, GEO)


def test_the_viewport_rect_is_on_the_screen():
    assert viewport_rect(GEO) == Box(x=2, y=87, width=1276, height=711)


class FakeCdp:
    """Answers the geometry calls and records each one (method, params, session)."""

    def __init__(self, *, window_state: str = "normal", sizes: Any = (1280, 800, 1276, 711)) -> None:
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []
        self.window_state = window_state
        self.sizes = sizes

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params, session_id))
        if method == "Browser.getWindowForTarget":
            bounds = {"left": 10, "top": 20, "width": 1280, "height": 800, "windowState": self.window_state}
            return {"result": {"windowId": 7, "bounds": bounds}}
        if method == "Browser.setWindowBounds":
            self.window_state = params["bounds"]["windowState"]
            return {"result": {}}
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "frame-main"}}}}
        if method == "Page.createIsolatedWorld":
            return {"result": {"executionContextId": 77}}
        if method == "Runtime.evaluate":
            return {"result": {"result": {"type": "object", "value": list(self.sizes)}}}
        raise AssertionError(f"unexpected CDP call {method}")


def test_geometry_is_read_in_an_isolated_world():
    cdp = FakeCdp()
    geo = asyncio.run(read_geometry(cdp, SESSION))
    assert geo == WindowGeometry(left=10, top=20, outer_w=1280, outer_h=800, inner_w=1276, inner_h=711)
    world = next(params for method, params, _ in cdp.calls if method == "Page.createIsolatedWorld")
    assert world["worldName"] == GEOMETRY_WORLD == "roost-geometry"
    assert world["frameId"] == "frame-main"
    evaluate = next(params for method, params, _ in cdp.calls if method == "Runtime.evaluate")
    assert evaluate["contextId"] == 77 and evaluate["returnByValue"] is True
    assert all(session == SESSION for _, _, session in cdp.calls)


def test_a_minimized_window_is_restored_before_its_geometry_is_read():
    cdp = FakeCdp(window_state="minimized")
    asyncio.run(read_geometry(cdp, SESSION))
    methods = [method for method, _, _ in cdp.calls]
    restore = methods.index("Browser.setWindowBounds")
    assert restore < methods.index("Runtime.evaluate")
    params = cdp.calls[restore][1]
    assert params == {"windowId": 7, "bounds": {"windowState": "normal"}}
    assert methods.count("Browser.getWindowForTarget") == 2


def test_a_window_that_stays_minimized_is_unreadable():
    class Stubborn(FakeCdp):
        async def send(self, method, params=None, session_id=None):
            if method == "Browser.setWindowBounds":
                self.calls.append((method, params or {}, session_id))
                return {"result": {}}
            return await super().send(method, params, session_id)

    with pytest.raises(GeometryUnreadable):
        asyncio.run(read_geometry(Stubborn(window_state="minimized"), SESSION))


@pytest.mark.parametrize("sizes", [(1280, 800, 1276), ("1280", 800, 1276, 711), (1280, 800, 0, 711),
                                   (1280, 800, 1300, 711), None])
def test_odd_sizes_are_unreadable(sizes):
    with pytest.raises(GeometryUnreadable):
        asyncio.run(read_geometry(FakeCdp(sizes=sizes if sizes is not None else ()), SESSION))


def test_the_window_size_comes_from_its_bounds_not_brave_s_outer_size():
    """Live on a JWM-framed Brave (2026-10-24): bounds 1274x708 at (3, 30), page 1274x627, but outerWidth and
    outerHeight said 1276x633. The outer size made a rect roost-input never matched and put clicks ~75 px high."""

    class Framed(FakeCdp):
        async def send(self, method, params=None, session_id=None):
            if method == "Browser.getWindowForTarget":
                self.calls.append((method, params or {}, session_id))
                bounds = {"left": 3, "top": 30, "width": 1274, "height": 708, "windowState": "normal"}
                return {"result": {"windowId": 7, "bounds": bounds}}
            return await super().send(method, params, session_id)

    geo = asyncio.run(read_geometry(Framed(sizes=(1276, 633, 1274, 627)), SESSION))
    assert geo.window_rect == (3, 30, 1274, 708)
    assert viewport_to_screen((0, 0), geo) == (3, 111)


def test_bounds_without_a_size_fall_back_to_the_outer_size():
    class Sizeless(FakeCdp):
        async def send(self, method, params=None, session_id=None):
            if method == "Browser.getWindowForTarget":
                self.calls.append((method, params or {}, session_id))
                return {"result": {"windowId": 7, "bounds": {"left": 0, "top": 0, "windowState": "normal"}}}
            return await super().send(method, params, session_id)

    geo = asyncio.run(read_geometry(Sizeless(), SESSION))
    assert (geo.outer_w, geo.outer_h) == (1280, 800)
