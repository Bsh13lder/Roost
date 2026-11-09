"""A read-only snapshot of LazyClaw's database.

The source is opened with ``mode=ro`` (never ``immutable=1``, which would skip the WAL) and
copied with SQLite's online backup API. Nothing is written to the source: no pragma, no
checkpoint, no VACUUM. The copy lives in a 0700 temp dir as a 0600 file.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from roost.migrate.lazyclaw.constants import (
    COUNTED_TABLES, DIR_MODE, FILE_MODE, SNAPSHOT_BUSY_TIMEOUT_S, SNAPSHOT_COUNT_ATTEMPTS,
    LAZYCLAW_RUNNING_MESSAGE, LEFTOVER_WAL_HINT, SNAPSHOT_DIR_PREFIX, SNAPSHOT_FILE_NAME, STAGE_FILE_NAME,
)
from roost.migrate.lazyclaw.guard import any_port_open, lazyclaw_ports as derive_ports, wal_in_use


class SnapshotError(Exception):
    """The snapshot could not be taken safely. The message is safe to show."""


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    path: Path
    counts: dict[str, int]


def open_source_readonly(source: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(source.resolve()))}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=SNAPSHOT_BUSY_TIMEOUT_S)


def assert_private_dir(path: Path) -> None:
    """The one place a run may write: an existing directory with mode exactly 0700."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        is_dir = path.is_dir()
    except OSError:
        mode, is_dir = -1, False
    if not is_dir or mode != DIR_MODE:
        raise SnapshotError(f"{path} must be an existing folder with mode 0700 (owner only).")


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return {
        table: (conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in existing else 0)
        for table in COUNTED_TABLES
    }


def _content_digest(conn: sqlite3.Connection) -> str:
    """A checksum of every counted table's rows (so an edit that keeps the row count is noticed)."""
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    digest = hashlib.sha256()
    for table in COUNTED_TABLES:
        if table not in existing:
            continue
        digest.update(table.encode())
        for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
            digest.update(repr(row).encode())
    return digest.hexdigest()


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def _stable_counts(src: sqlite3.Connection, first: dict[str, int], first_digest: str) -> bool:
    """A second backup (to memory) must count the same rows, with the same checksum, as the first."""
    for _ in range(SNAPSHOT_COUNT_ATTEMPTS):
        probe = sqlite3.connect(":memory:")
        try:
            src.backup(probe)
            if _table_counts(probe) == first and _content_digest(probe) == first_digest:
                return True
        finally:
            probe.close()
    return False


def _copy(source: Path, target: Path) -> dict[str, int]:
    src = open_source_readonly(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        if not _integrity_ok(dst):
            raise SnapshotError("The copy failed SQLite's integrity check; nothing was imported.")
        counts = _table_counts(dst)
        if not _stable_counts(src, counts, _content_digest(dst)):
            raise SnapshotError("LazyClaw's data kept changing while it was copied. Try again in a quiet moment.")
        return counts
    except sqlite3.Error as exc:
        raise SnapshotError(f"Could not read the LazyClaw database safely ({type(exc).__name__}).") from exc
    finally:
        dst.close()
        src.close()


def assert_lazyclaw_stopped(source: Path, ports: tuple[int, ...] | None = None, *, wal_ok: bool = False) -> None:
    """Refuse while LazyClaw is listening, or has a ``-wal`` file the user hasn't vouched for.

    A hard ``docker compose stop`` leaves a non-empty ``-wal`` behind with no process holding it; the user
    then says so (``--lazyclaw-stopped``, ``wal_ok``) and the leftover WAL is read from a private copy."""
    ports = derive_ports(source) if ports is None else ports
    if any_port_open(ports):
        raise SnapshotError(LAZYCLAW_RUNNING_MESSAGE)
    if wal_in_use(source) and not wal_ok:
        raise SnapshotError(f"{LAZYCLAW_RUNNING_MESSAGE} {LEFTOVER_WAL_HINT}")


def _stage(source: Path, directory: Path) -> Path:
    """Copy the database and its leftover ``-wal`` into the private folder, byte for byte. SQLite replays
    the WAL there, so LazyClaw's own folder is only ever read (no ``-shm`` is made beside it)."""
    staged = directory / STAGE_FILE_NAME
    for suffix in ("", "-wal"):
        original = source.with_name(source.name + suffix)
        if original.is_file():
            copy = staged.with_name(staged.name + suffix)
            shutil.copyfile(original, copy)
            os.chmod(copy, FILE_MODE)
    return staged


def _unstage(staged: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        staged.with_name(staged.name + suffix).unlink(missing_ok=True)


def _copy_staged(source: Path, directory: Path, target: Path) -> dict[str, int]:
    staged = _stage(source, directory)
    try:
        with sqlite3.connect(staged) as conn:  # private copy: opening it read-write lets the WAL replay
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return _copy(staged, target)
    finally:
        _unstage(staged)


def take_snapshot(source: Path, *, base_dir: Path | None = None, check_running: bool = True,
                  lazyclaw_ports: tuple[int, ...] | None = None, wal_ok: bool = False) -> Snapshot:
    if not source.is_file():
        raise SnapshotError(f"LazyClaw database not found at {source}.")
    if check_running:
        assert_lazyclaw_stopped(source, lazyclaw_ports, wal_ok=wal_ok)
    directory = Path(tempfile.mkdtemp(prefix=SNAPSHOT_DIR_PREFIX, dir=base_dir))
    os.chmod(directory, DIR_MODE)
    target = directory / SNAPSHOT_FILE_NAME
    try:
        os.close(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE))
        leftover = wal_ok and wal_in_use(source)
        counts = _copy_staged(source, directory, target) if leftover else _copy(source, target)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return Snapshot(directory=directory, path=target, counts=counts)


def delete_snapshot(snapshot: Snapshot) -> None:
    shutil.rmtree(snapshot.directory, ignore_errors=True)
