"""Refuse to touch a database while the program that owns it is running."""

from __future__ import annotations

import re
import socket
from collections.abc import Iterable
from pathlib import Path

from roost.migrate.lazyclaw.constants import (
    LAZYCLAW_CONFIG_RELATIVE, LAZYCLAW_DEFAULT_PORT, LAZYCLAW_PORT_PATTERN, LOOPBACK, PORT_PROBE_TIMEOUT_S,
)

ROOST_RUNNING_MESSAGE = ("Roost is running (its gateway or keeper is listening). Stop Roost first, then run this "
                         "again: --apply and --undo must not change the database while Roost is using it.")


def port_open(port: int, host: str = LOOPBACK) -> bool:
    """True when something accepts a TCP connection on ``host:port``."""
    try:
        with socket.create_connection((host, port), timeout=PORT_PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def any_port_open(ports: Iterable[int]) -> bool:
    return any(port_open(p) for p in ports)


def lazyclaw_ports(source: Path) -> tuple[int, ...]:
    """The port LazyClaw serves on, read (read only) from its source config next to the database.

    ``source`` is ``<repo>/data/lazyclaw.db``; the config is ``<repo>/lazyclaw/config.py``. When it is
    not there or has no port line, LazyClaw's documented default is used.
    """
    for root in (source.resolve().parent.parent, source.resolve().parent):
        try:
            text = (root / LAZYCLAW_CONFIG_RELATIVE).read_text()
        except OSError:
            continue
        found = re.search(LAZYCLAW_PORT_PATTERN, text)
        if found:
            return (int(found.group(1)),)
    return (LAZYCLAW_DEFAULT_PORT,)


def wal_in_use(source: Path) -> bool:
    """A non-empty ``-wal`` file beside the database means a process still has it open."""
    try:
        return source.with_name(source.name + "-wal").stat().st_size > 0
    except OSError:
        return False
