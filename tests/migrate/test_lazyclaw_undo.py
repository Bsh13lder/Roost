"""``--undo <run_id>``: exactly what that run imported goes; edited rows are refused unless forced (Task 8)."""

from __future__ import annotations

import asyncio
import io

import pytest

from lazyclaw_factory import OLD_USERNAME, SAMPLE_PASSWORD, build_sample
from roost.migrate.lazyclaw.__main__ import main
from roost.migrate.lazyclaw.undo import UndoError, UndoRefused, undo_run
from roost.migrate.lazyclaw.writer import apply_import
from roost_harness import IMPORTED_AT, connect, general_id, make_rig, sample_mapped, table_count, unseal

RUN = "lazyclaw-undo-1"
LATER = "2099-02-01T09:00:00+00:00"


async def _imported(tmp_path, rig=None):
    rig = rig or await make_rig()
    mapped = sample_mapped(tmp_path, rig)
    conn = connect(rig)
    try:
        apply_import(conn, rig.dek, rig.user_id, mapped, run_id=RUN, imported_at=IMPORTED_AT,
                     general_id=general_id(rig))
    finally:
        conn.close()
    return rig


def undo(rig, run_id=RUN, force=False):
    conn = connect(rig)
    try:
        return undo_run(conn, rig.dek, rig.user_id, run_id, general_id=general_id(rig), force=force)
    finally:
        conn.close()


async def test_undo_removes_exactly_the_runs_rows(tmp_path):
    rig = await _imported(tmp_path)
    conn = connect(rig)       # rows the user made after the import are not the run's and stay
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('mine', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    result = undo(rig)
    assert result.removed == {"expense": 5, "recurring": 1, "comment": 1, "task": 3, "topup": 2, "project": 2}
    for table in ("money_expenses", "money_recurring", "task_comments", "money_topups"):
        assert table_count(rig, table) == 0
    assert table_count(rig, "tasks") == 1 and table_count(rig, "money_projects") == 1     # mine, and General
    assert table_count(rig, "import_links") == 0


async def test_undo_of_an_unknown_run_changes_nothing(tmp_path):
    rig = await _imported(tmp_path)
    with pytest.raises(UndoError):
        undo(rig, "no-such-run")
    assert table_count(rig, "tasks") == 3


async def test_an_edited_row_stops_the_undo_until_forced(tmp_path):
    rig = await _imported(tmp_path)
    conn = connect(rig)
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = 't2'", (LATER,))
    conn.close()
    with pytest.raises(UndoRefused) as stopped:
        undo(rig)
    assert "task t2" in str(stopped.value) and table_count(rig, "tasks") == 3 and table_count(rig, "import_links") == 14
    assert undo(rig, force=True).removed["task"] == 3
    assert table_count(rig, "tasks") == 0


async def test_something_added_to_an_imported_project_stops_the_undo(tmp_path):
    rig = await _imported(tmp_path)
    conn = connect(rig)
    conn.execute("INSERT INTO money_expenses (id, user_id, project_id, amount, spent_at, created_at, updated_at) "
                 "VALUES ('new-e', ?, 'pk', 'enc:x', '2026-11-01', 'n', 'n')", (rig.user_id,))
    conn.close()
    with pytest.raises(UndoRefused) as stopped:
        undo(rig)
    assert "project pk" in str(stopped.value)
    assert table_count(rig, "money_projects") == 3


async def test_generals_budget_is_restored_from_what_is_left(tmp_path):
    rig = await _imported(tmp_path)
    general = general_id(rig)
    conn = connect(rig)
    from roost.migrate.lazyclaw.writer_rows import Sealer
    s = Sealer(rig.dek, rig.user_id)
    conn.execute("INSERT INTO money_topups (id, user_id, project_id, amount, currency, kind, created_at, updated_at) "
                 "VALUES ('own', ?, ?, ?, 'EUR', 'credit', 'n', 'n')",
                 (rig.user_id, general, s.seal("money_topups", "amount", "20.00")))
    # as if the run had topped General up by 5 and set its budget to 25
    conn.execute("INSERT INTO money_topups (id, user_id, project_id, amount, currency, kind, created_at, updated_at) "
                 "VALUES ('gt', ?, ?, ?, 'EUR', 'credit', '2026-03-01T00:00:00+00:00', '2026-03-01T00:00:00+00:00')",
                 (rig.user_id, general, s.seal("money_topups", "amount", "5.00")))
    conn.execute("INSERT INTO import_links VALUES (?, 'lazyclaw', 'topup', 'gt', 'gt', ?, ?)", (rig.user_id, RUN, IMPORTED_AT))
    conn.execute("UPDATE money_projects SET budget = ? WHERE id = ?", (s.seal("money_projects", "budget", "25.00"), general))
    conn.close()
    undo(rig)
    conn = connect(rig)
    row = conn.execute("SELECT * FROM money_projects WHERE id = ?", (general,)).fetchone()
    assert unseal(rig, row, "money_projects", "budget") == "20.00"
    conn.close()


async def test_undo_never_touches_another_users_rows(tmp_path):
    rig = await _imported(tmp_path)
    other = await make_rig("bob")
    conn = connect(other)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('theirs', ?, 'enc:x', 'n', 'n')",
                 (other.user_id,))
    conn.close()
    undo(rig)
    assert table_count(other, "tasks") == 1


def cli(argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, getpass_fn=lambda p: SAMPLE_PASSWORD, input_fn=lambda p: OLD_USERNAME, out=out, err=err, env={}, roost_ports=(), lazyclaw_ports=())
    return code, out.getvalue(), err.getvalue()


async def test_the_cli_undoes_and_says_the_wipe_needs_the_backup(tmp_path):
    rig = await make_rig()
    source = build_sample(tmp_path / "lc.db")
    base = ["--source", str(source), "--roost-db", str(rig.db_path)]
    code, out, err = await asyncio.to_thread(cli, base + ["--apply", "--wipe", "--yes"])
    assert code == 0, err
    run_id = next(line.split()[-1] for line in out.splitlines() if line.startswith("Run id:"))
    code, out, err = await asyncio.to_thread(cli, ["--roost-db", str(rig.db_path), "--source", str(source), "--undo", run_id])
    assert code == 0, err
    assert table_count(rig, "tasks") == 0 and "pre-lazyclaw-" in out and "wipe" in out.lower()
    assert "roost.db-wal" in out and "roost.db-shm" in out
    code, _, err = await asyncio.to_thread(cli, ["--roost-db", str(rig.db_path), "--source", str(source), "--undo", "nope"])
    assert code == 1 and "no import run" in err.lower()
