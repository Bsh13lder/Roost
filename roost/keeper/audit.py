"""Keeper audit log — JSON lines at ``<database_dir>/keeper-audit.log``.

One line per decision: ``action``, ``bot_id``, ``result`` and a UTC
timestamp, plus (Mac file API only) a ``grant_id`` and a ``size``, or (computer
input only) the ``verb`` (click, move, key, type, scroll, open; never the text) and, for ``open``,
the app id. Deliberately
narrow — callers pass only those fields, so a ``cdp_token``, the ``keeper_secret``,
a file name or a path can never end up in this file by accident (there's no
parameter to put one in).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self, action: str, bot_id: str, result: str, *, grant_id: str | None = None, size: int | None = None,
        verb: str | None = None, app: str | None = None,
    ) -> None:
        entry: dict[str, object] = {
            "action": action,
            "bot_id": bot_id,
            "result": result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if grant_id is not None:
            entry["grant_id"] = grant_id
        if size is not None:
            entry["size"] = size
        if verb is not None:
            entry["verb"] = verb
        if app is not None:
            entry["app"] = app
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
