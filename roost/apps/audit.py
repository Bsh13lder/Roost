"""One ``audit`` row per app result (docs/plans/2026-10-22-roost-install-app.md §6), with no detail: the gate's own
rows already carry the call, sealed and redacted, so the package name is never kept here."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from roost.config import Config
from roost.db.connection import db_session

AppAction = Literal["install_app", "remove_app", "reinstall_app"]
AppResult = Literal["installed", "install_failed", "removed", "remove_failed", "owner_removed", "reinstall_failed"]


class AppAudit:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def record(self, user_id: str, bot_id: str, action: AppAction, result: AppResult, *,
                     tainted: bool = False) -> None:
        decision = "never" if result.endswith("_failed") else "do"
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
                "VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                (user_id, bot_id, action, decision, datetime.now(timezone.utc).isoformat(), result, int(tainted)),
            )
            await db.commit()
