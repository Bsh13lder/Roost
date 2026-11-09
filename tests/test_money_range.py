"""``GET /api/money/range`` and the pure day totals behind it (Batch G, G9)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
from money_http import O, two_users

from roost.constants import MONEY_RANGE_MAX_DAYS
from roost.gateway.app import create_app
from roost.money.day_totals import day_totals, range_summary
from roost.money.models import KIND_INCOME, Expense
from roost.money.months import today_madrid

_AT = "2026-10-01T09:00:00+00:00"


def _today() -> date:
    return date.fromisoformat(today_madrid())


def _ago(days: int) -> str:
    return (_today() - timedelta(days=days)).isoformat()


def _expense(amount: str, day: str, *, currency="EUR", status="posted", kind="expense") -> Expense:
    return Expense(id=f"{day}-{amount}-{currency}", user_id="u", project_id="p", amount=Decimal(amount),
                   currency=currency, description=None, vendor=None, spent_at=day, status=status, created_at=_AT,
                   updated_at=_AT, created_by_bot=None, tainted=False, kind=kind)


async def _project(client, name="Casa", **body) -> dict:
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _spend(client, project_id, amount, day, **body) -> dict:
    r = await client.post("/api/money/expenses", json={
        "amount": amount, "project_id": project_id, "spent_at": day, "note": "x", **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _range(client, first, last, **params):
    query = "&".join(f"{k}={v}" for k, v in {"from": first, "to": last, **params}.items())
    return await client.get(f"/api/money/range?{query}")


def test_day_totals_per_currency():
    days = day_totals((_expense("10.00", "2026-10-02"), _expense("5.50", "2026-10-02"),
                       _expense("12.00", "2026-10-02", currency="USD"), _expense("3.00", "2026-10-01")), "EUR")
    assert [(d.day, d.count, dict(d.totals)) for d in days] == [
        ("2026-10-02", 3, {"EUR": Decimal("15.50"), "USD": Decimal("12.00")}),
        ("2026-10-01", 1, {"EUR": Decimal("3.00")}),
    ]


def test_void_is_listed_but_not_counted():
    expenses = (_expense("10.00", "2026-10-02"), _expense("99.00", "2026-10-02", status="void"),
                _expense("7.00", "2026-10-03", status="void"), _expense("500.00", "2026-10-02", kind=KIND_INCOME))
    days = day_totals(expenses, "EUR")
    assert [(d.day, d.count, dict(d.totals), d.bar_percent) for d in days] == [
        ("2026-10-03", 0, {}, 0), ("2026-10-02", 1, {"EUR": Decimal("10.00")}, 100)]
    summary = range_summary(expenses)
    assert (summary.count, dict(summary.totals)) == (1, {"EUR": Decimal("10.00")})


def test_bar_percent_is_main_currency_against_the_biggest_day():
    days = day_totals((_expense("200.00", "2026-10-01"), _expense("50.00", "2026-10-02"),
                       _expense("1000.00", "2026-10-03", currency="USD"), _expense("33.33", "2026-10-04")), "EUR")
    assert {d.day: d.bar_percent for d in days} == {
        "2026-10-01": 100, "2026-10-02": 25, "2026-10-03": 0, "2026-10-04": 17}


async def test_range_answers_days_summary_and_rows():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        usd = await _project(alice, "Trip", currency="USD")
        await _spend(alice, casa["id"], "10", _ago(1))
        await _spend(alice, casa["id"], "30", _ago(1))
        await _spend(alice, usd["id"], "12", _ago(1))
        await _spend(alice, casa["id"], "20", _ago(3))
        await _spend(alice, casa["id"], "999", _ago(40))                        # outside the range
        r = await _range(alice, _ago(5), _ago(0))
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["from"], body["to"], body["currency"]) == (_ago(5), _ago(0), "EUR")
        assert body["summary"] == {"count": 4, "totals": {"EUR": "60.00", "USD": "12.00"}}
        assert body["days"] == [
            {"day": _ago(1), "count": 3, "totals": {"EUR": "40.00", "USD": "12.00"}, "bar_percent": 100},
            {"day": _ago(3), "count": 1, "totals": {"EUR": "20.00"}, "bar_percent": 50}]
        assert len(body["expenses"]) == 4 and all(e["project"] in {"Casa", "Trip"} for e in body["expenses"])


async def test_void_rows_are_listed_in_the_range_but_not_counted():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        gone = await _spend(alice, casa["id"], "40", _ago(1))
        await _spend(alice, casa["id"], "10", _ago(1))
        await alice.put(f"/api/money/expenses/{gone['id']}/void", json={"void": True}, headers=O)
        body = (await _range(alice, _ago(2), _ago(0))).json()
        assert sorted(e["status"] for e in body["expenses"]) == ["posted", "void"]
        assert body["summary"] == {"count": 1, "totals": {"EUR": "10.00"}}


async def test_range_is_per_user_and_a_foreign_project_is_404():
    async with two_users() as (alice, bob, _):
        casa = await _project(alice)
        await _spend(alice, casa["id"], "10", _ago(1))
        assert (await _range(bob, _ago(5), _ago(0))).json()["expenses"] == []
        assert (await _range(bob, _ago(5), _ago(0), project_id=casa["id"])).status_code == 404
        assert (await _range(alice, _ago(5), _ago(0), project_id=casa["id"])).status_code == 200
        other = await _project(alice, "Other")
        narrowed = (await _range(alice, _ago(5), _ago(0), project_id=other["id"])).json()
        assert narrowed["expenses"] == [] and narrowed["days"] == []


async def test_range_needs_a_session():
    async with two_users() as (_, _, app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anon:
            assert (await _range(anon, _ago(5), _ago(0))).status_code == 401


async def test_range_bounds_are_422():
    async with two_users() as (alice, _, _):
        for first, last in (("2026-13-01", "2026-13-02"), ("yesterday", "today"), (_ago(1), _ago(5)),
                            (_ago(MONEY_RANGE_MAX_DAYS + 5), _ago(0)), ("2026-1-1", "2026-1-2")):
            r = await _range(alice, first, last)
            assert r.status_code == 422, (first, last, r.text)
        assert (await alice.get("/api/money/range")).status_code == 422
        widest = await _range(alice, _ago(MONEY_RANGE_MAX_DAYS - 1), _ago(0))
        assert widest.status_code == 200


async def test_a_future_end_is_clamped_to_today():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        await _spend(alice, casa["id"], "10", _ago(0))
        future = (_today() + timedelta(days=30)).isoformat()
        body = (await _range(alice, _ago(2), future)).json()
        assert body["to"] == today_madrid() and body["summary"]["count"] == 1
        nothing = (await _range(alice, (_today() + timedelta(days=3)).isoformat(), future)).json()
        assert (nothing["expenses"], nothing["days"], nothing["summary"]) == ([], [], {"count": 0, "totals": {}})


async def test_range_catches_up_repeating_charges_first():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        r = await alice.post("/api/money/recurring", json={
            "amount": "9.99", "project_id": casa["id"], "cadence": "weekly", "anchor_day": _ago(1), "note": "Gym"},
            headers=O)
        assert r.status_code == 201, r.text
        body = (await _range(alice, _ago(2), _ago(0))).json()          # no other read has run
        assert [e["description"] for e in body["expenses"]] == ["Gym"] and body["summary"]["count"] == 1


async def test_repeat_names_the_cadence():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        await alice.post("/api/money/recurring", json={
            "amount": "9.99", "project_id": casa["id"], "cadence": "monthly", "anchor_day": _ago(1), "note": "Netflix"},
            headers=O)
        await _spend(alice, casa["id"], "5", _ago(1))
        rows = {e["description"]: e for e in (await _range(alice, _ago(2), _ago(0))).json()["expenses"]}
        assert rows["Netflix"]["repeat"] == "monthly" and rows["x"]["repeat"] is None


async def test_amounts_are_decimal_strings():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        await _spend(alice, casa["id"], "33.3", _ago(1))
        body = (await _range(alice, _ago(2), _ago(0))).json()
        amounts = [body["expenses"][0]["amount"], *body["days"][0]["totals"].values(), *body["summary"]["totals"].values()]
        assert amounts == ["33.30", "33.30", "33.30"]
        assert isinstance(body["days"][0]["bar_percent"], int)


async def test_range_names_the_general_project_so_an_expense_can_go_back_to_it():
    async with two_users() as (alice, bob, _):
        assert (await _range(alice, _ago(1), _ago(0))).json()["general_project_id"] is None     # none made yet
        loose = await alice.post("/api/money/expenses", json={"amount": "3", "spent_at": _ago(0)}, headers=O)
        assert loose.status_code == 201
        body = (await _range(alice, _ago(1), _ago(0))).json()
        assert body["general_project_id"] == loose.json()["project_id"]
        assert (await _range(bob, _ago(1), _ago(0))).json()["general_project_id"] is None


async def test_rows_carry_their_project_colour_for_the_dot():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, color="#ef4444")
        await _spend(alice, casa["id"], "10", _ago(1))
        await alice.post("/api/money/expenses", json={"amount": "3", "spent_at": _ago(1)}, headers=O)      # General
        colours = {e["project"]: e["project_color"] for e in (await _range(alice, _ago(2), _ago(0))).json()["expenses"]}
        assert colours["Casa"] == "#ef4444" and colours["General"].startswith("#")
