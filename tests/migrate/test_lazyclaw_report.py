import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from lazyclaw_factory import OLD_USERNAME, SAMPLE_PASSWORD, build_sample
from roost.migrate.lazyclaw.mapping import map_lazyclaw
from roost.migrate.lazyclaw.models import RoostContext
from roost.migrate.lazyclaw.old_crypto import load_old_keys_by_password
from roost.migrate.lazyclaw.reader import read_lazyclaw
from roost.migrate.lazyclaw.report import WipeCounts, build_report, render_report, truncate

CTX = RoostContext(user_id="new", import_day=date(2026, 10, 20), imported_at="2026-10-20T10:00:00+00:00")


@pytest.fixture(scope="module")
def mapped(tmp_path_factory):
    path = build_sample(tmp_path_factory.mktemp("r") / "lc.db")
    conn = sqlite3.connect(path)
    with load_old_keys_by_password(conn, OLD_USERNAME, SAMPLE_PASSWORD) as keys:
        data = read_lazyclaw(conn, keys)
    conn.close()
    return map_lazyclaw(data, CTX)


WIPE = WipeCounts(available=True, tasks=7, task_comments=2, expenses=11, topups=3, recurring=1, projects=4)


def test_counts_are_fixed(mapped):
    c = build_report(mapped, WIPE).counts
    assert c["tasks_by_status"] == {"done": 1, "in_progress": 1, "todo": 1}
    assert (c["steps"], c["comments"]) == (2, 1)
    assert (c["projects_active"], c["projects_archived"]) == (2, 1)
    assert (c["topups_live"], c["topups_opening"], c["topups_history"]) == (2, 1, 0)
    assert (c["expenses_posted"], c["expenses_void"]) == (4, 1)
    assert (c["recurring_active"], c["recurring_paused"]) == (1, 0)
    assert (c["tainted"], c["clean"]) == (0, 3)
    assert build_report(mapped, WIPE).skipped == {"tasks_deleted": 1}
    assert build_report(mapped, WIPE).lost["progress_log_entries"] == 2


def test_per_project_and_currency_numbers(mapped):
    r = build_report(mapped, WIPE)
    kitchen = next(p for p in r.projects if p.name == "Kitchen")
    assert kitchen.currency == "EUR" and kitchen.budget == Decimal("150.00")
    assert kitchen.live_topups == Decimal("150.00")
    assert kitchen.spent_lazyclaw == {"EUR": Decimal("25.50"), "USD": Decimal("10.00")}  # never added across currencies
    assert kitchen.spent_roost == Decimal("25.50")    # only the project's currency
    assert kitchen.remaining == Decimal("124.50")
    trip = next(p for p in r.projects if p.name.startswith("Trip"))
    assert trip.budget is None and trip.spent_roost == Decimal("20.00") and trip.remaining is None
    assert r.totals["EUR"].budget == Decimal("150.00")
    assert r.totals["EUR"].spent_roost == Decimal("28.70")
    assert r.totals["USD"].spent_roost == Decimal("20.00")


def test_anomalies_listed(mapped):
    r = build_report(mapped, WIPE)
    kinds = {a.kind for a in r.anomalies}
    assert {"budget_gap", "recurring_not_convertible", "allocated_budget_dropped"} & kinds >= {"budget_gap", "recurring_not_convertible"}
    assert r.blocked is False


def test_samples_truncated_and_no_full_title(mapped):
    r = build_report(mapped, WIPE)
    text = render_report(r)
    assert "Buy kitchen tiles from the big shop" not in text
    assert "Renew passport application" not in text
    assert "Buy kitchen tiles from" in text  # first 23 chars + ellipsis
    assert all(len(s) <= 24 for group in r.samples.values() for s in group)
    assert all(len(group) <= 5 for group in r.samples.values())


def test_truncate():
    assert truncate("short") == "short"
    assert truncate("x" * 24) == "x" * 24
    assert truncate("y" * 30) == "y" * 23 + "…" and len(truncate("y" * 30)) == 24
    assert truncate(None) == ""


def test_wipe_counts_are_in_the_text(mapped):
    text = render_report(build_report(mapped, WIPE))
    for needle in ("7 tasks", "2 task comments", "11 expenses", "3 top-ups", "1 recurring", "4 projects"):
        assert needle in text
    assert "notes and documents are left alone" in text.lower()
    unavailable = render_report(build_report(mapped, WipeCounts(available=False)))
    assert "could not be counted" in unavailable.lower()


def test_blocked_report_says_do_not_apply(mapped):
    from dataclasses import replace
    from roost.migrate.lazyclaw.models import Anomaly
    bad = replace(mapped, anomalies=mapped.anomalies + (Anomaly("task_invalid", "t9", "Unknown priority value.", True),))
    r = build_report(bad, WIPE)
    assert r.blocked and "must be fixed" in render_report(r)
    assert "t9" in render_report(r)


def test_text_shows_spent_per_currency_and_never_a_mixed_sum(mapped):
    text = render_report(build_report(mapped, WIPE))
    assert "EUR 25.50, USD 10.00" in text and "35.50" not in text
