"""Desk directory resolution — every path the keeper touches on disk for a
bot is built here, and every one of them is asserted to stay inside
``desks_dir``.

A bot id is attacker-reachable surface: it arrives as a URL path segment
(``/desks/{bot_id}/...``) and the keeper's own route validation
(``roost/keeper/app.py``) already rejects anything that isn't a UUID4.
This module is the second, independent line of defense — even if a
malformed or crafted id ever reached this layer, it still cannot resolve
to a path outside the desks root.
"""

from __future__ import annotations

from pathlib import Path

_BROWSER_SUBDIR = "browser"
_DOWNLOADS_SUBDIR = "downloads"
_WORKSPACE_SUBDIR = "workspace"


class BotIdOutsideDesksDir(ValueError):
    """Raised when a bot id would resolve to a path outside ``desks_dir``."""


def desk_dir(desks_dir: Path, bot_id: str) -> Path:
    """Return ``<desks_dir>/<bot_id>``, resolved, or raise if that escapes
    ``desks_dir`` (``../..`` traversal, an absolute path, etc.)."""
    desks_dir_resolved = desks_dir.resolve()
    candidate = (desks_dir_resolved / bot_id).resolve()
    if candidate != desks_dir_resolved and desks_dir_resolved not in candidate.parents:
        raise BotIdOutsideDesksDir(
            f"bot id {bot_id!r} resolves to {candidate}, outside desks_dir {desks_dir_resolved}"
        )
    return candidate


def browser_dir(desks_dir: Path, bot_id: str) -> Path:
    return desk_dir(desks_dir, bot_id) / _BROWSER_SUBDIR


def downloads_dir(desks_dir: Path, bot_id: str) -> Path:
    return desk_dir(desks_dir, bot_id) / _DOWNLOADS_SUBDIR


def workspace_dir(desks_dir: Path, bot_id: str) -> Path:
    return desk_dir(desks_dir, bot_id) / _WORKSPACE_SUBDIR
