"""The desktop side of the screen loop (full computer, Step 1; ``docs/plans/2026-10-23-roost-full-computer.md``).

When anything but Brave is in front (the runner asks ``Desk.front_window()`` before every look and act; the
model's arguments never decide it), the bot sees the whole screen and acts anywhere on it but in Brave:

- ``desktop_look``: the whole-screen grab with every visible Brave window blacked out (its rects read before and
  after the grab, so a window that moved meanwhile is covered too) and a plain summary: no page text, no titles.
- ``screen_resolution``: a screen act's resolution: no page, no target, ``space="screen"``, class ``browsing``.
  The gate lets it through (D1); the runner keeps every loop rule (lease, budget, look first, epoch, hands).
- ``app_refusal``: ``open_app`` takes a fixed app or the exact name of a package in the bot's ``bot_apps``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from roost.apps.store import AppStore
from roost.computer_use.models import ActResolution, ActTool
from roost.computer_use.screen_grab import desktop_jpeg, grab_screen
from roost.config import Config
from roost.constants import CU_OPEN_APPS, CU_VIEW_MAX_H, CU_VIEW_MAX_W
from roost.desk import FrontWindow

Rect = tuple[int, int, int, int]

TARGET_TEXT = "Another app is in front, so there is no page to find words on. Click a point (x and y) from your last look."
LINE_BREAKS_TEXT = ("Another app is in front, and there typing goes key by key, so I typed nothing: a line break or "
                    "a tab would press Enter or Tab. Type it as one line, and use press_key for Enter or Tab.")
OUTSIDE_SCREEN_TEXT ="That point is outside the screen, so I didn't touch it."
IN_BROWSER_TEXT = ("That point is on my browser window, so I didn't touch it. To use the browser, open_app browser "
                   "and look again.")
IN_BROWSER_NOTE = "I tried several times to use a point on my browser window from the desktop. Next: tell me what to do there."
NOT_INSTALLED_TEXT = "{app} isn't installed on my computer. Ask the user to install it first (install_app)."
NO_WINDOW_TEXT = "{app} has no window to open."
WAITED_TEXT = "Screen: waited a moment. Look to see it."
SCREEN_DONE_TEXT = "{line}. Look to check what you expected."
OPENED_TEXT = "{line}. Look to see it."
SCROLLED_TEXT = "Scrolled {direction}. Look before your next click."
_FRONT_WORDS = {"brave": "the browser", "other": "another app"}


@dataclass(frozen=True)
class DesktopShot:
    image: bytes
    text: str


def desktop_summary(front: FrontWindow, blacked: int) -> str:
    """Plain facts only: the screen, what kind of window is in front, how many browser windows are blacked out."""
    lines = ["screen: desktop", f"front window: {_FRONT_WORDS[front.kind]}"]
    if blacked:
        lines.append(f"browser windows blacked out: {blacked}. To see the browser, open_app browser and look again.")
    return "\n".join(lines)


def _union(*groups: Sequence[Rect]) -> tuple[Rect, ...]:
    return tuple(dict.fromkeys(rect for group in groups for rect in group))


async def desktop_look(desk: Any, front: FrontWindow) -> DesktopShot:
    """The whole screen, Brave's windows black. ``DeskAsleep`` / ``DeskUnavailable`` / ``ScreenGrabError`` pass up."""
    before = await desk.browser_windows()
    image = await grab_screen(await desk.open_screen())
    rects = _union(before, await desk.browser_windows())
    return DesktopShot(desktop_jpeg(image, rects), desktop_summary(front, len(rects)))


def on_screen(point: tuple[int, int]) -> bool:
    return 0 <= point[0] < CU_VIEW_MAX_W and 0 <= point[1] < CU_VIEW_MAX_H


def clamp(point: tuple[int, int]) -> tuple[int, int]:
    return min(max(point[0], 0), CU_VIEW_MAX_W - 1), min(max(point[1], 0), CU_VIEW_MAX_H - 1)


def screen_center() -> tuple[int, int]:
    return CU_VIEW_MAX_W // 2, CU_VIEW_MAX_H // 2


def screen_resolution(tool: ActTool, point: tuple[int, int] | None) -> ActResolution:
    return ActResolution(tool, "", "", None, point, "", "", "browsing", space="screen")


async def app_refusal(config: Config, user_id: str, bot_id: str, app: str) -> str | None:
    """None when ``app`` may open: a fixed app, or a package this bot has installed (exact name)."""
    if app in CU_OPEN_APPS or app in await AppStore(config).packages(user_id, bot_id):
        return None
    return NOT_INSTALLED_TEXT.format(app=app)
