"""Task rows carry their money and a due bucket (G3): the server works them out, the web adds nothing up."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.money.expense_store import ExpenseStore
from tz_helpers import MADRID_TZ
from roost.tasks.models import Task
from roost.tasks.views import due_bucket

O = {"Origin": "http://127.0.0.1:18800"}
TODAY = date(2026, 10, 20)


def day(offset: int) -> str:
    return (datetime.now(MADRID_TZ).date() + timedelta(days=offset)).isoformat()


def client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def project(c: TestClient, name: str = "Reno", currency: str = "EUR") -> dict:
    return c.post("/api/projects", json={"name": name, "currency": currency}, headers=O).json()


def task(c: TestClient, title: str, **fields) -> dict:
    made = c.post("/api/tasks", json={"title": title, **fields}, headers=O)
    assert made.status_code == 201, made.text
    return made.json()


def spend(c: TestClient, task_id: str, amount: str, **fields) -> None:
    made = c.post("/api/money/expenses", json={"amount": amount, "task_id": task_id, **fields}, headers=O)
    assert made.status_code == 201, made.text


def row(c: TestClient, url: str, task_id: str) -> dict:
    return next(r for r in c.get(url).json() if r["id"] == task_id)


def make(due: str | None, status: str = "todo") -> Task:
    return Task(id="t", user_id="u", title="t", description=None, category=None, priority="medium", status=status,  # type: ignore[arg-type]
                owner="user", due_date=due, reminder_at=None, pre_reminders=(), recurring=None, recur_until=None,
                tags=(), steps=(), created_at="2026-10-01T08:00:00+00:00", updated_at="x", completed_at=None,
                created_by_bot=None, tainted=False)


def test_view_rows_carry_money():
    c = client()
    p = project(c)
    t = task(c, "Paint", project_id=p["id"], allocated_budget="400", due_date=day(0))
    spend(c, t["id"], "320")
    expected = {"planned": "400.00", "spent": "320.00", "left": "80.00", "currency": "EUR", "over": False}
    for url in ("/api/tasks", "/api/tasks?view=today", "/api/tasks?q=paint", f"/api/tasks?project_id={p['id']}"):
        assert row(c, url, t["id"])["money"] == expected, url


def test_money_is_null_without_a_project_or_slice():
    c = client()
    p = project(c)
    bare = task(c, "Bare")
    no_slice = task(c, "No slice", project_id=p["id"])
    assert row(c, "/api/tasks", bare["id"])["money"] is None
    assert row(c, "/api/tasks", no_slice["id"])["money"] is None


def test_over_is_true_when_spent_passes_planned():
    c = client()
    p = project(c)
    t = task(c, "Tiles", project_id=p["id"], allocated_budget="100")
    spend(c, t["id"], "130")
    money = row(c, "/api/tasks", t["id"])["money"]
    assert (money["left"], money["over"]) == ("-30.00", True)


def test_money_is_in_the_projects_currency_and_never_mixed():
    c = client()
    p = project(c, currency="EUR")
    t = task(c, "Mixed", project_id=p["id"], allocated_budget="100")
    spend(c, t["id"], "40")
    spend(c, t["id"], "500", currency="USD")
    money = row(c, "/api/tasks", t["id"])["money"]
    assert (money["currency"], money["spent"], money["left"]) == ("EUR", "40.00", "60.00")


def test_rows_carry_due_bucket_in_madrid():
    c = client()
    ids = {name: task(c, name, due_date=when)["id"] for name, when in (
        ("late", day(-1)), ("now", day(0)), ("next", day(1)), ("soon", day(4)), ("far", day(9)), ("none", None)) if True}
    got = {r["title"]: r["due_bucket"] for r in c.get("/api/tasks").json()}
    assert got == {"late": "overdue", "now": "today", "next": "tomorrow", "soon": "week", "far": "later", "none": "none"}
    assert set(ids) == set(got)


def test_due_bucket_edges_and_closed_tasks():
    assert due_bucket(make("2026-10-26"), TODAY) == "week"      # 6 days
    assert due_bucket(make("2026-10-27"), TODAY) == "later"     # 7 days
    assert due_bucket(make("2026-10-19T23:00:00+02:00"), TODAY) == "overdue"
    assert due_bucket(make("2026-10-19", status="done"), TODAY) == "overdue"
    assert due_bucket(make("garbage"), TODAY) == "none"


def test_rows_money_reads_expenses_once():
    c = client()
    p = project(c)
    for n in range(3):
        task(c, f"T{n}", project_id=p["id"], allocated_budget="10")
    real = ExpenseStore.for_tasks
    calls = []

    async def counting(self, user_id, task_ids):
        calls.append(tuple(task_ids))
        return await real(self, user_id, task_ids)

    with patch.object(ExpenseStore, "for_tasks", counting):
        assert len(c.get("/api/tasks").json()) == 3
    assert len(calls) == 1 and len(calls[0]) == 3
