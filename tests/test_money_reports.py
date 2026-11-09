"""Money reports (Task 14): the trend, the CSV export and the General inbox."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from money_http import O, two_users

from roost.money.models import Expense
from roost.money.months import current_month, today_madrid
from roost.money.reports import csv_text, guard_cell, months_ending, trend


def _expense(day, amount, currency="EUR", status="posted", **kw) -> Expense:
    return Expense(id=kw.pop("id", f"e-{day}-{amount}-{currency}"), user_id="u", project_id=kw.pop("project_id", "p"),
                   amount=Decimal(amount), currency=currency, description=kw.pop("description", None),
                   vendor=kw.pop("vendor", None), spent_at=day, status=status, created_at="2026-01-01T00:00:00+00:00",
                   updated_at="2026-01-01T00:00:00+00:00", created_by_bot=None, tainted=False, **kw)


def test_months_ending_counts_back_across_a_year():
    assert months_ending("2026-02", 4) == ("2025-11", "2025-12", "2026-01", "2026-02")
    assert months_ending("2026-10", 1) == ("2026-10",)


def test_trend_is_per_currency_and_never_mixed():
    rows = trend([
        _expense("2026-09-03", "10.00"), _expense("2026-09-20", "5.50"), _expense("2026-09-21", "7.00", "USD"),
        _expense("2026-10-02", "1.00"), _expense("2026-10-03", "99.00", status="void"),
        _expense("2026-01-01", "50.00"),                                   # outside the window
    ], ("2026-08", "2026-09", "2026-10"))
    assert [(r.month, dict(r.totals)) for r in rows] == [
        ("2026-08", {}), ("2026-09", {"EUR": Decimal("15.50"), "USD": Decimal("7.00")}),
        ("2026-10", {"EUR": Decimal("1.00")})]


def test_guard_cell_prefixes_formula_starts():
    assert guard_cell("=1+1") == "'=1+1"
    for danger in ("+1", "-2", "@SUM(A1)", "\tx", "\rx", "  =cmd|' /C calc'!A0"):
        assert guard_cell(danger).startswith("'"), danger
    for safe in ("lunch", "12 - 3", "a=b", "", None):
        assert guard_cell(safe) == (safe or "")


def test_guard_cell_catches_full_width_and_keeps_the_original_text():
    assert guard_cell("＝1+1") == "'＝1+1"
    for danger in ("＋1", "－1", "＠x", "  ＝2", "\uff1d1"):
        assert guard_cell(danger) == f"'{danger}", danger
    assert guard_cell("ｅ＝mc") == "ｅ＝mc"


def test_csv_has_headers_and_decimal_strings_and_guards_formula_cells():
    text = csv_text([_expense("2026-10-02", "0.10", description="=1+1", vendor='Cafe, "Bar"', is_favorite=True),
                     _expense("2026-10-03", "1234.50", currency="USD", status="void", description="+49 call")],
                    {"p": "@Trip"})
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["Date", "Project", "Amount", "Currency", "Note", "Vendor", "Status", "Starred", "Kind"]
    assert rows[1] == ["2026-10-02", "'@Trip", "0.10", "EUR", "'=1+1", 'Cafe, "Bar"', "posted", "yes", "expense"]
    assert rows[2] == ["2026-10-03", "'@Trip", "1234.50", "USD", "'+49 call", "", "void", "no", "expense"]


async def _project(client, name, **body):
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _spend(client, amount, spent_at="today", **body):
    r = await client.post("/api/money/expenses", json={"amount": amount, "spent_at": spent_at, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def test_trend_route_bounds_and_months():
    async with two_users() as (alice, bob, _):
        trip = await _project(alice, "Trip")
        await _spend(alice, "10", project_id=trip["id"])
        await _spend(alice, "5", currency="USD")
        await _spend(alice, "99")
        voided = await _spend(alice, "1000")
        await alice.put(f"/api/money/expenses/{voided['id']}/void", json={"void": True}, headers=O)
        await _spend(bob, "777")
        everything = (await alice.get("/api/money/trend?months=3")).json()["months"]
        assert len(everything) == 3 and everything[-1]["month"] == current_month()
        assert everything[-1]["totals"] == {"EUR": "109.00", "USD": "5.00"} and everything[0]["totals"] == {}
        one = (await alice.get(f"/api/money/trend?months=1&project_id={trip['id']}")).json()["months"]
        assert one == [{"month": current_month(), "totals": {"EUR": "10.00"}}]
        assert len((await alice.get("/api/money/trend")).json()["months"]) == 6
        for bad in ("months=0", "months=25", "months=x"):
            assert (await alice.get(f"/api/money/trend?{bad}")).status_code == 422, bad
        assert (await bob.get(f"/api/money/trend?project_id={trip['id']}")).status_code == 404
        assert (await alice.get("/api/money/trend?project_id=nope")).status_code == 404


async def test_csv_route_headers_ranges_and_per_user(monkeypatch):
    async with two_users() as (alice, bob, _):
        trip = await _project(alice, "=HYPERLINK(\"x\")")
        await _spend(alice, "12.50", project_id=trip["id"], note="@evil", vendor="-v")
        await _spend(alice, "3", spent_at="2026-01-05")
        await _spend(bob, "777", note="bob's secret")
        r = await alice.get(f"/api/money/export.csv?from={current_month()}&to={current_month()}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert f'filename="roost-expenses-{current_month()}.csv"' in r.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0][0] == "Date" and len(rows) == 2
        assert rows[1][1:7] == ["'=HYPERLINK(\"x\")", "12.50", "EUR", "'@evil", "'-v", "posted"]
        assert "secret" not in r.text and "777" not in r.text
        both = (await alice.get(f"/api/money/export.csv?from=2026-01&to={current_month()}")).text
        assert [row[0] for row in csv.reader(io.StringIO(both))][1:] == ["2026-01-05", today_madrid()]  # oldest first
        default = (await alice.get("/api/money/export.csv")).text
        assert len(list(csv.reader(io.StringIO(default)))) == 2
        for bad in ("from=2026-13", "from=2026-10&to=2026-01", "from=x", "to=2026-1"):
            assert (await alice.get(f"/api/money/export.csv?{bad}")).status_code == 422, bad
        assert (await bob.get(f"/api/money/export.csv?project_id={trip['id']}")).status_code == 404
        monkeypatch.setattr("roost.gateway.routes.money_reports.CSV_EXPORT_MAX_ROWS", 1)
        capped = await alice.get(f"/api/money/export.csv?from=2026-01&to={current_month()}")
        assert capped.headers["x-rows-cut"] == "yes" and len(list(csv.reader(io.StringIO(capped.text)))) == 2
        assert [row[0] for row in csv.reader(io.StringIO(capped.text))][1:] == [today_madrid()]       # the newest kept


async def test_general_inbox_pages_newest_first(monkeypatch):
    async with two_users() as (alice, bob, _):
        trip = await _project(alice, "Trip")
        await _spend(alice, "1", project_id=trip["id"])
        days = ["2026-10-01", "2026-10-02", "2026-10-02", "2026-10-03", "2026-10-04"]
        made = [await _spend(alice, str(n + 1), spent_at=day) for n, day in enumerate(days)]
        await _spend(bob, "50", spent_at="2026-10-02")
        monkeypatch.setattr("roost.money.service.GENERAL_INBOX_PAGE", 2)
        first = (await alice.get("/api/money/general")).json()
        assert [e["spent_at"] for e in first["expenses"]] == ["2026-10-04", "2026-10-03"] and first["next"] == "2026-10-03"
        second = (await alice.get(f"/api/money/general?before={first['next']}")).json()
        assert [e["spent_at"] for e in second["expenses"]][:2] == ["2026-10-02", "2026-10-02"]
        got = [e["id"] for e in second["expenses"]]
        assert set(got) >= {made[1]["id"], made[2]["id"]}                  # a day is never split across pages
        rest = (await alice.get(f"/api/money/general?before={second['next']}")).json() if second["next"] else None
        every = [e["id"] for page in (first, second, *([rest] if rest else [])) for e in page["expenses"]]
        assert sorted(every) == sorted(m["id"] for m in made) and len(set(every)) == len(every)
        assert all(e["project"] == "General" for e in first["expenses"])
        for bad in ("before=yesterday", "before=2026-1-1", "before=20261001"):
            assert (await alice.get(f"/api/money/general?{bad}")).status_code == 422, bad
        assert (await bob.get("/api/money/general")).json()["expenses"][0]["amount"] == "50.00"


async def test_general_inbox_is_empty_before_general_exists():
    async with two_users() as (alice, _, _):
        assert (await alice.get("/api/money/general")).json() == {"expenses": [], "next": None}


async def test_reports_catch_up_repeating_charges_first():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        start = (date.fromisoformat(today_madrid()).replace(day=1)).isoformat()
        r = await alice.post("/api/money/recurring", json={"amount": "9.99", "project_id": casa["id"],
                                                           "cadence": "monthly", "anchor_day": start, "note": "Net"},
                             headers=O)
        assert r.status_code == 201
        assert (await alice.get("/api/money/trend?months=1")).json()["months"][0]["totals"] == {"EUR": "9.99"}
        rule = (await alice.post("/api/money/recurring", json={"amount": "1.00", "project_id": casa["id"],
                                                               "cadence": "monthly", "anchor_day": start}, headers=O))
        text = (await alice.get("/api/money/export.csv")).text
        assert "Net" in text and text.count("posted") == 2 and rule.status_code == 201


async def test_reports_need_a_login():
    from fastapi.testclient import TestClient
    from roost.gateway.app import create_app
    anon = TestClient(create_app())
    for path in ("/api/money/trend", "/api/money/export.csv", "/api/money/general"):
        assert anon.get(path).status_code == 401, path
