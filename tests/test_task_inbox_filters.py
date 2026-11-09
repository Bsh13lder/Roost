"""The Board's Tasks rail and Inbox: ``project_id=none`` (tasks in no project), counts per project or none,
the ``open`` count, and ``include_finished`` on the today / upcoming / someday views."""

from __future__ import annotations

from fastapi.testclient import TestClient

from money_http import two_users
from roost.constants import TASK_NO_PROJECT
from test_task_views import TODAY, make
from test_task_views_api import O, add, client, day


def titles(c: TestClient, query: str) -> list[str]:
    got = c.get(f"/api/tasks?{query}")
    assert got.status_code == 200, got.text
    return sorted(t["title"] for t in got.json())


def project(c: TestClient, name: str = "Reno") -> str:
    made = c.post("/api/projects", json={"name": name}, headers=O)
    assert made.status_code == 201, made.text
    return made.json()["id"]


def done(c: TestClient, task: dict) -> None:
    assert c.post(f"/api/tasks/{task['id']}/complete", headers=O).status_code == 200


def rig() -> tuple[TestClient, str]:
    """Loose and filed tasks: today, upcoming, someday, overdue, plus one done today in each place."""
    c = client()
    reno = project(c)
    for where, extra in (("loose", {}), ("filed", {"project_id": reno})):
        add(c, f"{where} today", due_date=day(0), **extra)
        add(c, f"{where} later", due_date=day(3), **extra)
        add(c, f"{where} someday", **extra)
        add(c, f"{where} late", due_date=day(-2), **extra)
        done(c, add(c, f"{where} done today", due_date=day(0), **extra))
    return c, reno


def test_sentinel_lives_in_constants():
    assert TASK_NO_PROJECT == "none"


def test_project_none_lists_only_loose_tasks():
    c, reno = rig()
    assert titles(c, "project_id=none") == ["loose late", "loose later", "loose someday", "loose today"]
    assert titles(c, f"project_id={reno}") == ["filed late", "filed later", "filed someday", "filed today"]
    assert len(titles(c, "project_id=")) == 8 == len(titles(c, ""))


def test_project_none_with_views_and_status():
    c, _ = rig()
    assert titles(c, "project_id=none&view=today") == ["loose today"]
    assert titles(c, "project_id=none&view=overdue") == ["loose late"]
    assert titles(c, "project_id=none&view=upcoming") == ["loose later"]
    assert titles(c, "project_id=none&view=someday") == ["loose someday"]
    assert titles(c, "project_id=none&view=done") == ["loose done today"]
    assert len(titles(c, "project_id=none&view=board")) == 5
    assert titles(c, "project_id=none&status=done") == ["loose done today"]


def test_project_none_with_a_range():
    c, _ = rig()
    got = titles(c, f"project_id=none&from={day(0)}&to={day(4)}")
    assert got == ["loose done today", "loose late", "loose later", "loose today"]


def test_done_cap_applies_after_the_project_filter(monkeypatch):
    import roost.tasks.views as views
    monkeypatch.setattr(views, "TASK_DONE_VIEW_LIMIT", 2)
    c = client()
    reno = project(c)
    for title in ("loose one", "loose two"):
        done(c, add(c, title))
    for title in ("filed one", "filed two", "filed three"):
        done(c, add(c, title, project_id=reno))
    assert titles(c, "project_id=none&view=done") == ["loose one", "loose two"]


def test_include_finished_adds_done_tasks_in_the_view_window():
    c, reno = rig()
    assert titles(c, "view=today&project_id=none&include_finished=1") == ["loose done today", "loose today"]
    assert titles(c, f"view=today&project_id={reno}&include_finished=1") == ["filed done today", "filed today"]
    assert titles(c, "view=today&include_finished=0&project_id=none") == ["loose today"]
    done(c, add(c, "loose done later", due_date=day(5)))
    done(c, add(c, "loose done someday"))
    assert titles(c, "view=upcoming&project_id=none&include_finished=1") == ["loose done later", "loose later"]
    assert titles(c, "view=someday&project_id=none&include_finished=1") == ["loose done someday", "loose someday"]


def test_include_finished_leaves_failed_and_other_views_alone():
    c = client()
    failed = add(c, "failed today", due_date=day(0))
    assert c.post(f"/api/tasks/{failed['id']}/fail", headers=O).status_code == 200
    done(c, add(c, "done late", due_date=day(-3)))
    assert titles(c, "view=today&include_finished=1") == []
    assert titles(c, "view=overdue&include_finished=1") == []


def test_include_finished_in_the_pure_view():
    from roost.tasks.views import pick
    tasks = [make("open", due="2026-10-20"), make("closed", due="2026-10-20", status="done"),
             make("closed tomorrow", due="2026-10-21", status="done")]
    assert [t.title for t in pick(tasks, "today", today=TODAY)] == ["open"]
    assert {t.title for t in pick(tasks, "today", today=TODAY, finished=True)} == {"open", "closed"}


def test_counts_for_one_project_and_for_none():
    c, reno = rig()
    whole, loose, filed = (c.get(f"/api/tasks/counts{q}").json() for q in ("", "?project_id=none",
                                                                          f"?project_id={reno}"))
    assert whole["open"] == 8 and whole["overdue"] == 2 and whole["done_week"] == 2
    for got in (loose, filed):
        assert (got["open"], got["overdue"], got["today"], got["upcoming_14"], got["someday"], got["done_week"]) == (
            4, 1, 1, 1, 1, 1)
    assert c.get("/api/tasks/counts?project_id=").json() == whole


def test_open_count_skips_done_failed_and_cancelled():
    c = client()
    add(c, "todo")
    busy = add(c, "busy")
    c.patch(f"/api/tasks/{busy['id']}", json={"status": "in_progress"}, headers=O)
    gone = add(c, "gone")
    c.patch(f"/api/tasks/{gone['id']}", json={"status": "cancelled"}, headers=O)
    done(c, add(c, "done"))
    failed = add(c, "failed")
    c.post(f"/api/tasks/{failed['id']}/fail", headers=O)
    assert c.get("/api/tasks/counts").json()["open"] == 2


async def test_counts_for_another_users_project_is_404():
    async with two_users() as (alice, bob, _):
        reno = (await alice.post("/api/projects", json={"name": "Reno"}, headers=O)).json()["id"]
        await alice.post("/api/tasks", json={"title": "x", "project_id": reno}, headers=O)
        assert (await alice.get(f"/api/tasks/counts?project_id={reno}")).json()["open"] == 1
        assert (await bob.get(f"/api/tasks/counts?project_id={reno}")).status_code == 404
        assert (await bob.get("/api/tasks/counts?project_id=nope")).status_code == 404
        assert (await bob.get("/api/tasks/counts?project_id=none")).json()["open"] == 0


async def test_project_none_is_per_user():
    async with two_users() as (alice, bob, _):
        await alice.post("/api/tasks", json={"title": "Alice loose"}, headers=O)
        assert (await bob.get("/api/tasks?project_id=none")).json() == []
        assert [t["title"] for t in (await alice.get("/api/tasks?project_id=none")).json()] == ["Alice loose"]


def test_project_list_progress_has_open_and_overdue():
    c, reno = rig()
    row = next(p for p in c.get("/api/projects").json() if p["id"] == reno)
    got = row["progress"]
    assert (got["open"], got["overdue"], got["done"], got["total"]) == (4, 1, 1, 5)
