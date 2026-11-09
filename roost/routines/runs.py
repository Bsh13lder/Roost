"""``RoutineRunStore``: the run log (schema v25 ``routine_runs``).

``note`` is user content, ``enc:v2`` under ``routine_runs:note``; ids, slot times, states and counts stay
plaintext. Every query names ``user_id``. A slot may hold one row per state (a ``missed`` row and the one run
that followed it), and the unique index refuses a second row for the same slot and state."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.constants import ROUTINE_RUNS_PAGE, RUN_LOG_RETENTION_DAYS
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.routines.models import FINISHED_STATES, OPEN_STATES, Clock, Routine, RoutineRun, RunState

_COLUMNS = ("id, user_id, routine_id, bot_id, slot_at, work_item_id, state, missed_count, note, started_at, "
            "finished_at, created_at")
_UTC = timezone.utc


class SlotAlreadyRecorded(Exception):
    """The slot already has a run row in that state: another tick got there first."""


def utc_now() -> datetime:
    return datetime.now(_UTC)


def iso(moment: datetime) -> str:
    """A UTC ISO string at whole seconds, so stored times compare correctly as text."""
    return moment.astimezone(_UTC).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(_UTC) if value else None


def retention_cutoff(now: datetime) -> datetime:
    return now - timedelta(days=RUN_LOG_RETENTION_DAYS)


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "routine_runs:note")


def _to_run(row: aiosqlite.Row, dek: bytes) -> RoutineRun:
    note = decrypt_field(row["note"], dek, _aad(row["user_id"]), fallback="")
    return RoutineRun(
        id=row["id"], user_id=row["user_id"], routine_id=row["routine_id"], bot_id=row["bot_id"],
        slot_at=parse_iso(row["slot_at"]), work_item_id=row["work_item_id"], state=row["state"],
        missed_count=row["missed_count"], note=note, started_at=parse_iso(row["started_at"]),
        finished_at=parse_iso(row["finished_at"]), created_at=parse_iso(row["created_at"]))


class RoutineRunStore:
    def __init__(self, config: RoostConfig, *, clock: Clock = utc_now) -> None:
        self._config = config
        self._clock = clock

    async def record(
        self, user_id: str, routine: Routine, slot_at: datetime, state: RunState,
        *, note: str | None = None, missed_count: int = 0, work_item_id: str | None = None,
    ) -> RoutineRun:
        """Add a run row for one slot. Raises ``SlotAlreadyRecorded`` when that slot and state already has one."""
        dek = await get_user_dek(self._config, user_id)
        now = iso(self._clock())
        run_id = str(uuid4())
        started = now if state == "running" else None
        finished = now if state in FINISHED_STATES else None
        async with db_session(self._config) as db:
            try:
                await db.execute(
                    f"INSERT INTO routine_runs ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, user_id, routine.id, routine.bot_id, iso(slot_at), work_item_id, state, missed_count,
                     encrypt_field(note, dek, _aad(user_id)), started, finished, now))
                await db.commit()
            except aiosqlite.IntegrityError:
                await db.rollback()
                raise SlotAlreadyRecorded(f"routine {routine.id}: slot already has a {state} run") from None
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (run_id, user_id))
        return found[0]

    async def set_state(
        self, user_id: str, run_id: str, state: RunState,
        *, expected: Collection[str] | None = None, note: str | None = None,
    ) -> RoutineRun | None:
        """Move a run to ``state`` (a compare-and-set against ``expected`` when given). ``None`` when it is not
        the user's, or it is no longer in an expected state."""
        dek = await get_user_dek(self._config, user_id)
        now = iso(self._clock())
        sets, params = ["state = ?"], [state]
        if state == "running":
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        if state in FINISHED_STATES:
            sets.append("finished_at = ?")
            params.append(now)
        if note is not None:
            sets.append("note = ?")
            params.append(encrypt_field(note, dek, _aad(user_id)))
        where, where_params = "id = ? AND user_id = ?", [run_id, user_id]
        if expected is not None:
            marks = ",".join("?" for _ in expected)
            where += f" AND state IN ({marks})"
            where_params.extend(sorted(expected))
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE routine_runs SET {', '.join(sets)} WHERE {where} RETURNING {_COLUMNS}",
                (*params, *where_params))
            rows = await cursor.fetchall()
            await db.commit()
        return _to_run(rows[0], dek) if rows else None

    async def rebind(
        self, user_id: str, run_id: str, work_item_id: str, *, note: str,
    ) -> RoutineRun | None:
        """Point an open run at a new work item and back to ``queued`` (its one retry). ``None`` when it is not the
        user's, or no longer open."""
        dek = await get_user_dek(self._config, user_id)
        marks = ",".join("?" for _ in OPEN_STATES)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE routine_runs SET work_item_id = ?, state = 'queued', note = ? "
                f"WHERE id = ? AND user_id = ? AND state IN ({marks}) RETURNING {_COLUMNS}",
                (work_item_id, encrypt_field(note, dek, _aad(user_id)), run_id, user_id, *OPEN_STATES))
            rows = await cursor.fetchall()
            await db.commit()
        return _to_run(rows[0], dek) if rows else None

    async def for_item(self, user_id: str, work_item_id: str) -> RoutineRun | None:
        found = await self._select(user_id, "WHERE user_id = ? AND work_item_id = ? LIMIT 1", (user_id, work_item_id))
        return found[0] if found else None

    async def open_for_routine(self, user_id: str, routine_id: str) -> tuple[RoutineRun, ...]:
        """The routine's ``queued`` or ``running`` rows."""
        marks = ",".join("?" for _ in OPEN_STATES)
        return await self._select(
            user_id, f"WHERE user_id = ? AND routine_id = ? AND state IN ({marks}) ORDER BY created_at, rowid",
            (user_id, routine_id, *OPEN_STATES))

    async def open_runs(self, user_id: str) -> tuple[RoutineRun, ...]:
        """All of this user's ``queued`` or ``running`` rows, oldest first (the scheduler's reconcile reads these)."""
        marks = ",".join("?" for _ in OPEN_STATES)
        return await self._select(
            user_id, f"WHERE user_id = ? AND state IN ({marks}) ORDER BY created_at, rowid", (user_id, *OPEN_STATES))

    async def list_for_routine(
        self, user_id: str, routine_id: str, limit: int = ROUTINE_RUNS_PAGE, *, before_id: str | None = None,
    ) -> tuple[RoutineRun, ...]:
        """The routine's runs, newest first. With ``before_id``, only the runs older than that run (an unknown id
        gives none)."""
        if before_id is None:
            return await self._select(
                user_id, "WHERE user_id = ? AND routine_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (user_id, routine_id, limit))
        return await self._select(
            user_id,
            "WHERE user_id = ? AND routine_id = ? AND EXISTS (SELECT 1 FROM routine_runs c WHERE c.id = ? "
            "AND c.user_id = ? AND c.routine_id = ? AND (routine_runs.created_at < c.created_at "
            "OR (routine_runs.created_at = c.created_at AND routine_runs.rowid < c.rowid))) "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, routine_id, before_id, user_id, routine_id, limit))

    async def list_recent_for_user(self, user_id: str, limit: int) -> tuple[RoutineRun, ...]:
        """The user's runs across every routine, newest first, at most ``limit``."""
        return await self._select(
            user_id, "WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?", (user_id, limit))

    async def prune(self, user_id: str, before: datetime) -> int:
        """Delete this user's rows created before ``before``; returns how many."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "DELETE FROM routine_runs WHERE user_id = ? AND created_at < ?", (user_id, iso(before)))
            await db.commit()
            return cursor.rowcount

    async def recent_reports(self, user_id: str, bot_id: str, since: datetime) -> int:
        """How many Reports the bot has posted since ``since`` (the hourly cap counts these)."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id = ? AND author_bot_id = ? AND kind = 'report' "
                "AND created_at >= ?", (user_id, bot_id, since.astimezone(_UTC).isoformat()))
            row = await cursor.fetchone()
        return int(row[0])

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[RoutineRun, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM routine_runs {where}", params)).fetchall()
        return tuple(_to_run(row, dek) for row in rows)
