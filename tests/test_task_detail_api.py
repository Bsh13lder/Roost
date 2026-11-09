"""The task drawer's server side (redesign P3): one task with its money and expenses, the reminder
and the repeat set on their own, and an expense added for a task or one of its steps."""

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


def _project(c: TestClient, name: str = "Renovation", currency: str = "EUR") -> dict:
    return c.post("/api/projects", json={"name": name, "currency": currency}, headers=O).json()


def _expense(c: TestClient, **fields) -> dict:
    created = c.post("/api/money/expenses", json={"amount": "10", **fields}, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


def test_a_task_with_its_money_per_task_and_per_step_and_its_expenses():
    c = _client()
    project = _project(c)
    task = c.post("/api/tasks", json={"title": "Fix the sink", "project_id": project["id"],
                                      "allocated_budget": "50"}, headers=O).json()
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    on_step = _expense(c, amount="12,50", task_id=task["id"], step_id=step["id"], note="washers")
    on_task = _expense(c, amount="30", task_id=task["id"])
    assert (on_step["project_id"], on_step["step_id"], on_task["step_id"]) == (project["id"], step["id"], None)
    detail = c.get(f"/api/tasks/{task['id']}").json()
    assert detail["title"] == "Fix the sink"
    assert detail["money"] == {"planned": "50.00", "spent": "42.50", "left": "7.50", "currency": "EUR",
                               "used_percent": 85, "tone": "warn", "steps": {step["id"]: "12.50"}, "other_currencies": {},
                               "steps_other_currencies": {},
                               "steps_money": {step["id"]: {"planned": None, "spent": "12.50", "left": None,
                                                            "used_percent": None, "tone": None}}}
    assert sorted(e["amount"] for e in detail["expenses"]) == ["12.50", "30.00"]


def test_a_task_with_no_project_counts_its_money_in_general_and_lists_its_expenses():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Buy stamps"}, headers=O).json()
    _expense(c, task_id=task["id"])
    detail = c.get(f"/api/tasks/{task['id']}").json()
    assert (detail["money"]["currency"], detail["money"]["spent"], detail["money"]["planned"]) == ("EUR", "10.00", None)
    assert [e["project"] for e in detail["expenses"]] == ["General"]


def test_an_expense_names_a_real_task_and_one_of_its_steps():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Fix the sink"}, headers=O).json()
    for body, reason in (
        ({"task_id": "no-such-task"}, "No such task."),
        ({"task_id": task["id"], "step_id": "s-nope"}, "That task has no such step."),
        ({"step_id": "s-nope"}, "A step needs its task: name the task too."),
    ):
        refused = c.post("/api/money/expenses", json={"amount": "10", **body}, headers=O)
        assert (refused.status_code, refused.json()["detail"]) == (422, reason)


def test_the_reminder_and_the_repeat_are_set_and_cleared_on_their_own():
    c = _client()
    task = c.post("/api/tasks", json={"title": "Water the plants", "due_date": "2026-12-01"}, headers=O).json()
    reminded = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": "2026-11-30T20:00"}, headers=O).json()
    assert (reminded["due_date"], reminded["reminder_at"], reminded["pre_reminders"]) == (
        "2026-12-01", "2026-11-30T19:00:00+00:00", ["2026-11-30T18:30:00+00:00"])
    repeating = c.patch(f"/api/tasks/{task['id']}", json={"recurring": "0 9 * * 1"}, headers=O).json()
    assert repeating["recurring"] == "0 9 * * 1"
    cleared = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": None, "recurring": None}, headers=O).json()
    assert (cleared["reminder_at"], cleared["pre_reminders"], cleared["recurring"]) == (None, [], None)


def test_a_reminder_or_repeat_it_cannot_read_is_422():
    c = _client()
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    no_time = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": "next monday"}, headers=O)
    assert no_time.status_code == 422 and "could not read a time" in no_time.json()["detail"]
    bad_cron = c.patch(f"/api/tasks/{task['id']}", json={"recurring": "every day"}, headers=O)
    assert bad_cron.status_code == 422 and "is not a cron expression" in bad_cron.json()["detail"]


def test_another_users_task_is_404_and_their_task_cannot_take_an_expense():
    alice = _client()
    task = alice.post("/api/tasks", json={"title": "Mine"}, headers=O).json()
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O).status_code == 200
    assert bob.get(f"/api/tasks/{task['id']}").status_code == 404
    sneaky = bob.post("/api/money/expenses", json={"amount": "10", "task_id": task["id"]}, headers=O)
    assert (sneaky.status_code, sneaky.json()["detail"]) == (422, "No such task.")


def test_an_expense_for_a_task_goes_to_the_tasks_project_or_is_refused_elsewhere():
    c = _client()
    reno = _project(c)
    other = _project(c, "Garden")
    task = c.post("/api/tasks", json={"title": "Fix the sink", "project_id": reno["id"]}, headers=O).json()
    bare = c.post("/api/tasks", json={"title": "Buy stamps"}, headers=O).json()
    assert _expense(c, task_id=task["id"])["project_id"] == reno["id"]
    assert _expense(c, task_id=task["id"], project="renovation")["project_id"] == reno["id"]
    assert _expense(c, task_id=task["id"], project_id=reno["id"])["project_id"] == reno["id"]
    for body in ({"project": "General"}, {"project": "Garden"}, {"project_id": other["id"]}):
        refused = c.post("/api/money/expenses", json={"amount": "5", "task_id": task["id"], **body}, headers=O)
        assert (refused.status_code, refused.json()["detail"]) == (422, "That task is in Renovation.")
    refused = c.post("/api/money/expenses", json={"amount": "5", "task_id": bare["id"], "project": "Garden"}, headers=O)
    assert (refused.status_code, refused.json()["detail"]) == (422, "That task has no project.")
    assert _expense(c, task_id=bare["id"])["project"] == "General"


def test_spending_in_another_currency_shows_apart_on_the_task_and_its_step():
    c = _client()
    project = _project(c)
    task = c.post("/api/tasks", json={"title": "Fix the sink", "project_id": project["id"]}, headers=O).json()
    step = c.post(f"/api/tasks/{task['id']}/steps", json={"title": "Buy a washer"}, headers=O).json()["steps"][0]
    _expense(c, amount="30", task_id=task["id"])
    _expense(c, amount="4", currency="USD", task_id=task["id"], step_id=step["id"])
    _expense(c, amount="3", currency="USD", task_id=task["id"])
    voided = _expense(c, amount="9", currency="GBP", task_id=task["id"])
    assert c.put(f"/api/money/expenses/{voided['id']}/void", json={"void": True}, headers=O).status_code == 200
    money = c.get(f"/api/tasks/{task['id']}").json()["money"]
    assert money["spent"] == "30.00"
    assert money["other_currencies"] == {"USD": "7.00"}
    assert money["steps_other_currencies"] == {step["id"]: {"USD": "4.00"}}
