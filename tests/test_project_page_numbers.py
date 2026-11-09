"""The project page's extra numbers (G13): overdue, steps, planned, counts and the repeating rules."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from money_http import O, two_users

from roost.money.months import today_madrid
from roost.projects.numbers import progress
from roost.tasks.models import Step, Task

TODAY = date(2026, 10, 21)
_AT = "2026-10-01T09:00:00+00:00"


def _task(status="todo", *, due: str | None = None, budget: str | None = None, steps=()) -> Task:
    return Task(
        id=f"t-{status}-{due}-{budget}", user_id="u1", title="x", description=None, category=None, priority="medium",
        status=status, owner="user", due_date=due, reminder_at=None, pre_reminders=(), recurring=None,
        recur_until=None, tags=(), steps=tuple(steps), created_at=_AT, updated_at=_AT, completed_at=None,
        created_by_bot=None, tainted=False, project_id="p", allocated_budget=None if budget is None else Decimal(budget),
    )


def _step(done: bool) -> Step:
    return Step(id=f"s-{done}", title="s", done=done)


def test_progress_counts_overdue_and_steps():
    tasks = (
        _task(due="2026-10-20"), _task("in_progress", due="2026-10-01T09:00:00"),   # overdue
        _task(due="2026-10-21"), _task(),                                            # today / no date: not overdue
        _task("done", due="2026-09-01"), _task("cancelled", due="2026-09-01"),       # closed: not overdue
        _task(steps=(_step(True), _step(False), _step(True))), _task("done", steps=(_step(True),)),
    )
    result = progress(tasks, today=TODAY)
    assert (result.done, result.total, result.overdue) == (2, 7, 2)
    assert (result.steps_done, result.steps_total) == (3, 4)


def test_planned_total_is_in_the_project_currency_and_leaves_out_cancelled():
    tasks = (_task(budget="100.50"), _task("in_progress", budget="20"), _task("done", budget="999"),
             _task("cancelled", budget="500"), _task())
    assert progress(tasks, today=TODAY).planned_total == Decimal("120.50")
    assert progress((), today=TODAY).planned_total == Decimal("0.00")


async def _project(client, name="Casa", **body) -> dict:
    r = await client.post("/api/projects", json={"name": name, **body}, headers=O)
    assert r.status_code == 201, r.text
    return r.json()


def _day(offset: int) -> str:
    return (date.fromisoformat(today_madrid()) + timedelta(days=offset)).isoformat()


async def test_detail_counts():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        link = {"project_id": casa["id"]}
        await alice.post("/api/tasks", json={"title": "Late", "due_date": _day(-2), "allocated_budget": "40", **link}, headers=O)
        done = (await alice.post("/api/tasks", json={"title": "Done", **link}, headers=O)).json()
        await alice.post(f"/api/tasks/{done['id']}/complete", headers=O)
        await alice.post("/api/tasks", json={"title": "Elsewhere"}, headers=O)
        await alice.post("/api/money/expenses", json={"amount": "5", "project_id": casa["id"]}, headers=O)
        page = (await alice.get(f"/api/projects/{casa['id']}")).json()
        assert page["counts"] == {"tasks_open": 1, "expenses": 1, "notes": 0, "documents": 0}
        assert page["progress"]["overdue"] == 1 and page["progress"]["planned_total"] == "40.00"
        assert (page["progress"]["steps_done"], page["progress"]["steps_total"]) == (0, 0)


async def test_detail_lists_the_projects_repeating_rules():
    async with two_users() as (alice, _, _):
        casa = await _project(alice)
        other = await _project(alice, "Shed")
        mine = await alice.post("/api/money/recurring", json={
            "amount": "42", "project_id": casa["id"], "cadence": "monthly", "anchor_day": _day(3), "note": "Insurance"},
            headers=O)
        assert mine.status_code == 201, mine.text
        await alice.post("/api/money/recurring", json={
            "amount": "9", "project_id": other["id"], "cadence": "weekly", "anchor_day": _day(3)}, headers=O)
        page = (await alice.get(f"/api/projects/{casa['id']}")).json()
        assert [(r["id"], r["note"], r["cadence"]) for r in page["repeating"]] == [(mine.json()["id"], "Insurance", "monthly")]


async def test_detail_is_per_user():
    async with two_users() as (alice, bob, _):
        casa = await _project(alice)
        await alice.post("/api/money/recurring", json={
            "amount": "42", "project_id": casa["id"], "cadence": "monthly", "anchor_day": _day(3)}, headers=O)
        assert (await bob.get(f"/api/projects/{casa['id']}")).status_code == 404
        bobs = await _project(bob, "Mine")
        page = (await bob.get(f"/api/projects/{bobs['id']}")).json()
        assert page["repeating"] == [] and page["counts"]["tasks_open"] == 0
