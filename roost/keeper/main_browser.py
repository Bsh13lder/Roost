"""Open in your main Brave: the keeper side (stuck flow, piece A; design §3,
D-A3/D-A4, R8).

This is the keeper's only action on the user's own Brave. It runs the fixed argv
``MAIN_BROWSER_OPEN_ARGV + (url,)`` (``/usr/bin/open -a "Brave Browser" <url>``)
as an argument list, never through a shell. There is no debug port, no profile
access and no automation. ``open`` hands the address to Launch Services, and
Brave opens it in a tab like any link the user clicked.

The address that reaches ``MainBrowserOpener.open`` has already passed
``check_url`` in the route (``roost/keeper/app.py``). So it is always an
``http``/``https`` URL, and it can never start with ``-`` and be read by
``open`` as a flag.

``runner`` is injectable, the same pattern as ``roost.keeper.workspaces.Runner``.
Tests can then assert on the exact argv and never launch a real browser.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable, Sequence

from roost.constants import MAIN_BROWSER_OPEN_ARGV, MAIN_BROWSER_OPEN_TIMEOUT_S


class MainBrowserOpenError(RuntimeError):
    """Raised when ``open`` could not start, timed out or exited non-zero. The route answers a
    fixed 500 ``"failed to open the main browser"``. The message never carries the address."""


# (argv, timeout in seconds) -> the process's exit code. Raises
# asyncio.TimeoutError on a timeout, and OSError when the process can't start.
Runner = Callable[[Sequence[str], float], Awaitable[int]]


async def _run_open(argv: Sequence[str], timeout_s: float) -> int:
    """The real runner. It runs an argv list (no shell), discards the output, and kills the process on a timeout."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        return await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        raise


class MainBrowserOpener:
    """Opens one checked address in the user's own Brave. ``create_app`` builds one, as
    ``app.state.main_browser``. Tests replace it with one that has a fake ``runner``."""

    def __init__(self, *, runner: Runner | None = None) -> None:
        self._run: Runner = runner if runner is not None else _run_open

    async def open(self, url: str) -> None:
        argv = (*MAIN_BROWSER_OPEN_ARGV, url)
        try:
            exit_code = await self._run(argv, MAIN_BROWSER_OPEN_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise MainBrowserOpenError(f"open did not finish within {MAIN_BROWSER_OPEN_TIMEOUT_S} s") from exc
        except OSError as exc:
            raise MainBrowserOpenError(f"open could not start: {exc.strerror or type(exc).__name__}") from exc
        if exit_code != 0:
            raise MainBrowserOpenError(f"open exited with code {exit_code}")
