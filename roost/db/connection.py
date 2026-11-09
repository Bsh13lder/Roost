"""Database connection management with a persistent connection pool.

Carried from LazyClaw's ``lazyclaw/db/connection.py`` (git history preserved
via git-filter-repo). The corruption guard below is kept verbatim — it's
what the 2026-07-03 production outage taught: SQLite WAL + mid-write kill =
`database disk image is malformed`, and crash-looping straight back into
`executescript` turns one bad shutdown into a permanent outage.

Night-1 trims this file down to ``init_db`` / ``db_session`` / ``close_pool``
/ ``ensure_initialized`` against the shared contract schema in
``schema.sql`` (``users``, ``sessions``, ``bots``, ``threads``,
``messages``, ``events``, ``audit``); the old per-table migration list and
the LazyBrain timezone-backfill pass were lazyclaw-specific and are
dropped — schema changes since the baseline live in
``roost/db/migrations.py``.

Uses a single shared aiosqlite connection per database path. SQLite
serializes writes internally via WAL mode, so a shared connection is safe
and avoids the ~20-30ms overhead of connect/close per query.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from roost.config import RoostConfig
from roost.db.migrations import apply_migrations, latest_version, pending, schema_version

logger = logging.getLogger(__name__)

# Persistent connection pool: db_path → open connection
_pool: dict[str, aiosqlite.Connection] = {}
# One lock per pooled connection, guarding a whole ``db_session`` block
# (see that function's docstring for why this has to be the WHOLE block,
# not just each statement).
_locks: dict[str, asyncio.Lock] = {}


class DatabaseCorruptionError(RuntimeError):
    """Raised by ``init_db`` when an existing DB file fails integrity check.

    Deliberately NOT a subclass of ``sqlite3.DatabaseError`` — this is a
    startup-guard signal, not a raw driver error, so callers (and process
    supervisors reading logs) can tell "we detected corruption and backed
    it up" apart from "executescript blew up mid-write" (the 2026-07-03
    outage: the latter crash-looped with no recovery path).
    """


def get_db_path(config: RoostConfig) -> Path:
    return config.database_dir / "roost.db"


def _backup_corrupt_db(db_path: Path) -> Path:
    """Copy (never move/delete) a malformed DB file aside for forensics.

    Timestamped so repeated crash-loop attempts against the same corrupt
    file don't clobber each other's backup.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.corrupt-{timestamp}.bak")
    shutil.copy2(db_path, backup_path)
    return backup_path


async def _guard_against_corrupt_db(db_path: Path) -> None:
    """Fail safe on a malformed on-disk DB instead of crash-looping.

    Fresh installs (no file yet) are unaffected — this only runs the
    integrity check against a pre-existing file. On corruption, the file
    is preserved (copied aside, never deleted/replaced) and a precise,
    actionable error is raised instead of letting a raw
    ``sqlite3.DatabaseError`` surface out of ``executescript`` mid-restart-
    loop (2026-07-03 production outage root cause).
    """
    if not db_path.exists():
        return  # new install — nothing to check yet

    corrupt_reason: str | None = None
    try:
        async with aiosqlite.connect(db_path) as check_db:
            cursor = await check_db.execute("PRAGMA quick_check")
            row = await cursor.fetchone()
            result = row[0] if row else None
            if result != "ok":
                corrupt_reason = str(result)
    except aiosqlite.Error as exc:
        # quick_check itself can raise (not just report a non-"ok" row)
        # when the image is malformed badly enough that SQLite can't even
        # walk the btree to run the check — this is the exact exception
        # shape from the outage (`database disk image is malformed`).
        corrupt_reason = str(exc)

    if corrupt_reason is not None:
        backup_path = _backup_corrupt_db(db_path)
        raise DatabaseCorruptionError(
            f"Database at {db_path} failed integrity check "
            f"({corrupt_reason}). The corrupt file was left in place and "
            f"a backup copy was saved to {backup_path}. Refusing to "
            "auto-repair or auto-replace it — do NOT just restart the "
            "process (it will crash-loop). Manual recovery: run "
            f"`sqlite3 {backup_path} \".recover\" | sqlite3 "
            f"{db_path.with_suffix('.recovered.db')}`, verify row counts "
            "(not just `PRAGMA integrity_check`), then swap the recovered "
            "file into place."
        )


async def _backup_before_migrating(db: aiosqlite.Connection, db_path: Path, target_version: int) -> Path:
    """Consistent copy (SQLite backup API, safe under WAL) taken before any
    pending migration touches an existing database. Never deleted by Roost."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.pre-v{target_version}-{timestamp}.bak")
    async with aiosqlite.connect(backup_path) as target:
        await db.backup(target)
    logger.warning("Backed up %s to %s before migrating to schema v%s", db_path, backup_path, target_version)
    return backup_path


async def init_db(config: RoostConfig) -> None:
    """Create the baseline schema (if needed), then apply pending migrations.

    Idempotent: safe on every boot. A database that already existed gets a
    backup copy before its first pending migration runs."""
    config.database_dir.mkdir(parents=True, exist_ok=True)
    schema_sql = (Path(__file__).parent / "schema.sql").read_text()

    db_path = get_db_path(config)
    await _guard_against_corrupt_db(db_path)
    existed = db_path.exists()

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.executescript(schema_sql)
        await db.commit()
        if existed and pending(await schema_version(db)):
            await _backup_before_migrating(db, db_path, latest_version())
        await apply_migrations(db)


@asynccontextmanager
async def db_session(config: RoostConfig) -> AsyncIterator[aiosqlite.Connection]:
    """Get a database connection from the persistent pool.

    Reuses a single connection per database path instead of opening and
    closing on every call (~20-30ms savings per query). Every connection
    has ``foreign_keys=ON``.

    Task 4 finding: WAL mode serializes concurrent *writers* at the
    SQLite file level, but that's not the whole story for ONE shared
    ``aiosqlite.Connection`` driven by MANY concurrent coroutines (e.g.
    several ``ask_bot`` handoffs to the same bot via ``asyncio.gather``,
    or that bot's own drain loop running alongside them). Python's
    ``sqlite3`` module tracks open statements *per connection*: a
    ``SELECT`` whose cursor hasn't been fully drained (a plain
    ``fetchone()`` call, common throughout this codebase, steps the
    statement once without discovering it's done) stays "in progress"
    until that cursor is garbage-collected. If another coroutine's
    ``commit()`` reaches the connection while that statement is still
    open — perfectly possible, since every ``await`` here is a point
    the event loop can run something else — SQLite raises
    ``OperationalError: cannot commit transaction - SQL statements in
    progress``, nondeterministically (it depends on scheduling order).
    One lock per connection, held for the whole block below, makes every
    ``db_session`` user's sequence of statements atomic with respect to
    every other one -- the serialization the module docstring already
    promises, actually enforced.
    """
    db_path = str(get_db_path(config))

    if db_path not in _pool:
        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA busy_timeout = 5000")
        _pool[db_path] = db
        _locks[db_path] = asyncio.Lock()
        logger.debug("Opened persistent DB connection: %s", db_path)

    async with _locks[db_path]:
        yield _pool[db_path]


async def close_pool() -> None:
    """Close all pooled connections. Call on shutdown."""
    for db_path, conn in list(_pool.items()):
        try:
            await conn.close()
            logger.debug("Closed pooled DB connection: %s", db_path)
        except Exception as exc:
            logger.debug("Failed to close pooled DB connection %s: %s", db_path, exc)
    _pool.clear()
    _locks.clear()


# Directories (as resolved strings) that have already had ``init_db`` run
# against them this process — see ``ensure_initialized`` below.
_initialized_dirs: set[str] = set()


async def ensure_initialized(config: RoostConfig) -> None:
    """Idempotently run ``init_db`` once per database directory.

    A real server boot (``python -m roost``) calls ``init_db`` directly
    from the gateway app's lifespan handler, which runs once before any
    request is served. This exists as a second, defensive path for
    anything that serves requests WITHOUT that lifespan ever firing —
    notably Starlette's ``TestClient`` when constructed and used without
    ``with TestClient(app) as c:``: its bare constructor never runs the
    ASGI lifespan protocol at all (each request gets its own throwaway
    event-loop portal instead), which is exactly how the gateway's
    contract tests build clients. ``roost/gateway/auth.py``'s route
    handlers and ``get_current_user`` call this before touching the DB
    so they work correctly either way. Cheap to call on every request:
    short-circuits to a set lookup once a directory is known-initialized.
    """
    key = str(config.database_dir)
    if key in _initialized_dirs:
        return
    await init_db(config)
    _initialized_dirs.add(key)
