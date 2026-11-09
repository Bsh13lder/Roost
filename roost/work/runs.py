"""``RunLog`` — one row per run: the daily cap counts these (spec §4.2,
A14), and a crash leaves ``outcome IS NULL`` for boot to close as
``interrupted``. Days are local days; every timestamp is stored
as UTC ISO-8601 with ``+00:00``, so string comparison is time order."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Mapping

from roost.config import Config
from roost.db.connection import db_session
from roost.timezones import local_tz
from roost.work.models import RunOutcome

# A helper's run id is its parent's id and "-h<n>" (roost/helpers/tools.py); a parent's id is a UUID (hex only).
HELPER_RUN_GLOB = "*-h[0-9]*"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _midnight(local: datetime) -> datetime:
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def madrid_day_start_utc(now: datetime) -> str:
    return _midnight(now.astimezone(local_tz())).astimezone(timezone.utc).isoformat()


def madrid_today(now: datetime) -> str:
    return now.astimezone(local_tz()).date().isoformat()


def seconds_until_madrid_midnight(now: datetime) -> float:
    tomorrow = _midnight(now.astimezone(local_tz()) + timedelta(days=1))
    return (tomorrow.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds()


class RunLog:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def start(self, user_id: str, bot_id: str, thread_id: str, run_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO runs (id, user_id, bot_id, thread_id, started_at) VALUES (?,?,?,?,?)",
                (run_id, user_id, bot_id, thread_id, _now_iso()),
            )
            await db.commit()

    async def finish(self, user_id: str, run_id: str, outcome: RunOutcome) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE runs SET outcome = ?, ended_at = ? WHERE id = ? AND user_id = ? AND outcome IS NULL",
                (outcome, _now_iso(), run_id, user_id),
            )
            await db.commit()

    async def count_today(self, user_id: str, bot_id: str, *, now: datetime | None = None) -> int:
        """The bot's runs today (local), its helpers' runs left out (owner, 2026-11-03: they don't count)."""
        moment = now if now is not None else datetime.now(timezone.utc)
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM runs WHERE user_id = ? AND bot_id = ? AND started_at >= ? AND id NOT GLOB ?",
                (user_id, bot_id, madrid_day_start_utc(moment), HELPER_RUN_GLOB),
            )).fetchone()
        return int(row[0])

    async def last_active(self, user_id: str) -> Mapping[str, str]:
        """When each of the user's bots last started a run (UTC ISO)."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT bot_id, MAX(started_at) AS last FROM runs WHERE user_id = ? GROUP BY bot_id", (user_id,),
            )).fetchall()
        return MappingProxyType({row["bot_id"]: row["last"] for row in rows})

    async def close_open_on_boot(self) -> int:
        """Boot only, across users: a run still open died with the old process."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE runs SET outcome = 'interrupted', ended_at = ? WHERE outcome IS NULL", (_now_iso(),),
            )
            await db.commit()
        return cursor.rowcount
