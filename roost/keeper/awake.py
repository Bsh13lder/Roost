"""Keep the Mac awake while the keeper runs (owner decision 2026-10-23: Roost, its routines and the phone's
link stay up while the Mac is on).

macOS's own ``caffeinate`` holds the assertions: ``-i`` no idle sleep (on battery too), ``-s`` no system sleep
on power, and ``-w <pid>`` lets go by itself when the keeper's process ends. The display may still sleep.
Closing the lid on battery still sleeps the Mac; that is the owner's own power setting to change."""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Callable

logger = logging.getLogger(__name__)

CAFFEINATE = "/usr/bin/caffeinate"

Spawn = Callable[..., Any]


def awake_argv(pid: int) -> list[str]:
    return [CAFFEINATE, "-i", "-s", "-w", str(pid)]


def keep_awake(pid: int, *, spawn: Spawn = subprocess.Popen) -> Any | None:
    """Start caffeinate for ``pid``; None (and a log line) when it can't start."""
    try:
        return spawn(awake_argv(pid), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as exc:
        logger.warning("could not keep the Mac awake (stay awake not held): %s", exc)
        return None
