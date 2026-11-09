"""Edit, delete, restore and bulk-move expenses over HTTP (Task 8)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from money_http import O, two_users

from roost.config import load_config
from roost.db.connection import get_db_path
from roost.money.months import today_madrid
from roost.money.service import ARCHIVED_TEXT, EXPENSE_GONE_PROJECT_TEXT


def _sql(query: str, *params) -> list[tuple]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        rows = con.execute(query, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


async def _project(client, name: str, **body) -> dict:
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def _expense(client, amount="12", **body) -> dict:
    r = await client.post("/api/money/expenses", json={"amount": amount, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


async def test_patch_changes_amount_note_vendor_day_project():
    async with two_users() as (alice, _, _):
        trip, food = await _project(alice, "Trip"), await _project(alice, "Food")
        lunch = await _expense(alice, "12", project_id=trip["id"], note="lunch", vendor="Old")
        r = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={
            "amount": "13,50", "note": "dinner", "vendor": "Mercadona", "spent_at": "2026-01-05",
            "project_id": food["id"]}, headers=O)
        assert r.status_code == 200, r.text
        row = r.json()
        assert (row["amount"], row["description"], row["vendor"], row["spent_at"], row["project_id"]) == (
            "13.50", "dinner", "Mercadona", "2026-01-05", food["id"])
        cleared = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"vendor": "", "note": None}, headers=O)
        assert (cleared.json()["vendor"], cleared.json()["description"], cleared.json()["amount"]) == (None, None, "13.50")


async def test_patch_reads_day_words_and_refuses_a_future_day():
    async with two_users() as (alice, _, _):
        lunch = await _expense(alice)
        yesterday = (date.fromisoformat(today_madrid()) - timedelta(days=1)).isoformat()
        ok = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"spent_at": "yesterday"}, headers=O)
        assert ok.json()["spent_at"] == yesterday
        for body in ({"spent_at": "tomorrow"}, {"spent_at": "whenever"}, {"amount": "0"}, {"amount": "12.345"},
                     {"amount": True}, {}, {"amount": None}, {"spent_at": None}, {"project_id": None},
                     {"colour": "red"}, {"note": "n" * 201}):
            r = await alice.patch(f"/api/money/expenses/{lunch['id']}", json=body, headers=O)
            assert r.status_code == 422, (body, r.text)
        listed = await alice.get("/api/money/expenses", params={"month": yesterday[:7]})   # the 1st: last month
        assert listed.json()[0]["spent_at"] == yesterday


async def test_patch_into_an_archived_or_foreign_project_is_refused():
    async with two_users() as (alice, bob, _):
        lunch = await _expense(alice)
        old = await _project(alice, "Old")
        await alice.patch(f"/api/projects/{old['id']}", json={"status": "archived"}, headers=O)
        shed = await _project(bob, "Shed")
        archived = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"project_id": old["id"]}, headers=O)
        foreign = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"project_id": shed["id"]}, headers=O)
        unknown = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"project_id": "nope"}, headers=O)
    assert (archived.status_code, archived.json()["detail"]) == (422, ARCHIVED_TEXT.format(name="Old"))
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "No such project.")
    assert unknown.status_code == 422
    assert _sql("SELECT project_id FROM money_expenses WHERE id = ?", lunch["id"])[0][0] == lunch["project_id"]


async def test_patch_cannot_move_a_task_expense_out_of_its_project():
    async with two_users() as (alice, _, _):
        trip, food = await _project(alice, "Trip"), await _project(alice, "Food")
        task = (await alice.post("/api/tasks", json={"title": "Book", "project_id": trip["id"]}, headers=O)).json()
        spent = await _expense(alice, task_id=task["id"])
        assert spent["project_id"] == trip["id"]
        out = await alice.patch(f"/api/money/expenses/{spent['id']}", json={"project_id": food["id"]}, headers=O)
        moved = await alice.post("/api/money/expenses/move", json={"expense_ids": [spent["id"]],
                                                                    "project_id": food["id"]}, headers=O)
        same = await alice.patch(f"/api/money/expenses/{spent['id']}", json={"project_id": trip["id"], "amount": "5"},
                                 headers=O)
    assert (out.status_code, out.json()["detail"]) == (422, "That task is in Trip.")
    assert moved.status_code == 422
    assert same.status_code == 200 and same.json()["amount"] == "5.00"


async def test_another_users_expense_is_404_for_patch_delete_restore():
    async with two_users() as (alice, bob, _):
        lunch = await _expense(alice)
        path = f"/api/money/expenses/{lunch['id']}"
        assert (await bob.patch(path, json={"amount": "1"}, headers=O)).status_code == 404
        assert (await bob.delete(path, headers=O)).status_code == 404
        assert (await alice.delete(path, headers=O)).status_code == 204
        assert (await bob.post(f"{path}/restore", headers=O)).status_code == 404
        assert (await alice.patch("/api/money/expenses/none", json={"amount": "1"}, headers=O)).status_code == 404
        assert (await alice.post("/api/money/expenses/none/restore", headers=O)).status_code == 404
        still_gone = _sql("SELECT deleted_at FROM money_expenses WHERE id = ?", lunch["id"])[0][0]
        assert still_gone is not None
        assert (await alice.patch(path, json={"amount": "1"}, headers=O)).status_code == 404     # a deleted one: gone


async def test_delete_then_restore():
    async with two_users() as (alice, _, _):
        lunch = await _expense(alice, note="lunch")
        path = f"/api/money/expenses/{lunch['id']}"
        assert (await alice.delete(path, headers=O)).status_code == 204
        assert (await alice.delete(path, headers=O)).status_code == 404
        assert (await alice.get("/api/money/expenses")).json() == []
        back = await alice.post(f"{path}/restore", headers=O)
        assert back.status_code == 200 and back.json()["id"] == lunch["id"]
        assert [e["id"] for e in (await alice.get("/api/money/expenses")).json()] == [lunch["id"]]
        assert (await alice.post(f"{path}/restore", headers=O)).status_code == 404       # not deleted now


async def test_restore_into_a_deleted_project_is_refused():
    async with two_users() as (alice, _, _):
        trip = await _project(alice, "Trip")
        lunch = await _expense(alice, project_id=trip["id"])
        await alice.delete(f"/api/money/expenses/{lunch['id']}", headers=O)
        _sql("UPDATE money_projects SET deleted_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", trip["id"])
        r = await alice.post(f"/api/money/expenses/{lunch['id']}/restore", headers=O)
    assert (r.status_code, r.json()["detail"]) == (422, EXPENSE_GONE_PROJECT_TEXT)
    assert _sql("SELECT deleted_at IS NOT NULL FROM money_expenses WHERE id = ?", lunch["id"])[0][0] == 1


async def test_bulk_move_moves_all_and_reports_where_from():
    async with two_users() as (alice, _, _):
        trip, food = await _project(alice, "Trip"), await _project(alice, "Food")
        a = await _expense(alice, project_id=trip["id"])
        b = await _expense(alice)                                  # General
        r = await alice.post("/api/money/expenses/move", json={"expense_ids": [a["id"], b["id"]],
                                                               "project_id": food["id"]}, headers=O)
        assert r.status_code == 200, r.text
        assert r.json() == {"moved": [{"id": a["id"], "from_project_id": trip["id"]},
                                      {"id": b["id"], "from_project_id": b["project_id"]}]}
        assert {e["project_id"] for e in (await alice.get("/api/money/expenses")).json()} == {food["id"]}


async def test_a_foreign_id_refuses_the_whole_move():
    async with two_users() as (alice, bob, _):
        trip, food = await _project(alice, "Trip"), await _project(alice, "Food")
        mine = await _expense(alice, project_id=trip["id"])
        theirs = await _expense(bob)
        deleted = await _expense(alice, project_id=trip["id"])
        await alice.delete(f"/api/money/expenses/{deleted['id']}", headers=O)
        for ids in ([mine["id"], theirs["id"]], [mine["id"], "unknown"], [mine["id"], deleted["id"]]):
            r = await alice.post("/api/money/expenses/move", json={"expense_ids": ids, "project_id": food["id"]},
                                 headers=O)
            assert r.status_code == 404, (ids, r.text)
        assert _sql("SELECT project_id FROM money_expenses WHERE id = ?", mine["id"])[0][0] == trip["id"]
        assert _sql("SELECT project_id FROM money_expenses WHERE id = ?", theirs["id"])[0][0] == theirs["project_id"]
        bobs = await bob.post("/api/money/expenses/move", json={"expense_ids": [mine["id"]],
                                                                 "project_id": food["id"]}, headers=O)
        assert bobs.status_code == 404


async def test_bulk_move_into_a_foreign_or_archived_project_is_refused():
    async with two_users() as (alice, bob, _):
        mine = await _expense(alice)
        shed = await _project(bob, "Shed")
        old = await _project(alice, "Old")
        await alice.patch(f"/api/projects/{old['id']}", json={"status": "archived"}, headers=O)
        for project_id in (shed["id"], old["id"], "nope"):
            r = await alice.post("/api/money/expenses/move", json={"expense_ids": [mine["id"]],
                                                                    "project_id": project_id}, headers=O)
            assert r.status_code == 422, r.text
        assert _sql("SELECT project_id FROM money_expenses WHERE id = ?", mine["id"])[0][0] == mine["project_id"]


async def test_bulk_move_limits_and_duplicates_are_422():
    async with two_users() as (alice, _, _):
        food = await _project(alice, "Food")
        mine = await _expense(alice)
        for ids in ([], [mine["id"], mine["id"]], [f"id{n}" for n in range(101)], [""]):
            r = await alice.post("/api/money/expenses/move", json={"expense_ids": ids, "project_id": food["id"]},
                                 headers=O)
            assert r.status_code == 422, (len(ids), r.text)
        extra = await alice.post("/api/money/expenses/move", json={"expense_ids": [mine["id"]],
                                                                    "project_id": food["id"], "x": 1}, headers=O)
        assert extra.status_code == 422


async def test_every_write_needs_the_origin_header():
    evil = {"Origin": "http://evil.example"}
    async with two_users() as (alice, _, _):
        lunch = await _expense(alice)
        path = f"/api/money/expenses/{lunch['id']}"
        assert (await alice.patch(path, json={"amount": "1"}, headers=evil)).status_code == 403
        assert (await alice.delete(path, headers=evil)).status_code == 403
        assert (await alice.post(f"{path}/restore", headers=evil)).status_code == 403
        assert (await alice.post("/api/money/expenses/move", json={"expense_ids": [lunch["id"]],
                                                                    "project_id": "x"}, headers=evil)).status_code == 403
    from fastapi.testclient import TestClient
    from roost.gateway.app import create_app
    anon = TestClient(create_app())
    assert anon.patch(path, json={"amount": "1"}, headers=O).status_code == 401
    assert anon.delete(path, headers=O).status_code == 401
    assert anon.post("/api/money/expenses/move", json={"expense_ids": ["a"], "project_id": "b"}, headers=O).status_code == 401


async def test_amount_stays_decimal_and_sealed():
    async with two_users() as (alice, _, _):
        lunch = await _expense(alice, "0.10", note="lunch", vendor="Mercadona")
        r = await alice.patch(f"/api/money/expenses/{lunch['id']}", json={"amount": "0.20", "note": "secret",
                                                                          "vendor": "Corner shop"}, headers=O)
        assert r.json()["amount"] == "0.20"
    amount, note, vendor = _sql("SELECT amount, description, vendor FROM money_expenses WHERE id = ?", lunch["id"])[0]
    for sealed in (amount, note, vendor):
        assert sealed.startswith("enc:v2:") and "secret" not in sealed and "0.20" not in sealed
