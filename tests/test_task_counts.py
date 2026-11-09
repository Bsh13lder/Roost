"""Counts for the Board's tabs (G1): each equals what its view shows."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from money_http import two_users
from roost.gateway.app import create_app
from roost.tasks.views import counts, pick
from test_task_views import TODAY, make
from test_task_views_api import O, add, day

KEYS = {"overdue", "today", "upcoming_14", "someday", "done_week", "open"}


def test_counts_match_the_views():
    tasks = [make("a", due="2026-10-19"), make("b", due="2026-10-20"), make("c", due="2026-10-20T10:00:00+02:00"),
             make("d"), make("e", due="2026-10-25"), make("f", status="done", completed="2026-10-19T10:00:00+00:00")]
    got = counts(tasks, TODAY)
    assert got.overdue == len(pick(tasks, "overdue", today=TODAY)) == 1
    assert got.today == len(pick(tasks, "today", today=TODAY)) == 2
    assert got.someday == len(pick(tasks, "someday", today=TODAY)) == 1


def test_upcoming_counts_fourteen_days_only():
    tasks = [make("tomorrow", due="2026-10-21"), make("edge", due="2026-11-03"), make("far", due="2026-11-04"),
             make("today", due="2026-10-20")]
    assert counts(tasks, TODAY).upcoming_14 == 2


def test_done_week_starts_monday_in_madrid():
    # Monday is 19 Oct 2026. 18 Oct 22:30 UTC is already Monday 00:30 in Madrid.
    tasks = [make("in", status="done", completed="2026-10-18T22:30:00+00:00"),
             make("also", status="done", completed="2026-10-20T08:00:00+00:00"),
             make("before", status="done", completed="2026-10-18T21:30:00+00:00"),
             make("failed", status="failed", completed="2026-10-20T08:00:00+00:00")]
    assert counts(tasks, TODAY).done_week == 2


async def test_counts_are_per_user():
    async with two_users() as (alice, bob, _):
        await alice.post("/api/tasks", json={"title": "late", "due_date": day(-1)}, headers=O)
        assert (await alice.get("/api/tasks/counts")).json()["overdue"] == 1
        assert (await bob.get("/api/tasks/counts")).json() == {k: 0 for k in KEYS}


def test_counts_route_is_not_read_as_a_task_id():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    add(c, "x", due_date=day(0))
    r = c.get("/api/tasks/counts")
    assert r.status_code == 200 and set(r.json()) == KEYS and r.json()["today"] == 1
