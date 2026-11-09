"""The writer: one transaction, Roost's ciphertext, links, idempotent re-run (plan Task 6)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.migrate.lazyclaw import writer as writer_module
from roost.migrate.lazyclaw.writer import apply_import
from roost_harness import IMPORTED_AT, connect, general_id, make_rig, sample_mapped, table_count, unseal

RUN = "lazyclaw-test-1"


def run_apply(rig, mapped, run_id=RUN, wipe=True):
    conn = connect(rig)
    try:
        return apply_import(conn, rig.dek, rig.user_id, mapped, run_id=run_id, imported_at=IMPORTED_AT,
                            general_id=general_id(rig), wipe=wipe)
    finally:
        conn.close()


async def test_every_row_lands_trusted_and_linked(tmp_path):
    rig = await make_rig()
    mapped = sample_mapped(tmp_path, rig)
    result = run_apply(rig, mapped)
    assert not mapped.blocked
    assert table_count(rig, "tasks") == len(mapped.tasks) == 3
    assert table_count(rig, "task_comments") == len(mapped.comments) == 1
    assert table_count(rig, "money_expenses") == len(mapped.expenses) == 5
    assert table_count(rig, "money_topups") == len(mapped.topups) == 2          # b1 + the opening row
    assert table_count(rig, "money_recurring") == len(mapped.recurring) == 1
    # General is Roost's own; Kitchen and the archived trip are imported
    assert table_count(rig, "money_projects") == 3
    for table in ("tasks", "task_comments", "money_expenses", "money_topups", "money_recurring", "money_projects"):
        assert table_count(rig, table, "tainted = 1") == 0
    imported = sum(result.imported.values())
    assert table_count(rig, "import_links", "kind != 'wipe'") == imported == 3 + 1 + 5 + 2 + 1 + 2


async def test_text_is_enc_v2_under_roost_aads_and_never_plain_on_disk(tmp_path):
    rig = await make_rig()
    run_apply(rig, sample_mapped(tmp_path, rig))
    conn = connect(rig)
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = 't1'").fetchone()
        assert task["title"].startswith("enc:v2:") and unseal(rig, task, "tasks", "title") == \
            "Buy kitchen tiles from the big shop"
        assert unseal(rig, task, "tasks", "allocated_budget") == "40.00"
        assert task["project_id"] == "pk" and task["category"] is None and task["owner"] == "user"
        expense = conn.execute("SELECT * FROM money_expenses WHERE id = 'e1'").fetchone()
        assert unseal(rig, expense, "money_expenses", "amount") == "25.50" and expense["spent_at"] == "2026-03-05"
        assert {row[0] for row in conn.execute("SELECT kind FROM money_expenses")} == {"expense"}   # v21: never income
        topup = conn.execute("SELECT * FROM money_topups WHERE id = 'b1'").fetchone()
        assert unseal(rig, topup, "money_topups", "source") == "savings"
        rule = conn.execute("SELECT * FROM money_recurring WHERE id = 'r1'").fetchone()
        assert unseal(rig, rule, "money_recurring", "cadence") == "monthly"
        assert rule["anchor_day"] == rule["next_due"] == "2026-11-01"
        comment = conn.execute("SELECT * FROM task_comments").fetchone()
        assert unseal(rig, comment, "task_comments", "body") == "ok" and comment["step_id"] == "s1"
        steps = json.loads(unseal(rig, conn.execute("SELECT steps FROM tasks WHERE id = 't4'").fetchone(), "tasks", "steps"))
        assert [s["id"] for s in steps] == ["s1", "s2"]
    finally:
        conn.close()
    raw = rig.db_path.read_bytes()
    for plain in (b"Buy kitchen tiles", b"Hosting", b"savings", b"Kitchen"):
        assert plain not in raw


async def test_the_budget_equals_the_live_ledger(tmp_path):
    rig = await make_rig()
    run_apply(rig, sample_mapped(tmp_path, rig))
    conn = connect(rig)
    try:
        project = conn.execute("SELECT * FROM money_projects WHERE id = 'pk'").fetchone()
        assert unseal(rig, project, "money_projects", "budget") == "150.00"
        total = sum(Decimal(unseal(rig, r, "money_topups", "amount")) for r in conn.execute(
            "SELECT * FROM money_topups WHERE project_id = 'pk' AND deleted_at IS NULL"))
        assert total == Decimal("150.00")
    finally:
        conn.close()


async def test_a_rerun_imports_nothing_more_and_does_not_wipe(tmp_path):
    rig = await make_rig()
    mapped = sample_mapped(tmp_path, rig)
    first = run_apply(rig, mapped)
    conn = connect(rig)
    conn.execute("UPDATE tasks SET starred = 1 WHERE id = 't2'")     # a later edit must survive a re-run
    conn.close()
    second = run_apply(rig, mapped, run_id="lazyclaw-test-2")
    assert sum(second.imported.values()) == 0 and second.wiped is None
    assert first.wiped is not None
    assert table_count(rig, "tasks") == 3 and table_count(rig, "import_links", "kind != 'wipe'") == sum(first.imported.values())
    assert table_count(rig, "tasks", "starred = 1") == 1


async def test_the_wipe_clears_this_users_money_and_tasks_but_not_notes_general_or_other_users(tmp_path):
    rig = await make_rig()
    other = await make_rig("bob")
    for r in (rig, other):
        conn = connect(r)
        conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                     (f"old-{r.user_id}", r.user_id, "enc:x", "n", "n"))
        conn.execute("INSERT INTO notes (id, user_id, title, title_key, content, created_at, updated_at) "
                     "VALUES (?,?,?,?,?,?,?)", (f"n-{r.user_id}", r.user_id, "t", "k", "c", "n", "n"))
        conn.close()
    mapped = sample_mapped(tmp_path, rig)
    result = run_apply(rig, mapped)
    assert result.wiped is not None and result.wiped.tasks == 1
    assert table_count(rig, "tasks", "id = ?", (f"old-{rig.user_id}",)) == 0
    assert table_count(rig, "notes") == 1
    assert table_count(other, "tasks") == 1 and table_count(other, "notes") == 1


async def test_a_failing_row_rolls_back_everything_including_the_wipe(tmp_path, monkeypatch):
    rig = await make_rig()
    conn = connect(rig)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('keep', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    mapped = sample_mapped(tmp_path, rig)

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(writer_module, "insert_expense", boom)
    with pytest.raises(RuntimeError):
        run_apply(rig, mapped)
    assert table_count(rig, "tasks") == 1 and table_count(rig, "tasks", "id = 'keep'") == 1
    assert table_count(rig, "import_links") == 0 and table_count(rig, "money_projects") == 1


async def test_a_blocked_import_is_refused(tmp_path):
    from dataclasses import replace
    from roost.migrate.lazyclaw.models import Anomaly
    from roost.migrate.lazyclaw.writer import ImportRefused

    rig = await make_rig()
    mapped = replace(sample_mapped(tmp_path, rig), anomalies=(Anomaly("x", "ref", "bad", blocking=True),))
    with pytest.raises(ImportRefused):
        run_apply(rig, mapped)
    assert table_count(rig, "tasks") == 0


def _undo(rig, run_id):
    from roost.migrate.lazyclaw.undo import undo_run
    conn = connect(rig)
    try:
        return undo_run(conn, rig.dek, rig.user_id, run_id, general_id=general_id(rig))
    finally:
        conn.close()


async def test_no_wipe_unless_asked(tmp_path):
    rig = await make_rig()
    conn = connect(rig)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('keep', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    result = run_apply(rig, sample_mapped(tmp_path, rig), wipe=False)
    assert result.wiped is None and table_count(rig, "tasks", "id = 'keep'") == 1
    assert table_count(rig, "import_links", "kind = 'wipe'") == 0


async def test_the_wipe_happens_once_ever_even_after_an_undo(tmp_path):
    rig = await make_rig()
    mapped = sample_mapped(tmp_path, rig)
    assert run_apply(rig, mapped).wiped is not None
    _undo(rig, RUN)
    assert table_count(rig, "import_links", "kind = 'wipe'") == 1       # the marker outlives the undo
    conn = connect(rig)
    conn.execute("INSERT INTO tasks (id, user_id, title, created_at, updated_at) VALUES ('mine', ?, 'enc:x', 'n', 'n')",
                 (rig.user_id,))
    conn.close()
    again = run_apply(rig, mapped, run_id="lazyclaw-test-2")
    assert again.wiped is None and table_count(rig, "tasks", "id = 'mine'") == 1


async def test_a_wipe_is_never_added_after_a_plain_import(tmp_path):
    rig = await make_rig()
    mapped = sample_mapped(tmp_path, rig)
    run_apply(rig, mapped, wipe=False)
    assert run_apply(rig, mapped, run_id="lazyclaw-test-2", wipe=True).wiped is None


async def test_general_budget_is_recomputed_from_the_ledger_when_not_wiping(tmp_path):
    import dataclasses
    from roost.migrate.lazyclaw.writer_rows import Sealer
    rig = await make_rig()
    gid = general_id(rig)
    s = Sealer(rig.dek, rig.user_id)
    mapped = sample_mapped(tmp_path, rig)
    mapped = dataclasses.replace(mapped, projects=tuple(
        dataclasses.replace(p, budget=Decimal("5.00")) if p.is_general else p for p in mapped.projects))
    conn = connect(rig)
    conn.execute("INSERT INTO money_topups (id, user_id, project_id, amount, currency, source, kind, created_at, "
                 "updated_at, tainted) VALUES ('mine', ?, ?, ?, 'EUR', ?, 'credit', 'n', 'n', 0)",
                 (rig.user_id, gid, s.money("money_topups", "amount", Decimal("10.00")), s.seal("money_topups", "source", "x")))
    conn.execute("UPDATE money_projects SET budget = ? WHERE id = ?", (s.money("money_projects", "budget", Decimal("10.00")), gid))
    conn.close()
    run_apply(rig, mapped, wipe=False)
    conn = connect(rig)
    try:
        row = conn.execute("SELECT * FROM money_projects WHERE id = ?", (gid,)).fetchone()
        assert unseal(rig, row, "money_projects", "budget") == "10.00"
    finally:
        conn.close()
