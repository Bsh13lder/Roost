"""``--apply`` end to end on a temp Roost database (plan Task 6)."""

from __future__ import annotations

import asyncio
import io
import os
import sqlite3

import pytest

from lazyclaw_factory import OLD_USERNAME, SAMPLE_PASSWORD, build_sample
from roost.migrate.lazyclaw.__main__ import main
from roost_harness import connect, make_rig, table_count


def cli(argv, *, answer=OLD_USERNAME):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, getpass_fn=lambda prompt: SAMPLE_PASSWORD, input_fn=lambda prompt: answer, out=out, err=err,
                env={}, roost_ports=(), lazyclaw_ports=())
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def source(tmp_path):
    return build_sample(tmp_path / "lc.db")


async def test_apply_backs_up_first_then_imports(source, tmp_path):
    rig = await make_rig()
    conn = connect(rig)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('old', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    code, out, err = await asyncio.to_thread(cli, ["--source", str(source), "--roost-db", str(rig.db_path),
                                                   "--apply", "--wipe", "--yes"])
    assert code == 0, err
    assert table_count(rig, "tasks") == 3 and table_count(rig, "import_links", "kind != 'wipe'") == 14
    backups = list((tmp_path / "backups").glob("pre-lazyclaw-*.db"))
    assert len(backups) == 1 and f"{backups[0]}" in out
    assert (backups[0].stat().st_mode & 0o077) == 0 and ((tmp_path / "backups").stat().st_mode & 0o077) == 0
    old = sqlite3.connect(backups[0])
    assert old.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1       # the state before the wipe
    old.close()
    assert "--undo" in out and "run id" in out.lower() and "Read-back OK" in out
    assert "roost.db-wal" in out and "roost.db-shm" in out and "stop Roost" in out
    assert SAMPLE_PASSWORD not in out + err


async def test_apply_asks_first_and_no_changes_without_a_yes(source, tmp_path):
    rig = await make_rig()
    code, out, err = await asyncio.to_thread(cli, ["--source", str(source), "--roost-db", str(rig.db_path),
                                                   "--apply", "--wipe", "--old-username", OLD_USERNAME], answer="no")
    assert code == 1, err
    assert table_count(rig, "tasks") == 0 and table_count(rig, "import_links") == 0
    assert "WIPE BEFORE IMPORT" in out and "nothing was changed" in err
    assert len(list((tmp_path / "backups").glob("pre-lazyclaw-*.db"))) == 1     # the backup always comes first


async def test_apply_needs_an_explicit_roost_db(source):
    code, _, err = await asyncio.to_thread(cli, ["--source", str(source), "--apply", "--yes"])
    assert code == 2 and "--roost-db" in err


async def test_apply_twice_adds_nothing(source, tmp_path):
    rig = await make_rig()
    argv = ["--source", str(source), "--roost-db", str(rig.db_path), "--apply", "--wipe", "--yes"]
    assert (await asyncio.to_thread(cli, argv))[0] == 0
    code, out, err = await asyncio.to_thread(cli, argv)
    assert code == 0, err
    assert table_count(rig, "tasks") == 3 and table_count(rig, "import_links", "kind != 'wipe'") == 14
    assert "already imported" in out.lower()


def _listener():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s, s.getsockname()[1]


@pytest.mark.parametrize("flag", [["--apply", "--yes"], ["--undo", "lazyclaw-x"]])
async def test_apply_and_undo_refuse_while_roost_is_listening(source, tmp_path, flag):
    rig = await make_rig()
    s, port = _listener()
    try:
        out, err = io.StringIO(), io.StringIO()
        code = await asyncio.to_thread(
            main, ["--source", str(source), "--roost-db", str(rig.db_path), *flag],
            getpass_fn=lambda p: SAMPLE_PASSWORD, input_fn=lambda p: OLD_USERNAME, out=out, err=err, env={},
            roost_ports=(port,))
    finally:
        s.close()
    assert code == 1 and "Stop Roost first" in err.getvalue()
    assert table_count(rig, "tasks") == 0 and not (tmp_path / "backups").exists()


async def test_apply_refuses_a_schema_version_it_does_not_know(source, tmp_path):
    rig = await make_rig()
    conn = connect(rig)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    code, out, err = await asyncio.to_thread(cli, ["--source", str(source), "--roost-db", str(rig.db_path),
                                                   "--apply", "--yes"])
    assert code == 1 and "schema" in err.lower() and "99" in err
    assert table_count(rig, "tasks") == 0 and table_count(rig, "import_links") == 0


async def test_yes_alone_never_wipes(source, tmp_path):
    rig = await make_rig()
    conn = connect(rig)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('old', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    code, out, err = await asyncio.to_thread(cli, ["--source", str(source), "--roost-db", str(rig.db_path),
                                                   "--apply", "--yes"])
    assert code == 0, err
    assert table_count(rig, "tasks") == 4 and table_count(rig, "import_links", "kind = 'wipe'") == 0
    assert "Nothing was wiped" in out


def _plain_db(folder):
    folder.mkdir()
    path = folder / "roost.db"
    sqlite3.connect(path).close()
    return path


@pytest.mark.parametrize("flag", [["--apply", "--yes"], ["--undo", "lazyclaw-x"]])
def test_without_a_server_secret_nothing_is_created(source, tmp_path, flag):
    db = _plain_db(tmp_path / "fresh")
    code, out, err = cli(["--source", str(source), "--roost-db", str(db), *flag])
    assert code == 1 and "server secret" in err.lower() and "Traceback" not in err
    assert sorted(p.name for p in db.parent.iterdir()) == ["roost.db"]      # no server.secret, keeper.secret, backup
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("flag", [["--apply", "--yes"], ["--undo", "lazyclaw-x"]])
async def test_a_wrong_secret_is_a_friendly_message(source, tmp_path, flag):
    import secrets
    from roost.crypto.key_manager import clear_user_dek
    rig = await make_rig()
    clear_user_dek(rig.user_id)
    wrong = secrets.token_urlsafe(48)
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(
        main, ["--source", str(source), "--roost-db", str(rig.db_path), *flag],
        getpass_fn=lambda p: SAMPLE_PASSWORD, input_fn=lambda p: OLD_USERNAME, out=out, err=err,
        env={"ROOST_SERVER_SECRET": wrong}, roost_ports=(), lazyclaw_ports=())
    assert code == 1 and "secret" in err.getvalue().lower() and "Traceback" not in err.getvalue()
    assert wrong not in out.getvalue() + err.getvalue()
    assert table_count(rig, "tasks") == 0
