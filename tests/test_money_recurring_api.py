"""Repeating expenses over HTTP (Task 12): rules, upcoming charges, the expense line's cadence."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from money_http import O, two_users

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.money.months import today_madrid


def _sql(query: str, *params):
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        rows = con.execute(query, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _days_ago(n: int) -> str:
    return (date.fromisoformat(today_madrid()) - timedelta(days=n)).isoformat()


async def _project(client, name="Casa", **body) -> dict:
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _rule(client, project_id, **body) -> dict:
    r = await client.post("/api/money/recurring", json={
        "amount": "9,99", "project_id": project_id, "cadence": "weekly", "anchor_day": _days_ago(15), "note": "Gym",
        **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _charges(client, since_days: int) -> list[dict]:
    """Every expense from ``since_days`` ago to today: the list is one month, and the 1st reads last month too."""
    months = sorted({_days_ago(since_days)[:7], today_madrid()[:7]})
    return [e for m in months for e in (await client.get("/api/money/expenses", params={"month": m})).json()]


async def test_a_rule_makes_its_charges_when_money_is_read():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        rule = await _rule(alice, casa["id"])
        assert (rule["amount"], rule["cadence"], rule["note"], rule["paused"], rule["project"]) == (
            "9.99", "weekly", "Gym", False, "Casa")
        charges = [e for e in await _charges(alice, 15) if e["recurring_id"] == rule["id"]]
        # 15 days back, weekly: the anchor day, +7 and +14 (the month may start after the oldest, never after today)
        assert 1 <= len(charges) <= 3 and all(c["description"] == "Gym" and c["amount"] == "9.99" for c in charges)
        again = [e for e in await _charges(alice, 15) if e["recurring_id"] == rule["id"]]
        assert len(again) == len(charges)
        summary = (await alice.get("/api/money/summary")).json()
        this_month = [c for c in charges if c["spent_at"][:7] == today_madrid()[:7]]   # the summary is this month
        assert summary["expense_count"] == len(this_month)
        page = (await alice.get(f"/api/projects/{casa['id']}")).json()
        assert [c["recurring_id"] for c in page["upcoming_charges"]] == [rule["id"]] * len(page["upcoming_charges"])
        assert page["upcoming_charges"] and all(c["day"] > today_madrid() for c in page["upcoming_charges"])


async def test_an_expense_line_with_a_cadence_makes_the_rule_and_the_first_charge():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        r = await alice.post("/api/money/expenses", json={
            "amount": "9.99", "project_id": casa["id"], "note": "Netflix", "spent_at": "5 days ago",
            "cadence": "monthly"}, headers=O)
        assert r.status_code == 201, r.text
        first = r.json()
        assert first["spent_at"] == _days_ago(5) and first["recurring_id"]
        rules = (await alice.get("/api/money/recurring")).json()
        assert [(x["id"], x["cadence"], x["anchor_day"], x["note"]) for x in rules] == [
            (first["recurring_id"], "monthly", _days_ago(5), "Netflix")]
        assert rules[0]["next_due"] > today_madrid()
        listed = [e for e in await _charges(alice, 5) if e["recurring_id"]]
        assert len(listed) == 1                                        # the first charge is the typed day, once
        task = (await alice.post("/api/tasks", json={"title": "t", "project_id": casa["id"]}, headers=O)).json()
        bad = await alice.post("/api/money/expenses", json={"amount": "1", "task_id": task["id"], "cadence": "weekly"},
                               headers=O)
        assert bad.status_code == 422


async def test_archived_project_pauses_its_rule():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        rule = await _rule(alice, casa["id"], anchor_day=_days_ago(1), cadence="weekly")
        await alice.get("/api/money/expenses")                          # the first charge, yesterday
        await alice.patch(f"/api/projects/{casa['id']}", json={"status": "archived"}, headers=O)
        _sql("UPDATE money_recurring SET next_due = ? WHERE id = ?", _days_ago(14), rule["id"])    # long behind
        before = len(_sql("SELECT id FROM money_expenses WHERE recurring_id = ?", rule["id"]))
        await alice.get("/api/money/expenses")
        assert len(_sql("SELECT id FROM money_expenses WHERE recurring_id = ?", rule["id"])) == before
        assert (await alice.get("/api/money/upcoming")).json() == []
        assert (await alice.get("/api/money/recurring")).json()[0]["paused"] is True
        await alice.patch(f"/api/projects/{casa['id']}", json={"status": "active"}, headers=O)
        await alice.get("/api/money/expenses")
        assert len(_sql("SELECT id FROM money_expenses WHERE recurring_id = ?", rule["id"])) == before   # no back-fill


async def test_upcoming_charges_lists_the_next_31_days_over_http():
    async with two_users() as (alice, _, _):
        casa, other = await _project(alice), await _project(alice, "Other")
        await _rule(alice, casa["id"], anchor_day=_days_ago(1))
        await _rule(alice, other["id"], anchor_day=_days_ago(1), note="Other thing")
        every = (await alice.get("/api/money/upcoming")).json()
        mine = (await alice.get(f"/api/money/upcoming?project_id={casa['id']}")).json()
        assert 4 <= len(mine) <= 5 and {c["project_id"] for c in mine} == {casa["id"]}
        assert len(every) == 2 * len(mine)
        assert [c["day"] for c in every] == sorted(c["day"] for c in every)
        assert set(mine[0]) == {"recurring_id", "project_id", "day", "amount", "currency", "note"}


async def test_recurring_routes_are_per_user():
    async with two_users() as (alice, bob, _):
        casa = await _project(alice)
        shed = await _project(bob, "Shed")
        rule = await _rule(alice, casa["id"])
        path = f"/api/money/recurring/{rule['id']}"
        assert (await bob.patch(path, json={"amount": "1"}, headers=O)).status_code == 404
        assert (await bob.delete(path, headers=O)).status_code == 404
        assert (await bob.get("/api/money/recurring")).json() == []
        assert (await bob.get("/api/money/upcoming")).json() == []
        assert (await bob.get(f"/api/money/upcoming?project_id={casa['id']}")).status_code == 404
        assert (await bob.get(f"/api/money/recurring?project_id={casa['id']}")).status_code == 404
        foreign = await alice.post("/api/money/recurring", json={"amount": "1", "project_id": shed["id"],
                                                                  "cadence": "weekly"}, headers=O)
        assert (foreign.status_code, foreign.json()["detail"]) == (422, "No such project.")
        moved = await alice.patch(path, json={"project_id": shed["id"]}, headers=O)
        assert moved.status_code == 422
        assert (await alice.patch("/api/money/recurring/none", json={"amount": "1"}, headers=O)).status_code == 404
        assert (await alice.delete("/api/money/recurring/none", headers=O)).status_code == 404
        assert _sql("SELECT project_id FROM money_recurring WHERE id = ?", rule["id"])[0][0] == casa["id"]


async def test_patch_delete_and_validation():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        rule = await _rule(alice, casa["id"])
        path = f"/api/money/recurring/{rule['id']}"
        ok = await alice.patch(path, json={"amount": "12", "note": "Gym Pro", "vendor": "FitCo",
                                           "ends_on": _days_ago(-90)}, headers=O)
        assert ok.status_code == 200 and (ok.json()["amount"], ok.json()["note"], ok.json()["vendor"]) == (
            "12.00", "Gym Pro", "FitCo")
        cleared = await alice.patch(path, json={"ends_on": None, "vendor": ""}, headers=O)
        assert (cleared.json()["ends_on"], cleared.json()["vendor"]) == (None, None)
        for body in ({}, {"amount": None}, {"amount": "0"}, {"ends_on": "tomorrow"}, {"cadence": "daily"},
                     {"ends_on": _days_ago(100)}):
            assert (await alice.patch(path, json=body, headers=O)).status_code == 422, body
        for body in ({"cadence": "daily"}, {"amount": "1"}, {"amount": "1", "cadence": "weekly",
                                                             "project_id": casa["id"], "anchor_day": "soon"}):
            r = await alice.post("/api/money/recurring", json={"project_id": casa["id"], **body}, headers=O)
            assert r.status_code == 422, body
        assert (await alice.delete(path, headers=O)).status_code == 204
        assert (await alice.get("/api/money/recurring")).json() == []
        assert (await alice.delete(path, headers=O)).status_code == 404


async def test_deleting_a_project_deletes_its_rules():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        rule = await _rule(alice, casa["id"])
        assert (await alice.delete(f"/api/projects/{casa['id']}", headers=O)).status_code in (200, 204)
        assert (await alice.get("/api/money/recurring")).json() == []
        assert _sql("SELECT deleted_at IS NOT NULL FROM money_recurring WHERE id = ?", rule["id"])[0][0] == 1


async def test_every_recurring_write_needs_the_origin_header():
    evil = {"Origin": "http://evil.example"}
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        rule = await _rule(alice, casa["id"])
        path = f"/api/money/recurring/{rule['id']}"
        post = {"amount": "1", "project_id": casa["id"], "cadence": "weekly"}
        assert (await alice.post("/api/money/recurring", json=post, headers=evil)).status_code == 403
        assert (await alice.patch(path, json={"amount": "1"}, headers=evil)).status_code == 403
        assert (await alice.delete(path, headers=evil)).status_code == 403
    from fastapi.testclient import TestClient
    from roost.gateway.app import create_app
    anon = TestClient(create_app())
    assert anon.get("/api/money/recurring").status_code == 401 and anon.get("/api/money/upcoming").status_code == 401
    assert anon.post("/api/money/recurring", json=post, headers=O).status_code == 401
