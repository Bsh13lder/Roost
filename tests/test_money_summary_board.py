"""The Money tab's summary fields (Batch G, G8): Today, change, limits, top project, coming up, pins."""

from __future__ import annotations

from datetime import date, timedelta

from money_http import O, two_users

from roost.money.months import current_month, month_bounds, today_madrid


def _today() -> date:
    return date.fromisoformat(today_madrid())


def _last_month_day() -> str:
    first, _ = month_bounds(current_month())
    return (date.fromisoformat(first) - timedelta(days=1)).isoformat()


async def _project(client, name, **body) -> dict:
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _spend(client, project_id, amount, *, day=None, **body) -> dict:
    payload = {"amount": amount, "project_id": project_id, "note": "x", **body}
    if day:
        payload["spent_at"] = day
    r = await client.post("/api/money/expenses", json=payload, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _summary(client, month=None) -> dict:
    r = await client.get("/api/money/summary" + (f"?month={month}" if month else ""))
    assert r.status_code == 200, r.text
    return r.json()


def _row(summary, project_id):
    return next(row for row in summary["by_project"] if row["project_id"] == project_id)


async def test_by_project_carries_total_line_color_and_pin():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa", budget="1000", monthly_budget="500", color="#ef4444")
        await _spend(alice, casa["id"], "250")
        await alice.put(f"/api/projects/{casa['id']}/pin", json={"pinned": True}, headers=O)
        row = _row(await _summary(alice), casa["id"])
        assert row["color"] == "#ef4444" and row["pinned"] is True
        assert row["total"] == {"budget": "1000.00", "spent": "250.00", "remaining": "750.00",
                                "used_percent": 25, "tone": "ok"}
        assert row["month"]["used_percent"] == 50


async def test_today_totals_per_currency():
    async with two_users() as (alice, _, _):
        eur = await _project(alice, "Casa")
        usd = await _project(alice, "Trip", currency="USD")
        await _spend(alice, eur["id"], "84.20")
        await _spend(alice, usd["id"], "12")
        voided = await _spend(alice, eur["id"], "50")
        await alice.put(f"/api/money/expenses/{voided['id']}/void", json={"void": True}, headers=O)
        await _spend(alice, eur["id"], "7", day=(_today() - timedelta(days=1)).isoformat())
        today = (await _summary(alice))["today"]
        assert today == {"day": today_madrid(), "count": 2, "totals": {"EUR": "84.20", "USD": "12.00"}}


async def test_today_is_todays_even_when_a_past_month_is_asked():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        await _spend(alice, casa["id"], "5")
        past = await _summary(alice, _last_month_day()[:7])
        assert past["today"]["totals"] == {"EUR": "5.00"}


async def test_change_percent_is_main_currency_only_and_null_without_a_previous_month():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        usd = await _project(alice, "Trip", currency="USD")
        await _spend(alice, casa["id"], "136")
        none = await _summary(alice)
        assert (none["previous"], none["change_percent"]) == (None, None)
        await _spend(alice, casa["id"], "100", day=_last_month_day())
        await _spend(alice, usd["id"], "999", day=_last_month_day())       # another currency never counts
        got = await _summary(alice)
        assert got["previous"] == {"month": _last_month_day()[:7], "total": "100.00"}
        assert got["change_percent"] == 36
        await _spend(alice, casa["id"], "14")
        assert (await _summary(alice))["change_percent"] == 50


async def test_change_percent_can_be_negative():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        await _spend(alice, casa["id"], "50")
        await _spend(alice, casa["id"], "100", day=_last_month_day())
        assert (await _summary(alice))["change_percent"] == -50


async def test_limits_name_the_worst_first_with_unsigned_amounts():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa Nueva", monthly_budget="1500")
        side = await _project(alice, "Side business", currency="USD", monthly_budget="400")
        tidy = await _project(alice, "Tidy", monthly_budget="300")
        await _spend(alice, casa["id"], "1700.20")
        await _spend(alice, side["id"], "153")
        await _spend(alice, tidy["id"], "100")
        await _project(alice, "No limit")
        limits = (await _summary(alice))["limits"]
        assert limits["over_count"] == 1
        assert [(i["project"], i["currency"], i["amount"], i["over"], i["tone"]) for i in limits["items"]] == [
            ("Casa Nueva", "EUR", "200.20", True, "over"),
            ("Tidy", "EUR", "200.00", False, "ok"),
            ("Side business", "USD", "247.00", False, "ok"),
        ]
        assert limits["items"][0]["project_id"] == casa["id"]


async def test_limits_are_empty_without_any_monthly_limit():
    async with two_users() as (alice, _, _):
        await _project(alice, "Casa")
        assert (await _summary(alice))["limits"] == {"over_count": 0, "items": []}


async def test_top_project_leaves_out_general_and_other_currencies():
    async with two_users() as (alice, _, _):
        assert (await _summary(alice))["top_project"] is None
        casa = await _project(alice, "Casa", color="#22c55e")
        trip = await _project(alice, "Trip", currency="USD")
        await _spend(alice, trip["id"], "9000")
        await alice.post("/api/money/expenses", json={"amount": "5000", "note": "loose"}, headers=O)   # General
        await _spend(alice, casa["id"], "300")
        top = (await _summary(alice))["top_project"]
        assert top == {"project_id": casa["id"], "project": "Casa", "color": "#22c55e", "currency": "EUR",
                       "spent": "300.00", "share_percent": 6}          # 300 of the month's 5300 EUR


async def test_coming_up_is_31_days_per_currency():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        trip = await _project(alice, "Trip", currency="USD")
        empty = (await _summary(alice))["coming_up"]
        assert empty == {"days": 31, "count": 0, "totals": {}, "next": None}
        soon = (_today() + timedelta(days=3)).isoformat()
        later = (_today() + timedelta(days=9)).isoformat()
        for project, amount, note, day in ((casa, "9.99", "Netflix", later), (trip, "12", "Gym", soon)):
            r = await alice.post("/api/money/recurring", json={
                "amount": amount, "project_id": project["id"], "cadence": "monthly", "anchor_day": day,
                "note": note}, headers=O)
            assert r.status_code == 201, r.text
        coming = (await _summary(alice))["coming_up"]
        assert coming["days"] == 31 and coming["count"] == 2
        assert coming["totals"] == {"EUR": "9.99", "USD": "12.00"}
        assert coming["next"] == {"note": "Gym", "day": soon, "amount": "12.00", "currency": "USD"}


async def test_pinned_projects_and_starred_expenses():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa", budget="1000", monthly_budget="500")
        quiet = await _project(alice, "Quiet", monthly_budget="100")      # pinned, nothing spent this month
        await _project(alice, "Unpinned")
        for project in (casa, quiet):
            await alice.put(f"/api/projects/{project['id']}/pin", json={"pinned": True}, headers=O)
        mine = await _spend(alice, casa["id"], "40", starred=True, note="Paint")
        voided = await _spend(alice, casa["id"], "5", starred=True)
        await alice.put(f"/api/money/expenses/{voided['id']}/void", json={"void": True}, headers=O)
        await _spend(alice, casa["id"], "6")
        summary = await _summary(alice)
        assert [p["project_id"] for p in summary["pinned_projects"]] == [casa["id"], quiet["id"]]    # pin order
        first = summary["pinned_projects"][0]
        assert (first["project"], first["spent_month"], first["currency"]) == ("Casa", "46.00", "EUR")
        assert first["month"]["budget"] == "500.00" and first["total"]["budget"] == "1000.00"
        assert summary["pinned_projects"][1]["spent_month"] == "0.00"
        assert [e["id"] for e in summary["pinned_expenses"]] == [mine["id"]]
        assert summary["pinned_expenses"][0]["project"] == "Casa"


async def test_pinned_expenses_are_capped_and_newest_first():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa")
        for n in range(10):
            await _spend(alice, casa["id"], "1", starred=True, day=(_today() - timedelta(days=n)).isoformat())
        starred = (await _summary(alice))["pinned_expenses"]
        assert len(starred) == 8
        assert [e["spent_at"] for e in starred] == sorted((e["spent_at"] for e in starred), reverse=True)


async def test_summary_is_per_user():
    async with two_users() as (alice, bob, _):
        casa = await _project(alice, "Casa", monthly_budget="100")
        await alice.put(f"/api/projects/{casa['id']}/pin", json={"pinned": True}, headers=O)
        await _spend(alice, casa["id"], "150", starred=True)
        seen = await _summary(bob)
        assert seen["by_project"] == [] and seen["pinned_projects"] == [] and seen["pinned_expenses"] == []
        assert seen["limits"]["items"] == [] and seen["top_project"] is None
        assert seen["today"]["totals"] == {} and seen["previous"] is None


def _amount_strings(value, path="$"):
    if isinstance(value, float):
        raise AssertionError(f"a float at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"amount", "spent", "total", "budget", "remaining", "spent_month"} and isinstance(item, str):
                assert item.count(".") == 1 and len(item.split(".")[1]) == 2, f"{path}.{key}={item}"
            _amount_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _amount_strings(item, f"{path}[{index}]")


async def test_no_float_reaches_the_wire():
    async with two_users() as (alice, _, _):
        casa = await _project(alice, "Casa", budget="1000", monthly_budget="500")
        await alice.put(f"/api/projects/{casa['id']}/pin", json={"pinned": True}, headers=O)
        await _spend(alice, casa["id"], "33.3", starred=True)
        await _spend(alice, casa["id"], "10", day=_last_month_day())
        await alice.post("/api/money/recurring", json={
            "amount": "7", "project_id": casa["id"], "cadence": "monthly",
            "anchor_day": (_today() + timedelta(days=2)).isoformat()}, headers=O)
        _amount_strings(await _summary(alice))
