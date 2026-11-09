"""The folder picker: the keeper's only process in the Mac file API.

It runs ``MAC_PICK_ARGV`` exactly: a fixed argv through ``asyncio.create_subprocess_exec``, no
shell, and no text from any user in the script. The answer is a path the user chose in macOS's
own dialog; it still has to pass ``check_folder``'s deny list. ``runner`` is injectable (the
``main_browser.py`` pattern) so tests never open a dialog."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable, Sequence

from roost.constants import MAC_PICK_ARGV, MAC_PICK_TIMEOUT_S
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.ops_read import check_folder

_CANCEL_EXIT_CODE = 1   # osascript: "User canceled"

# (argv, timeout in seconds) -> (exit code, stdout). Raises asyncio.TimeoutError on a timeout and
# OSError when the process can't start.
Runner = Callable[[Sequence[str], float], Awaitable[tuple[int, bytes]]]


class FolderPickError(RuntimeError):
    """The dialog could not run or did not finish. The message never carries a path."""


async def _run_osascript(argv: Sequence[str], timeout_s: float) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        raise
    return proc.returncode if proc.returncode is not None else -1, out


class FolderPicker:
    def __init__(self, runner: Runner | None = None, *, home: str) -> None:
        self._run: Runner = runner if runner is not None else _run_osascript
        self._home = home

    async def pick(self) -> str | None:
        """The chosen folder (resolved and checked), or ``None`` when the user cancelled."""
        try:
            code, out = await self._run(tuple(MAC_PICK_ARGV), MAC_PICK_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise FolderPickError("the folder dialog did not finish in time") from None
        except OSError:
            raise FolderPickError("the folder dialog could not start") from None
        if code == _CANCEL_EXIT_CODE:
            return None
        if code != 0:
            raise FolderPickError("the folder dialog failed")
        try:
            text = out.decode("utf-8")
        except UnicodeDecodeError:
            raise FolderPickError("the folder dialog answered badly") from None
        text = text[:-1] if text.endswith("\n") else text
        if not text:
            raise MacFsError("bad_path")
        return str(check_folder(self._home, text)["resolved"])
