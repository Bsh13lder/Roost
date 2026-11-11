"""``RoutineStore``: a bot's routines (schema v25 ``routines``).

``name``, ``instructions`` and ``schedule`` (the schedule model's JSON) are user content, ``enc:v2`` under
``routines:<column>``; ids, flags and times stay plaintext. Every query names ``user_id``, so another user's
routine reads as "no such routine". ``next_run_at`` is the next slot plus its deterministic jitter (UTC, whole
seconds); ``claim_slot`` is the compare-and-swap that stops two ticks from firing one slot."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import aiosqlite
from pydantic import TypeAdapter

from roost.config import RoostConfig
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.routines.models import Clock, Routine, RoutineDraft, RoutinePatch
from roost.routines.runs import iso, parse_iso, utc_now
from roost.routines.schedule import Schedule, jitter_seconds, next_after
from roost.routines.watch_models import Watch, next_check
from roost.talk.store import TalkStore

_COLUMNS = ("id, user_id, bot_id, thread_id, name, instructions, schedule, builtin, enabled, tainted, created_by, "
            "next_run_at, last_run_at, created_at, updated_at, watch_url, watch_part, watch_every_min, model, model_failures")
# v47 and v48: set by the watch, the hooks and ``finish``, never inserted.
_READ_COLUMNS = f"{_COLUMNS}, last_error_kind, last_error_at, finished_at, finished_reason"
_SCHEDULE = TypeAdapter(Schedule)
DAY_SUMMARY_BUILTIN = "day_summary"
DAY_SUMMARY_NAME = "End-of-day summary"
_PATCHABLE = frozenset({"name", "instructions", "schedule", "tainted", "watch", "model"})


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"routines:{column}")


def _watch_of(row: aiosqlite.Row, dek: bytes) -> Watch | None:
    """The routine's watch; one whose address can't be read is no watch (it never opens a page it can't name)."""
    every, user_id = row["watch_every_min"], row["user_id"]
    url = decrypt_field(row["watch_url"], dek, _aad(user_id, "watch_url"), fallback="") if every else ""
    if not url:
        return None
    part = decrypt_field(row["watch_part"], dek, _aad(user_id, "watch_part"), fallback="") or ""
    return Watch(url=url, part=part, every_min=int(every))


def _to_routine(row: aiosqlite.Row, dek: bytes) -> Routine:
    user_id = row["user_id"]
    schedule_json = decrypt_field(row["schedule"], dek, _aad(user_id, "schedule"), fallback="")
    return Routine(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], thread_id=row["thread_id"],
        name=decrypt_field(row["name"], dek, _aad(user_id, "name"), fallback="") or "",
        instructions=decrypt_field(row["instructions"], dek, _aad(user_id, "instructions"), fallback="") or "",
        schedule=_SCHEDULE.validate_json(schedule_json), builtin=row["builtin"], enabled=bool(row["enabled"]),
        tainted=bool(row["tainted"]), created_by=row["created_by"], next_run_at=parse_iso(row["next_run_at"]),
        last_run_at=parse_iso(row["last_run_at"]), created_at=parse_iso(row["created_at"]),
        updated_at=parse_iso(row["updated_at"]), watch=_watch_of(row, dek), model=row["model"],
        model_failures=int(row["model_failures"] or 0),
        last_error_kind=row["last_error_kind"] or None, last_error_at=parse_iso(row["last_error_at"]),
        finished_at=parse_iso(row["finished_at"]), finished_reason=_reason_of(row, dek))


def _reason_of(row: aiosqlite.Row, dek: bytes) -> str | None:
    """A finished routine's sealed reason; None when it is not finished."""
    if not row["finished_at"] or not row["finished_reason"]:
        return None
    return decrypt_field(row["finished_reason"], dek, _aad(row["user_id"], "finished_reason"), fallback="") or None


def _watch_values(user_id: str, watch: Watch | None, dek: bytes) -> tuple:
    if watch is None:
        return None, None, None
    return (encrypt(watch.url, dek, _aad(user_id, "watch_url")), encrypt(watch.part, dek, _aad(user_id, "watch_part")),
            watch.every_min)


def first_run_at(routine_id: str, schedule: Schedule, now: datetime, watch: Watch | None = None) -> datetime:
    """The next slot after ``now`` plus its jitter; for a watching routine, its next check."""
    if watch is not None:
        return next_check(watch, now)
    slot = next_after(schedule, now)
    return slot + timedelta(seconds=jitter_seconds(routine_id, slot))


class RoutineStore:
    def __init__(self, config: RoostConfig, talk: TalkStore, *, clock: Clock = utc_now) -> None:
        self._config = config
        self._talk = talk
        self._clock = clock

    async def create(self, user_id: str, draft: RoutineDraft) -> Routine:
        """Make the routine and its run-log thread. Raises ``ValueError`` when the bot is not there."""
        dek = await get_user_dek(self._config, user_id)
        routine_id, now = str(uuid4()), self._clock()
        try:
            thread = await self._talk.create_thread(user_id, draft.bot_id, draft.name, kind="routine")
        except aiosqlite.IntegrityError:
            raise ValueError("No such bot.") from None
        next_run = first_run_at(routine_id, draft.schedule, now, draft.watch) if draft.enabled else None
        try:
            async with db_session(self._config) as db:
                await db.execute(
                    f"INSERT INTO routines ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (routine_id, user_id, draft.bot_id, thread.id,
                     encrypt(draft.name, dek, _aad(user_id, "name")),
                     encrypt(draft.instructions, dek, _aad(user_id, "instructions")),
                     encrypt(draft.schedule.model_dump_json(), dek, _aad(user_id, "schedule")),
                     draft.builtin, int(draft.enabled), int(draft.tainted), draft.created_by,
                     iso(next_run) if next_run else None, None, iso(now), iso(now),
                     *_watch_values(user_id, draft.watch, dek), draft.model, 0))
                await db.commit()
        except Exception:
            await self._drop_thread(user_id, thread.id)
            raise
        return await self._one(user_id, "WHERE id = ? AND user_id = ?", (routine_id, user_id))

    async def get(self, user_id: str, routine_id: str) -> Routine | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (routine_id, user_id))
        return found[0] if found else None

    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[Routine, ...]:
        return await self._select(
            user_id, "WHERE user_id = ? AND bot_id = ? ORDER BY created_at, rowid", (user_id, bot_id))

    async def list_for_user(self, user_id: str) -> tuple[Routine, ...]:
        """Every routine of every one of the user's bots, oldest first."""
        return await self._select(user_id, "WHERE user_id = ? ORDER BY created_at, rowid", (user_id,))

    async def for_thread(self, user_id: str, thread_id: str) -> Routine | None:
        """The routine whose run-log thread this is."""
        found = await self._select(user_id, "WHERE user_id = ? AND thread_id = ? LIMIT 1", (user_id, thread_id))
        return found[0] if found else None

    async def count_for_bot(self, user_id: str, bot_id: str) -> int:
        return await self._count("WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))

    async def count_for_user(self, user_id: str) -> int:
        return await self._count("WHERE user_id = ?", (user_id,))

    async def builtin_for(self, user_id: str, bot_id: str, builtin: str) -> Routine | None:
        found = await self._select(
            user_id, "WHERE user_id = ? AND bot_id = ? AND builtin = ? LIMIT 1", (user_id, bot_id, builtin))
        return found[0] if found else None

    async def due(self, user_id: str, now: datetime, limit: int | None = None) -> tuple[Routine, ...]:
        """Enabled routines whose next run is at or before ``now``, oldest first."""
        sql = "WHERE user_id = ? AND enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ? " \
              "ORDER BY next_run_at, rowid"
        params: tuple = (user_id, iso(now))
        if limit is not None:
            sql, params = sql + " LIMIT ?", (*params, limit)
        return await self._select(user_id, sql, params)

    async def claim_slot(
        self, user_id: str, routine_id: str, old_next: datetime, new_next: datetime | None, last_run_at: datetime,
    ) -> bool:
        """Compare-and-swap ``next_run_at``: true for exactly one caller per slot."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE routines SET next_run_at = ?, last_run_at = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND next_run_at = ?",
                (iso(new_next) if new_next else None, iso(last_run_at), iso(self._clock()), routine_id, user_id,
                 iso(old_next)))
            await db.commit()
            return cursor.rowcount == 1

    async def set_enabled(self, user_id: str, routine_id: str, enabled: bool) -> Routine | None:
        """Switch on or off. Off clears ``next_run_at``; on plans from now, so no past slot is replayed."""
        current = await self.get(user_id, routine_id)
        if current is None:
            return None
        now = self._clock()
        next_run = first_run_at(routine_id, current.schedule, now, current.watch) if enabled else None
        # Switching a finished routine back on is its Resume: it is no longer finished, so it is never swept.
        cleared = ", finished_at = NULL, finished_reason = NULL" if enabled else ""
        await self._write(user_id, routine_id, f"enabled = ?, next_run_at = ?{cleared}",
                          (int(enabled), iso(next_run) if next_run else None), now)
        return await self.get(user_id, routine_id)

    async def finish(self, user_id: str, routine_id: str, reason: str) -> Routine | None:
        """v48: the bot finished it. Off, no next run, ``finished_at`` now and the reason sealed."""
        if await self.get(user_id, routine_id) is None:
            return None
        dek, now = await get_user_dek(self._config, user_id), self._clock()
        await self._write(user_id, routine_id, "enabled = 0, next_run_at = NULL, finished_at = ?, finished_reason = ?",
                          (iso(now), encrypt(reason, dek, _aad(user_id, "finished_reason"))), now)
        return await self.get(user_id, routine_id)

    async def finished_before(self, user_id: str, cutoff: datetime) -> tuple[Routine, ...]:
        """The user's routines finished at or before ``cutoff`` and still finished, oldest first."""
        return await self._select(
            user_id, "WHERE user_id = ? AND finished_at IS NOT NULL AND finished_at <= ? ORDER BY finished_at, rowid",
            (user_id, iso(cutoff)))

    async def set_last_error(
        self, user_id: str, routine_id: str, kind: str | None, at: datetime | None,
    ) -> None:
        """Keep a routine's last failure (a ``ROUTINE_ERROR_*`` word and when), or clear it with ``None``."""
        await self._write(user_id, routine_id, "last_error_kind = ?, last_error_at = ?",
                          (kind, iso(at) if at is not None and kind is not None else None), self._clock())

    async def replan_all(self, user_id: str) -> int:
        """After the install's time zone changed: plan every enabled timed routine of the user again from now, so
        08:00 stays 08:00 on the new local clock. A watching routine's next check is a plain interval and stays.
        Returns how many were planned again."""
        now = self._clock()
        timed = [r for r in await self.list_for_user(user_id) if r.enabled and r.watch is None]
        async with db_session(self._config) as db:
            for routine in timed:
                await db.execute(
                    "UPDATE routines SET next_run_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND enabled = 1",
                    (iso(first_run_at(routine.id, routine.schedule, now)), iso(now), routine.id, user_id))
            await db.commit()
        return len(timed)

    async def update(self, user_id: str, routine_id: str, patch: RoutinePatch) -> Routine | None:
        """Change name, instructions, schedule, tainted or watch. A new schedule or watch re-plans an enabled routine
        from now (a watching routine plans its next check). Raises ``ValueError`` for any other key."""
        unknown = set(patch.changes) - _PATCHABLE
        if unknown:
            raise ValueError(f"A routine can't change {', '.join(sorted(unknown))}.")
        current = await self.get(user_id, routine_id)
        if current is None:
            return None
        dek, now = await get_user_dek(self._config, user_id), self._clock()
        sets: list[str] = []
        params: list = []
        for column in ("name", "instructions"):
            if column in patch.changes:
                sets.append(f"{column} = ?")
                params.append(encrypt(patch.changes[column], dek, _aad(user_id, column)))
        schedule, watch = current.schedule, patch.changes.get("watch", current.watch)
        if "schedule" in patch.changes:
            schedule = _SCHEDULE.validate_python(patch.changes["schedule"])
            sets.append("schedule = ?")
            params.append(encrypt(schedule.model_dump_json(), dek, _aad(user_id, "schedule")))
        if "watch" in patch.changes:
            sets.append("watch_url = ?, watch_part = ?, watch_every_min = ?")
            params.extend(_watch_values(user_id, watch, dek))
        if current.enabled and {"schedule", "watch"} & set(patch.changes):
            sets.append("next_run_at = ?")
            params.append(iso(first_run_at(routine_id, schedule, now, watch)))
        if "tainted" in patch.changes:
            sets.append("tainted = ?")
            params.append(int(bool(patch.changes["tainted"])))
        if "model" in patch.changes:
            sets.append("model = ?, model_failures = 0")
            params.append(patch.changes["model"])
        if sets:
            await self._write(user_id, routine_id, ", ".join(sets), tuple(params), now)
        return await self.get(user_id, routine_id)

    async def note_model_run(self, user_id: str, routine_id: str, *, ok: bool) -> Routine | None:
        """Count a run on the routine's own model: a good run starts the count over, a failed one adds to it."""
        assignments = "model_failures = 0" if ok else "model_failures = model_failures + 1"
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE routines SET {assignments} WHERE id = ? AND user_id = ? AND model IS NOT NULL",
                (routine_id, user_id))
            await db.commit()
        return await self.get(user_id, routine_id)

    async def delete(self, user_id: str, routine_id: str) -> bool:
        """Delete the routine, its runs and its run-log thread."""
        current = await self.get(user_id, routine_id)
        if current is None:
            return False
        async with db_session(self._config) as db:
            await db.execute("DELETE FROM routines WHERE id = ? AND user_id = ?", (routine_id, user_id))
            await db.commit()
        await self._drop_thread(user_id, current.thread_id)
        return True

    async def _write(self, user_id: str, routine_id: str, assignments: str, params: tuple, now: datetime) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE routines SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
                (*params, iso(now), routine_id, user_id))
            await db.commit()

    async def _drop_thread(self, user_id: str, thread_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("DELETE FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id))
            await db.commit()

    async def _count(self, where: str, params: tuple) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(f"SELECT COUNT(*) FROM routines {where}", params)).fetchone()
        return int(row[0])

    async def _one(self, user_id: str, where: str, params: tuple) -> Routine:
        return (await self._select(user_id, where, params))[0]

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[Routine, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_READ_COLUMNS} FROM routines {where}", params)).fetchall()
        return tuple(_to_routine(row, dek) for row in rows)
