"""Rung 1 of the stuck ladder and ask_for_help's arguments (stuck flow, Task 4).

Split out of ``roost/talk/tool_runner.py`` so the runner stays a dispatcher.
Nothing here clicks, types or solves anything (design §1). It reads the page
the bot's own browser already loaded. For a ``challenge`` it waits, then
repeats the same call once (R4): ``open_page(url)`` again, or ``read_page()``
again, never a reload. The wait is passed in by the caller, so tests patch
``roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS``: ``tool_runner`` is the
module that reads the constant, and this module only receives the seconds. When
the user takes control during the wait, it ends at once (``ControlLock.wait_taken``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import STUCK_REASON_MAX_CHARS
from roost.desk import PageText
from roost.desk.control import ControlLock
from roost.desk.stuck import Block, detect_block
from roost.records.tool_text import ToolText

Fetch = Callable[[], Awaitable[PageText]]
Announce = Callable[[str], Awaitable[None]]
HandsTaken = Callable[[], bool]


class AskForHelpArgs(BaseModel):
    """ask_for_help's arguments. The reason is kept as plain text (the card shows it as text, never HTML)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    reason: ToolText = Field(min_length=1, max_length=STUCK_REASON_MAX_CHARS)
    suggest_main_browser: bool = False


@dataclass(frozen=True)
class Checked:
    """The page a browser call ends with, and the block it shows (``None``: the page is fine)."""

    page: PageText
    block: Block | None


async def check_page(page: PageText, fetch: Fetch, *, wait_seconds: float, announce: Announce,
                     hands_taken: HandsTaken, control: ControlLock | None = None, bot_id: str = "") -> Checked:
    """Rung 1. A challenge gets one wait and one repeat of the same call. A sign-in
    page, a code check or a refusal gets neither. If the user took control, before
    or during the wait, the repeat is skipped (Review Focus 2): the bot never
    navigates under the user's hands, and the block stands. Taking control also
    ends the wait at once, so the card opens without the rest of the seconds (I7)."""
    block = detect_block(page)
    if block is None or block.reason != "challenge":
        return Checked(page, block)
    await announce(f"waiting for {block.host} to let me in")
    if control is None:
        await asyncio.sleep(wait_seconds)
    elif await control.wait_taken(bot_id, wait_seconds):
        return Checked(page, block)
    if hands_taken():
        return Checked(page, block)
    again = await fetch()
    return Checked(again, detect_block(again))
