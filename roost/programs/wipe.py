"""Wipe workspace: the owner empties a bot's workspace and clears its workspace mark.

The wipe is the fixed in-container script (``file_ops_command("wipe", "")``, no argument from anyone), sent
through the desk's ``exec`` like every program call, and it waits for the bot's workspace lock so it never
lands in the middle of a program. Only a wipe that finished clears the mark."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from roost.constants import PROGRAM_WIPE_TIMEOUT_S
from roost.desk import Desk, DeskUnavailable
from roost.programs.file_ops import file_ops_command, parse_wipe
from roost.programs.marks import WorkspaceMarks
from roost.programs.wrap import UNAVAILABLE_TEXT

WIPE_FAILED_TEXT = "Couldn't wipe the workspace. Some files may be left; try again."


@dataclass(frozen=True)
class WipeOutcome:
    ok: bool
    removed: int
    text: str


async def wipe_workspace(desk: Desk, marks: WorkspaceMarks, lock: asyncio.Lock, user_id: str,
                         bot_id: str) -> WipeOutcome:
    async with lock:
        try:
            result = await desk.exec(file_ops_command("wipe", ""), timeout_s=PROGRAM_WIPE_TIMEOUT_S)
        except DeskUnavailable:
            return WipeOutcome(False, 0, UNAVAILABLE_TEXT)
        if result.exit_code != 0 or result.timed_out:
            return WipeOutcome(False, 0, WIPE_FAILED_TEXT)
        await marks.clear(user_id, bot_id)
    return WipeOutcome(True, parse_wipe(result.stderr), "")
