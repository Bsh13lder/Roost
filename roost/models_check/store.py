"""Seen models and notice dismissals (schema v20). Public facts and settings, so plaintext."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from roost.config import Config
from roost.db.connection import db_session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SeenModelStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add_new(self, models: Mapping[str, str]) -> tuple[str, ...]:
        """Remember models not seen before; return the ids that were new (an old id keeps its label)."""
        added: list[str] = []
        async with db_session(self._config) as db:
            for model_id, label in models.items():
                cursor = await db.execute(
                    "INSERT OR IGNORE INTO seen_models (model_id, label, first_seen_at) VALUES (?, ?, ?)",
                    (model_id, label, _now_iso()),
                )
                if cursor.rowcount:
                    added.append(model_id)
            await db.commit()
        return tuple(added)

    async def ids(self) -> frozenset[str]:
        return frozenset(await self.labels())

    async def labels(self) -> dict[str, str]:
        async with db_session(self._config) as db:
            rows = await (await db.execute("SELECT model_id, label FROM seen_models")).fetchall()
        return {row["model_id"]: row["label"] for row in rows}

    async def newest_undismissed(self, user_id: str) -> tuple[str, str] | None:
        """The newest seen model this user has not dismissed: (id, label), or None."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT model_id, label FROM seen_models WHERE model_id NOT IN "
                "(SELECT model_id FROM model_notice_dismissals WHERE user_id = ?) "
                "ORDER BY first_seen_at DESC, rowid DESC LIMIT 1",
                (user_id,),
            )).fetchone()
        return None if row is None else (row["model_id"], row["label"])

    async def dismiss(self, user_id: str, model_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT OR IGNORE INTO model_notice_dismissals (user_id, model_id, dismissed_at) VALUES (?, ?, ?)",
                (user_id, model_id, _now_iso()),
            )
            await db.commit()
