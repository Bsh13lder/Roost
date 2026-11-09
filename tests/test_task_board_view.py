"""The Kanban's `board` view and its sorts (G6)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from tz_helpers import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}


def client(name: str = "alice") -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": name, "password": "pw-123456"}, headers=O).status_code == 201
    return c


def add(c: TestClient, title: str, **fields) -> dict:
    made = c.post("/api/tasks", json={"title": title, **fields}, headers=O)
    assert made.status_code == 201, made.text
    return made.json()


def titles(c: TestClient, query: str) -> list[str]:
    got = c.get(f"/api/tasks?{query}")
    assert got.status_code == 200, got.text
    return [t["title"] for t in got.json()]


def test_board_view_has_open_and_this_weeks_done():
    c = client()
    add(c, "Open one")
    started = add(c, "Started")
    c.patch(f"/api/tasks/{started['id']}", json={"status": "in_progress"}, headers=O)
    fresh = add(c, "Fresh done")
    c.post(f"/api/tasks/{fresh['id']}/complete", headers=O)
    assert set(titles(c, "view=board")) == {"Open one", "Started", "Fresh done"}


def test_board_view_drops_old_done_tasks():
    from datetime import date
    from test_task_views import make
    from roost.constants import BOARD_DONE_DAYS
    today = date(2026, 10, 20)
    recent = (datetime(2026, 10, 20, 9, tzinfo=MADRID_TZ) - timedelta(days=BOARD_DONE_DAYS - 1)).isoformat()
    old = (datetime(2026, 10, 20, 9, tzinfo=MADRID_TZ) - timedelta(days=BOARD_DONE_DAYS + 2)).isoformat()
    tasks = [make("open"), make("busy", status="in_progress"), make("recent", status="done", completed=recent),
             make("old", status="done", completed=old), make("failed", status="failed")]
    from roost.tasks.views import pick
    assert {t.title for t in pick(tasks, "board", today=today)} == {"open", "busy", "recent"}


def test_sort_newest_oldest_and_title():
    c = client()
    for name in ("Éclair", "apple", "Banana"):
        add(c, name)
    assert titles(c, "sort=created") == ["Banana", "apple", "Éclair"]
    assert titles(c, "sort=created_asc") == ["Éclair", "apple", "Banana"]
    assert titles(c, "sort=title") == ["apple", "Banana", "Éclair"]


def test_sort_money_left_puts_most_left_first_and_no_slice_last():
    c = client()
    project = c.post("/api/projects", json={"name": "Reno", "budget": "1000"}, headers=O).json()
    add(c, "Small", project_id=project["id"], allocated_budget="50")
    add(c, "Big", project_id=project["id"], allocated_budget="400")
    add(c, "No slice")
    assert titles(c, "sort=money_left") == ["Big", "Small", "No slice"]


async def test_board_view_is_per_user():
    from money_http import two_users
    async with two_users() as (alice, bob, _):
        made = await alice.post("/api/tasks", json={"title": "Alice only"}, headers=O)
        assert made.status_code == 201
        assert (await bob.get("/api/tasks?view=board")).json() == []
        assert [t["title"] for t in (await alice.get("/api/tasks?view=board")).json()] == ["Alice only"]
