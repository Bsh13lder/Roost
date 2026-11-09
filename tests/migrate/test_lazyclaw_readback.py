"""After the commit, every row is read back through Roost's stores and the money matches the dry run (Task 7)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

from lazyclaw_factory import OLD_USER_ID, SAMPLE_DEK, enc_v1, insert
from roost.migrate.lazyclaw.readback import read_back
from roost.migrate.lazyclaw.report import build_report, WipeCounts
from roost.migrate.lazyclaw.writer import apply_import
from roost_harness import IMPORTED_AT, connect, general_id, make_rig, sample_mapped

RUN = "lazyclaw-rb-1"


def _extra(path):
    conn = sqlite3.connect(path)
    e = lambda text: enc_v1(text, SAMPLE_DEK)  # noqa: E731
    # an expense whose step was removed (it stays on the task), a valid step, a CAD one, an old archived spend
    for eid, amt, cur, sub, st in (("e6", 7.25, "EUR", "gone", "posted"), ("e7", 3.5, "EUR", "s2", "posted"),
                                   ("e8", 11.0, "CAD", None, "posted"), ("e9", 99.0, "EUR", None, "void")):
        insert(conn, "project_expenses", id=eid, user_id=OLD_USER_ID, project_id="pk", task_id="t4", subtask_id=sub,
               amount=amt, currency=cur, status=st, description=e("More"), spent_at="2026-03-06",
               created_at="2026-03-06 08:00:00")
    conn.close()


async def _imported(tmp_path, extra=_extra):
    rig = await make_rig()
    mapped = sample_mapped(tmp_path, rig, extra=extra)
    conn = connect(rig)
    try:
        apply_import(conn, rig.dek, rig.user_id, mapped, run_id=RUN, imported_at=IMPORTED_AT,
                     general_id=general_id(rig))
    finally:
        conn.close()
    return rig, mapped


async def test_the_stores_read_back_what_was_imported(tmp_path):
    rig, mapped = await _imported(tmp_path)
    result = await read_back(rig.cfg, rig.user_id, mapped, today_month="2026-10")
    assert result.ok, result.problems
    assert result.checked["tasks"] == 3 and result.checked["expenses"] == 9 and result.checked["projects"] == 3


async def test_roost_totals_equal_the_dry_runs_roost_way(tmp_path):
    rig, mapped = await _imported(tmp_path)
    result = await read_back(rig.cfg, rig.user_id, mapped, today_month="2026-10")
    lines = {l.name: l for l in build_report(mapped, WipeCounts(False)).projects}
    kitchen = lines["Kitchen"]
    assert kitchen.spent_roost == Decimal("25.50") + Decimal("7.25") + Decimal("3.50")   # EUR posted only
    assert result.spent["pk"] == kitchen.spent_roost and result.other_currencies["pk"] == {
        "USD": Decimal("10.00"), "CAD": Decimal("11.00")}
    assert result.task_spent["t4"] == Decimal("10.75")        # the removed step's expense stays on the task


async def test_a_wrong_number_is_reported_not_hidden(tmp_path):
    rig, mapped = await _imported(tmp_path)
    conn = connect(rig)
    conn.execute("DELETE FROM money_expenses WHERE id = 'e1'")
    conn.close()
    result = await read_back(rig.cfg, rig.user_id, mapped, today_month="2026-10")
    assert not result.ok
    assert any("expenses of project pk" in p for p in result.problems)
    assert any("spent of project pk" in p for p in result.problems)
    assert all("Buy kitchen" not in p for p in result.problems)       # problems never carry user text


async def test_a_dangling_link_and_the_recurring_rule_are_checked(tmp_path):
    rig, mapped = await _imported(tmp_path)
    assert (await read_back(rig.cfg, rig.user_id, mapped, today_month="2026-10")).ok     # r1 decrypts to 9.99 monthly
    conn = connect(rig)
    conn.execute("DELETE FROM money_recurring WHERE id = 'r1'")
    conn.close()
    result = await read_back(rig.cfg, rig.user_id, mapped, today_month="2026-10")
    assert any("recurring r1" in p for p in result.problems) and any("link recurring r1" in p for p in result.problems)
