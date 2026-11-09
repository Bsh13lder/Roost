import hashlib
import os
import sqlite3
import stat

import pytest

from lazyclaw_factory import add_user, insert, new_db
from roost.migrate.lazyclaw import source as src
from roost.migrate.lazyclaw.source import SnapshotError, assert_private_dir, delete_snapshot, take_snapshot

DEK = bytes(range(32))


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture
def wal_source(tmp_path):
    path = tmp_path / "live" / "lazyclaw.db"
    path.parent.mkdir()
    conn = new_db(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    add_user(conn, dek=DEK)
    insert(conn, "tasks", id="t1", user_id="old-user-1", title="a")
    insert(conn, "tasks", id="t2", user_id="old-user-1", title="b")
    yield path, conn  # the writer stays open: rows live in the WAL, like a running LazyClaw
    conn.close()


def test_snapshot_sees_wal_rows_and_is_private(wal_source, tmp_path):
    path, _conn = wal_source
    wal = path.with_name(path.name + "-wal")
    assert wal.stat().st_size > 0
    snap = take_snapshot(path, base_dir=tmp_path, check_running=False)
    assert snap.counts["tasks"] == 2 and snap.counts["users"] == 1
    assert stat.S_IMODE(snap.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(snap.path.stat().st_mode) == 0o600
    copy = sqlite3.connect(snap.path)
    assert copy.execute("select count(*) from tasks").fetchone()[0] == 2
    copy.close()
    delete_snapshot(snap)
    assert not snap.directory.exists()


def test_source_is_never_written(wal_source, tmp_path):
    path, _conn = wal_source
    wal = path.with_name(path.name + "-wal")
    before = (_digest(path), _digest(wal), path.stat().st_mtime_ns, wal.stat().st_mtime_ns)
    snap = take_snapshot(path, base_dir=tmp_path, check_running=False)
    after = (_digest(path), _digest(wal), path.stat().st_mtime_ns, wal.stat().st_mtime_ns)
    assert before == after
    delete_snapshot(snap)


def test_source_cannot_be_written_through_the_uri(wal_source):
    path, _ = wal_source
    conn = src.open_source_readonly(path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("insert into tasks (id, user_id, title) values ('x','y','z')")
    conn.close()


def test_missing_source(tmp_path):
    with pytest.raises(SnapshotError, match="not found"):
        take_snapshot(tmp_path / "nope.db", base_dir=tmp_path)


def test_corrupt_copy_is_refused(wal_source, tmp_path, monkeypatch):
    path, _ = wal_source
    monkeypatch.setattr(src, "_integrity_ok", lambda conn: False)
    with pytest.raises(SnapshotError, match="integrity"):
        take_snapshot(path, base_dir=tmp_path, check_running=False)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("roost-lazyclaw-")]


def test_counts_that_keep_changing_are_refused(wal_source, tmp_path, monkeypatch):
    path, _ = wal_source
    calls = iter(range(100))
    monkeypatch.setattr(src, "_table_counts",
                        lambda conn: {t: next(calls) for t in ("users", "tasks")})
    with pytest.raises(SnapshotError, match="changing"):
        take_snapshot(path, base_dir=tmp_path, check_running=False)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("roost-lazyclaw-")]


def test_missing_optional_table_counts_zero(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("create table users (id text)")
    conn.commit()
    conn.close()
    snap = take_snapshot(path, base_dir=tmp_path, check_running=False)
    assert snap.counts["tasks"] == 0
    delete_snapshot(snap)


def test_assert_private_dir(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir(mode=0o700)
    os.chmod(ok, 0o700)
    assert_private_dir(ok)
    loose = tmp_path / "loose"
    loose.mkdir()
    os.chmod(loose, 0o755)
    with pytest.raises(SnapshotError, match="0700"):
        assert_private_dir(loose)
    with pytest.raises(SnapshotError, match="0700"):
        assert_private_dir(tmp_path / "absent")


def test_snapshot_refused_while_the_wal_is_in_use(wal_source, tmp_path):
    path, _ = wal_source
    with pytest.raises(SnapshotError, match=r"Stop LazyClaw first \(its database is in use\)"):
        take_snapshot(path, base_dir=tmp_path, lazyclaw_ports=())
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("roost-lazyclaw-")]


def _leftover_wal(wal_source, tmp_path):
    """LazyClaw stopped hard: its -wal file is left behind, but no process has the database open."""
    path, _conn = wal_source
    stopped = tmp_path / "stopped" / "lazyclaw.db"
    stopped.parent.mkdir()
    for suffix in ("", "-wal"):
        stopped.with_name(stopped.name + suffix).write_bytes(path.with_name(path.name + suffix).read_bytes())
    return stopped


def test_a_leftover_wal_is_refused_unless_the_user_says_lazyclaw_is_stopped(wal_source, tmp_path):
    stopped = _leftover_wal(wal_source, tmp_path)
    with pytest.raises(SnapshotError, match="--lazyclaw-stopped"):
        take_snapshot(stopped, base_dir=tmp_path, lazyclaw_ports=())
    snap = take_snapshot(stopped, base_dir=tmp_path, lazyclaw_ports=(), wal_ok=True)
    assert snap.counts["tasks"] == 2  # the rows that live only in the WAL are in the copy
    delete_snapshot(snap)


def test_a_leftover_wal_is_read_from_a_private_copy_and_lazyclaw_is_untouched(wal_source, tmp_path):
    stopped = _leftover_wal(wal_source, tmp_path)
    wal = stopped.with_name(stopped.name + "-wal")
    before = (_digest(stopped), _digest(wal), stopped.stat().st_mtime_ns, wal.stat().st_mtime_ns)
    snap = take_snapshot(stopped, base_dir=tmp_path, lazyclaw_ports=(), wal_ok=True)
    after = (_digest(stopped), _digest(wal), stopped.stat().st_mtime_ns, wal.stat().st_mtime_ns)
    assert before == after
    assert sorted(p.name for p in stopped.parent.iterdir()) == ["lazyclaw.db", "lazyclaw.db-wal"]  # no -shm made
    assert sorted(p.name for p in snap.directory.iterdir()) == ["lazyclaw-snapshot.db"]  # the stage copies are gone
    delete_snapshot(snap)


def test_snapshot_refused_while_a_lazyclaw_port_listens(tmp_path):
    import socket
    path = tmp_path / "data" / "lazyclaw.db"
    path.parent.mkdir()
    new_db(path).close()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    try:
        with pytest.raises(SnapshotError, match="Stop LazyClaw first"):
            take_snapshot(path, base_dir=tmp_path, lazyclaw_ports=(s.getsockname()[1],))
    finally:
        s.close()


def test_a_quiet_lazyclaw_is_snapshotted(tmp_path):
    path = tmp_path / "data" / "lazyclaw.db"
    path.parent.mkdir()
    new_db(path).close()
    delete_snapshot(take_snapshot(path, base_dir=tmp_path, lazyclaw_ports=()))


def test_port_is_read_from_the_source_config(tmp_path):
    from roost.migrate.lazyclaw.guard import lazyclaw_ports
    (tmp_path / "lazyclaw").mkdir()
    (tmp_path / "lazyclaw" / "config.py").write_text('port=int(os.getenv("PORT", "19999")),\n')
    (tmp_path / "data").mkdir()
    assert lazyclaw_ports(tmp_path / "data" / "lazyclaw.db") == (19999,)
    assert lazyclaw_ports(tmp_path / "other" / "deep" / "x.db") == (18789,)


def test_same_counts_but_different_content_is_refused(wal_source, tmp_path, monkeypatch):
    path, _ = wal_source
    calls = iter(range(100))
    monkeypatch.setattr(src, "_content_digest", lambda conn: str(next(calls)))
    with pytest.raises(SnapshotError, match="changing"):
        take_snapshot(path, base_dir=tmp_path, check_running=False)


def test_the_cli_takes_lazyclaw_stopped():
    from roost.migrate.lazyclaw.__main__ import _parser
    assert _parser().parse_args(["--lazyclaw-stopped"]).lazyclaw_stopped is True
    assert _parser().parse_args([]).lazyclaw_stopped is False
