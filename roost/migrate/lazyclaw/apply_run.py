"""The Roost side of ``--apply``: the backup, the schema, the account's key and ids, the import."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag

from roost.config import Config
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import close_pool, init_db
from roost.migrate.lazyclaw.constants import (
    BACKUP_DIR_NAME, BACKUP_PREFIX, DIR_MODE, FILE_MODE, RUN_ID_PREFIX, SUPPORTED_SCHEMA_VERSIONS,
)
from roost.migrate.lazyclaw.models import LazyData, Mapped, RoostContext
from roost.migrate.lazyclaw.mapping import map_lazyclaw
from roost.migrate.lazyclaw.roost_side import RoostAccountError, ensure_general, main_bot_id, only_user_id


@dataclass(frozen=True)
class Account:
    """The Roost user the import writes for. ``dek`` is secret: never print it."""

    user_id: str
    dek: bytes = b""
    general_id: str = ""
    main_bot_id: str | None = None

    def __repr__(self) -> str:
        return f"Account(user_id={self.user_id!r})"


def new_run_id() -> str:
    return f"{RUN_ID_PREFIX}{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"


def backup_dir(db_path: Path) -> Path:
    return db_path.parent.parent / BACKUP_DIR_NAME


def backup_database(db_path: Path, run_id: str) -> Path:
    """An online SQLite backup of the Roost database into a 0700 folder as a 0600 file."""
    folder = backup_dir(db_path)
    folder.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(folder, DIR_MODE)
    target = folder / f"{BACKUP_PREFIX}{run_id}.db"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    os.close(fd)
    source, copy = sqlite3.connect(db_path), sqlite3.connect(target)
    try:
        source.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RoostAccountError("The backup of the Roost database did not pass its integrity check.")
    finally:
        copy.close()
        source.close()
    os.chmod(target, FILE_MODE)
    return target


def find_backup(db_path: Path, run_id: str) -> Path | None:
    found = backup_dir(db_path) / f"{BACKUP_PREFIX}{run_id}.db"
    return found if found.is_file() else None


def _assert_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        known = ", ".join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)
        raise RoostAccountError(f"This tool only knows Roost's database schema {known}, but this database is at "
                                f"{version}. Nothing was changed.")


async def _unlock_dek(config: Config, user_id: str) -> bytes:
    """The account's key. A wrong or missing secret is a plain message; the secret is never shown."""
    try:
        return await get_user_dek(config, user_id)
    except (ValueError, InvalidTag):
        raise RoostAccountError("Roost's server secret does not unlock this account's key (a wrong secret, or "
                                "a damaged account). Nothing was changed.") from None


async def _prepare(config: Config, db_path: Path, now: str) -> Account:
    await init_db(config)            # brings the schema up to v18 (import_links)
    conn = connect(db_path)
    try:
        _assert_schema(conn)
        user_id = only_user_id(conn)
        dek = await _unlock_dek(config, user_id)
        conn.execute("BEGIN IMMEDIATE")
        general = ensure_general(conn, dek, user_id, now)
        conn.execute("COMMIT")
        return Account(user_id=user_id, dek=dek, general_id=general, main_bot_id=main_bot_id(conn, user_id))
    finally:
        conn.close()
        await close_pool()


def connect(db_path: Path) -> sqlite3.Connection:
    """Autocommit connection; the writer opens its own transaction. Foreign keys on, as in Roost."""
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_account(config: Config, db_path: Path, now: str) -> Account:
    return asyncio.run(_prepare(config, db_path, now))


def map_for(account: Account, data: LazyData, now: str) -> Mapped:
    ctx = RoostContext(user_id=account.user_id, import_day=date.today(), imported_at=now,
                       general_project_id=account.general_id, main_bot_id=account.main_bot_id)
    return map_lazyclaw(data, ctx)
