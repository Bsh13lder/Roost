"""Temp Roost databases for the LazyClaw writer tests. Never a real path (conftest repoints the data dir)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from lazyclaw_factory import OLD_USERNAME, SAMPLE_PASSWORD, build_sample
from roost.bots.store import BotStore
from roost.config import Config, load_config
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.migrate.lazyclaw.mapping import map_lazyclaw
from roost.migrate.lazyclaw.models import Mapped, RoostContext
from roost.migrate.lazyclaw.old_crypto import load_old_keys_by_password
from roost.migrate.lazyclaw.reader import read_lazyclaw
from roost.migrate.lazyclaw.roost_side import ensure_general
from team_helpers import make_bot

IMPORTED_AT = "2099-01-01T08:00:00+00:00"   # after any real clock: sample source rows stamp updated_at with now


@dataclass(frozen=True)
class Rig:
    cfg: Config
    user_id: str
    dek: bytes
    db_path: Path
    bot_id: str


async def make_rig(username: str = "alice") -> Rig:
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, username, "pw-123456")
    bot = await make_bot(cfg, user.id, "Main")
    await BotStore(cfg).set_primary(user.id, bot.id)
    return Rig(cfg, user.id, await get_user_dek(cfg, user.id), get_db_path(cfg), bot.id)


def connect(rig: Rig) -> sqlite3.Connection:
    conn = sqlite3.connect(rig.db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def general_id(rig: Rig) -> str:
    conn = connect(rig)
    try:
        conn.execute("BEGIN IMMEDIATE")
        found = ensure_general(conn, rig.dek, rig.user_id, IMPORTED_AT)
        conn.execute("COMMIT")
        return found
    finally:
        conn.close()


def sample_mapped(tmp_path: Path, rig: Rig, *, import_day: date = date(2026, 10, 21), extra=None) -> Mapped:
    source = build_sample(tmp_path / "lc.db")
    if extra is not None:
        extra(source)
    lazy = sqlite3.connect(source)
    try:
        with load_old_keys_by_password(lazy, OLD_USERNAME, SAMPLE_PASSWORD) as keys:
            data = read_lazyclaw(lazy, keys)
    finally:
        lazy.close()
    ctx = RoostContext(user_id=rig.user_id, import_day=import_day, imported_at=IMPORTED_AT,
                       general_project_id=general_id(rig), main_bot_id=rig.bot_id)
    return map_lazyclaw(data, ctx)


def table_count(rig: Rig, table: str, where: str = "1=1", params: tuple = ()) -> int:
    conn = connect(rig)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ? AND {where}", (rig.user_id, *params)).fetchone()[0]
    finally:
        conn.close()


def unseal(rig: Rig, row: sqlite3.Row, table: str, column: str) -> str | None:
    return decrypt_field(row[column], rig.dek, user_aad(rig.user_id, f"{table}:{column}"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ZERO = Decimal("0")
