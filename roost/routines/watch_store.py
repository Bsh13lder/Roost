"""``WatchStore``: the last snapshot Roost read for a watching routine (schema v40 ``routine_watches``).

``snapshot`` (the watched part as it was read) and ``change_text`` (what the change run is told) are page content,
``enc:v2`` under ``routine_watches:<column>``; the fingerprint is a keyed HMAC (``watch_part.fingerprint``), never the
text. Ids, flags, counts and times stay plaintext. Every query names ``user_id``, so another user's routine has no
snapshot. One row per routine; it goes with its routine (``ON DELETE CASCADE``) and ``reset`` drops it when the
address or the part changes, so the next check records a new baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import aiosqlite

from roost.config import RoostConfig
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.routines.models import Clock
from roost.routines.runs import iso, parse_iso, utc_now

_COLUMNS = ("routine_id, user_id, snapshot, fingerprint, change_text, change_run_id, blocked, quiet_run_id, "
            "quiet_count, checked_at, changed_at, updated_at")
_READ_COLUMNS = f"{_COLUMNS}, fail_count, fail_run_id"      # v47: failed checks in a row and the row they fold into
_CLEAR_FAILS = "fail_count = 0, fail_run_id = NULL"         # a check that read the page ends the failures


@dataclass(frozen=True)
class Snapshot:
    routine_id: str
    snapshot: str | None
    fingerprint: str | None
    change_text: str | None
    change_run_id: str | None
    blocked: bool
    quiet_run_id: str | None
    quiet_count: int
    checked_at: datetime | None
    changed_at: datetime | None
    fail_count: int = 0                 # checks in a row that could not read the page (v47)
    fail_run_id: str | None = None      # the "Couldn't check" run-log row they fold into


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"routine_watches:{column}")


def _to_snapshot(row: aiosqlite.Row, dek: bytes) -> Snapshot:
    user_id = row["user_id"]
    return Snapshot(
        routine_id=row["routine_id"],
        snapshot=decrypt_field(row["snapshot"], dek, _aad(user_id, "snapshot"), fallback=""),
        fingerprint=row["fingerprint"],
        change_text=decrypt_field(row["change_text"], dek, _aad(user_id, "change_text"), fallback=""),
        change_run_id=row["change_run_id"], blocked=bool(row["blocked"]), quiet_run_id=row["quiet_run_id"],
        quiet_count=int(row["quiet_count"]), checked_at=parse_iso(row["checked_at"]),
        changed_at=parse_iso(row["changed_at"]), fail_count=int(row["fail_count"] or 0),
        fail_run_id=row["fail_run_id"])


class WatchStore:
    def __init__(self, config: RoostConfig, *, clock: Clock = utc_now) -> None:
        self._config = config
        self._clock = clock

    async def get(self, user_id: str, routine_id: str) -> Snapshot | None:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_READ_COLUMNS} FROM routine_watches WHERE routine_id = ? AND user_id = ?",
                (routine_id, user_id))).fetchone()
        return _to_snapshot(row, dek) if row is not None else None

    async def save(
        self, user_id: str, routine_id: str, *, snapshot: str, fingerprint: str, changed: bool,
        change_text: str | None = None, change_run_id: str | None = None,
    ) -> None:
        """Keep what this check read. ``changed`` stamps ``changed_at`` and keeps the change for its run; the
        "No change" fold and the sign-in flag start over."""
        dek, now = await get_user_dek(self._config, user_id), iso(self._clock())
        sealed = encrypt_field(snapshot, dek, _aad(user_id, "snapshot"))
        change = encrypt_field(change_text, dek, _aad(user_id, "change_text")) if changed else None
        await self._upsert(
            user_id, routine_id,
            "snapshot = excluded.snapshot, fingerprint = excluded.fingerprint, blocked = 0, quiet_run_id = NULL, "
            f"quiet_count = 0, {_CLEAR_FAILS}, checked_at = excluded.checked_at, updated_at = excluded.updated_at"
            + (", change_text = excluded.change_text, change_run_id = excluded.change_run_id, "
               "changed_at = excluded.changed_at" if changed else ""),
            (sealed, fingerprint, change, change_run_id if changed else None, 0, None, 0, now,
             now if changed else None, now))

    async def set_change_run(self, user_id: str, routine_id: str, run_id: str) -> None:
        await self._update(user_id, routine_id, "change_run_id = ?", (run_id,))

    async def checked(self, user_id: str, routine_id: str) -> None:
        """A check that read the page and found it the same."""
        await self._update(user_id, routine_id, f"checked_at = ?, {_CLEAR_FAILS}", (iso(self._clock()),))

    async def set_blocked(self, user_id: str, routine_id: str, blocked: bool) -> None:
        now = iso(self._clock())
        await self._upsert(user_id, routine_id, "blocked = excluded.blocked, checked_at = excluded.checked_at, "
                           f"quiet_run_id = NULL, quiet_count = 0, {_CLEAR_FAILS}, updated_at = excluded.updated_at",
                           (None, None, None, None, int(blocked), None, 0, now, None, now))

    async def fold_quiet(self, user_id: str, routine_id: str, run_id: str, count: int) -> None:
        """The "No change" run-log row the quiet checks fold into, and how many it holds."""
        await self._update(user_id, routine_id, "quiet_run_id = ?, quiet_count = ?", (run_id, count))

    async def note_fail(self, user_id: str, routine_id: str, run_id: str | None, count: int) -> None:
        """One more check that could not read the page: how many in a row and the run-log row they fold into.
        The row is made if this routine has none yet (the first check may be the one that fails)."""
        now = iso(self._clock())
        await self._upsert(user_id, routine_id,
                           "fail_count = excluded.fail_count, fail_run_id = excluded.fail_run_id, "
                           "updated_at = excluded.updated_at",
                           (None, None, None, None, 0, None, 0, None, None, now), fails=(count, run_id))

    async def reset(self, user_id: str, routine_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("DELETE FROM routine_watches WHERE routine_id = ? AND user_id = ?", (routine_id, user_id))
            await db.commit()

    async def _update(self, user_id: str, routine_id: str, assignments: str, params: tuple) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE routine_watches SET {assignments}, updated_at = ? WHERE routine_id = ? AND user_id = ?",
                (*params, iso(self._clock()), routine_id, user_id))
            await db.commit()

    async def _upsert(
        self, user_id: str, routine_id: str, on_conflict: str, values: tuple, *, fails: tuple = (0, None),
    ) -> None:
        """Insert the row, or on a second write set ``on_conflict``. The routine must be this user's."""
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO routine_watches ({_READ_COLUMNS}) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE EXISTS (SELECT 1 FROM routines WHERE id = ? AND user_id = ?) "
                f"ON CONFLICT(routine_id) DO UPDATE SET {on_conflict} WHERE routine_watches.user_id = excluded.user_id",
                (routine_id, user_id, *values, *fails, routine_id, user_id))
            await db.commit()
