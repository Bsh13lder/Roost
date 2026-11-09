"""The task drawer's money everywhere (owner request 2026-10-26): a budget on any task, a project or
none (General's currency), a budget on each step, and planned / spent / left per task and per step,
all reckoned by the server. Another user's task or step is a 404 and nothing is written."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from roost.config import load_config
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _second_user(app) -> TestClient:
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(app)
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    return bob


def _expense(c: TestClient, **fields) -> dict:
    created = c.post("/api/money/expenses", json={"amount": "10", **fields}, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


def _task(c: TestClient, **fields) -> dict:
    created = c.post("/api/tasks", json={"title": "Fix the sink", **fields}, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


def _step(c: TestClient, task_id: str, title: str = "Buy a washer") -> dict:
    return c.post(f"/api/tasks/{task_id}/steps", json={"title": title}, headers=O).json()["steps"][-1]


def test_a_task_with_no_project_gets_a_budget_in_generals_currency():
    c = _client()
    task = _task(c)
    sliced = c.patch(f"/api/tasks/{task['id']}", json={"allocated_budget": "40"}, headers=O)
    assert (sliced.status_code, sliced.json()["allocated_budget"]) == (200, "40.00")
    _expense(c, amount="12,50", task_id=task["id"], note="washers")
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert (money["planned"], money["spent"], money["left"], money["currency"]) == ("40.00", "12.50", "27.50", "EUR")
    assert (money["used_percent"], money["tone"]) == (31, "ok")


def test_a_task_with_no_project_and_no_budget_still_shows_what_was_spent():
    c = _client()
    task = _task(c)
    _expense(c, amount="7", task_id=task["id"])
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert (money["planned"], money["spent"], money["left"], money["currency"]) == (None, "7.00", None, "EUR")


def test_a_budget_on_a_step_with_its_planned_spent_and_left():
    c = _client()
    task = _task(c, allocated_budget="100")
    step = _step(c, task["id"])
    other = _step(c, task["id"], "Call the plumber")
    set_ = c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={"budget": "20"}, headers=O)
    assert set_.status_code == 200, set_.text
    _expense(c, amount="12,50", task_id=task["id"], step_id=step["id"])
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert money["steps_money"][step["id"]] == {"planned": "20.00", "spent": "12.50", "left": "7.50",
                                               "used_percent": 62, "tone": "ok"}
    assert money["steps_money"][other["id"]] == {"planned": None, "spent": "0.00", "left": None,
                                                "used_percent": None, "tone": None}
    cleared = c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={"budget": None}, headers=O)
    assert cleared.status_code == 200
    again = c.get(f"/api/tasks/{task['id']}").json()["money"]["steps_money"][step["id"]]
    assert (again["planned"], again["spent"]) == (None, "12.50")


def test_a_step_budget_follows_the_amount_rules_and_keeps_its_title_and_tick():
    c = _client()
    task = _task(c)
    step = _step(c, task["id"])
    for bad in ("0", "-3", "1.005", "lots"):
        refused = c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={"budget": bad}, headers=O)
        assert refused.status_code == 422, bad
    both = c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={"budget": "5", "done": True}, headers=O)
    assert both.status_code == 200
    assert [(s["title"], s["done"]) for s in both.json()["steps"]] == [("Buy a washer", True)]


def test_a_step_budget_in_another_currency_reads_as_none_after_a_move():
    c = _client()
    dollars = c.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O).json()
    task = _task(c)
    step = _step(c, task["id"])
    c.patch(f"/api/tasks/{task['id']}/steps/{step['id']}", json={"budget": "20"}, headers=O)
    c.patch(f"/api/tasks/{task['id']}", json={"project_id": dollars["id"]}, headers=O)
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert (money["currency"], money["steps_money"][step["id"]]["planned"]) == ("USD", None)


def test_a_slice_follows_the_currency_into_and_out_of_a_project():
    c = _client()
    euros = c.post("/api/projects", json={"name": "House", "currency": "EUR"}, headers=O).json()
    dollars = c.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O).json()
    task = _task(c, allocated_budget="30")
    joined = c.patch(f"/api/tasks/{task['id']}", json={"project_id": euros["id"]}, headers=O).json()
    left = c.patch(f"/api/tasks/{task['id']}", json={"project_id": None}, headers=O).json()
    moved = c.patch(f"/api/tasks/{task['id']}", json={"project_id": dollars["id"]}, headers=O).json()
    assert (joined["allocated_budget"], left["allocated_budget"], moved["allocated_budget"]) == ("30.00", "30.00", None)
    assert moved["notice"] == "Its budget slice was cleared because Trip uses USD."


def test_an_expense_on_a_step_is_deleted_and_leaves_the_sums():
    c = _client()
    task = _task(c)
    step = _step(c, task["id"])
    expense = _expense(c, amount="9", task_id=task["id"], step_id=step["id"])
    assert c.delete(f"/api/money/expenses/{expense['id']}", headers=O).status_code == 204
    detail = c.get(f"/api/tasks/{task['id']}").json()
    assert (detail["money"]["spent"], detail["money"]["steps_money"][step["id"]]["spent"]) == ("0.00", "0.00")
    assert detail["expenses"] == []


def test_another_users_step_budget_is_a_404_and_nothing_changes():
    alice = _client()
    bob = _second_user(alice.app)
    task = _task(alice)
    step = _step(alice, task["id"])
    for client_, step_id in ((bob, step["id"]), (alice, "s-nope")):
        refused = client_.patch(f"/api/tasks/{task['id']}/steps/{step_id}", json={"budget": "5"}, headers=O)
        assert refused.status_code == 404
    assert bob.get(f"/api/tasks/{task['id']}").status_code == 404
    money = alice.get(f"/api/tasks/{task['id']}").json()["money"]
    assert money["steps_money"][step["id"]]["planned"] is None
