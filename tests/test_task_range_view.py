"""The task calendar's range (G11): ``GET /api/tasks?from=&to=``."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.constants import TASK_RANGE_MAX_DAYS
from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}


def day(offset: int) -> str:
    return (datetime.now(MADRID_TZ).date() + timedelta(days=offset)).isoformat()


def client(name: str = "alice") -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201
    return c


def add(c: TestClient, title: str, **fields) -> dict:
    created = c.post("/api/tasks", json={"title": title, **fields}, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


def titles(response) -> list[str]:
    assert response.status_code == 200, response.text
    return sorted(task["title"] for task in response.json())


def test_range_lists_due_in_range_and_overdue_on_today():
    c = client()
    add(c, "inside", due_date=day(2))
    add(c, "timed", due_date=f"{day(3)}T09:30")
    add(c, "outside", due_date=day(20))
    add(c, "late", due_date=day(-4))
    add(c, "no date")
    done = add(c, "finished", due_date=day(1))
    c.post(f"/api/tasks/{done['id']}/complete", headers=O)
    got = c.get(f"/api/tasks?from={day(0)}&to={day(6)}")
    assert titles(got) == ["finished", "inside", "late", "timed"]
    assert all("money" in task and "due_bucket" in task for task in got.json())
    # today outside the range: the late task is not added
    assert titles(c.get(f"/api/tasks?from={day(1)}&to={day(6)}")) == ["finished", "inside", "timed"]


def test_range_leaves_out_cancelled():
    c = client()
    task = add(c, "dropped", due_date=day(1))
    assert c.patch(f"/api/tasks/{task['id']}", json={"status": "cancelled"}, headers=O).status_code == 200
    add(c, "kept", due_date=day(1))
    assert titles(c.get(f"/api/tasks?from={day(0)}&to={day(3)}")) == ["kept"]


def test_range_span_is_bounded_and_needs_both_ends():
    c = client()
    assert c.get(f"/api/tasks?from={day(0)}&to={day(TASK_RANGE_MAX_DAYS - 1)}").status_code == 200
    assert c.get(f"/api/tasks?from={day(0)}&to={day(TASK_RANGE_MAX_DAYS)}").status_code == 422
    assert c.get(f"/api/tasks?from={day(3)}&to={day(0)}").status_code == 422
    assert c.get(f"/api/tasks?from={day(0)}").status_code == 422
    assert c.get(f"/api/tasks?to={day(0)}").status_code == 422
    assert c.get(f"/api/tasks?from={day(0)}&to={day(3)}&view=today").status_code == 422
    assert c.get("/api/tasks?from=2026-13-01&to=2026-13-02").status_code == 422
    assert c.get("/api/tasks?from=nope&to=nope").status_code == 422


async def test_range_is_per_user():
    from money_http import two_users
    async with two_users() as (alice, bob, _):
        for who, title in ((alice, "mine"), (bob, "theirs")):
            made = await who.post("/api/tasks", json={"title": title, "due_date": day(1)}, headers=O)
            assert made.status_code == 201
        got = await alice.get(f"/api/tasks?from={day(0)}&to={day(3)}")
        assert [task["title"] for task in got.json()] == ["mine"]


def test_range_adds_open_tasks_whose_reminder_fires_in_it():
    """Clean calendar (2026-10-26): a reminder that fires inside the range brings its task, even when the task is
    due later or has no due day; a done task's reminder never fires, so it does not."""
    c = client()

    def remind(task: dict, at: str, early: list[str]) -> None:
        patched = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": at, "pre_reminders": early}, headers=O)
        assert patched.status_code == 200, patched.text

    remind(add(c, "due later", due_date=day(20)), f"{day(2)}T09:00", [])
    remind(add(c, "no date, reminded"), f"{day(3)}T18:00", [])
    remind(add(c, "advance only", due_date=day(20)), f"{day(9)}T09:00", ["-5d"])
    closed = add(c, "done, reminded")
    remind(closed, f"{day(2)}T09:00", [])
    c.post(f"/api/tasks/{closed['id']}/complete", headers=O)
    add(c, "no reminder", due_date=day(20))
    assert titles(c.get(f"/api/tasks?from={day(1)}&to={day(6)}")) == ["advance only", "due later", "no date, reminded"]


def _task(reminder_at: str | None, pre: tuple[str, ...] = ()):
    from roost.tasks.models import Task
    return Task(id="t", user_id="u", title="x", description=None, category=None, priority="medium", status="todo",
                owner="user", due_date=None, reminder_at=reminder_at, pre_reminders=pre, recurring=None,
                recur_until=None, tags=(), steps=(), created_at="2026-10-01T00:00:00Z",
                updated_at="2026-10-01T00:00:00Z", completed_at=None, created_by_bot=None, tainted=False)


def test_reminder_days_are_the_madrid_days_of_every_fire():
    from datetime import date as d

    from roost.tasks.views import reminder_days
    # 22:30 UTC on the 23rd is 00:30 on the 24th in Madrid; 21:00 UTC on the 22nd is 23:00 Madrid;
    # -1h is 21:30 UTC on the 23rd, 23:30 Madrid; a stray entry is skipped
    task = _task("2026-10-23T22:30:00+00:00", ("2026-10-22T21:00:00+00:00", "-1h", "nonsense"))
    assert reminder_days(task) == frozenset({d(2026, 10, 24), d(2026, 10, 23), d(2026, 10, 22)})
    assert reminder_days(_task(None)) == frozenset()
    assert reminder_days(_task("not a time")) == frozenset()
