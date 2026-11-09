"""Tasks over HTTP (the Board's data, M1 D8) and the tasks_changed frame."""

from __future__ import annotations

import sqlite3

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def _frames() -> list[str]:
    con = sqlite3.connect(get_db_path(load_config()))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_create_list_update_complete_delete():
    c = _client()
    created = c.post("/api/tasks", json={"title": "Call the dentist", "due_date": "2026-12-01T09:00"}, headers=O)
    assert created.status_code == 201
    task = created.json()
    assert (task["due_date"], task["pre_reminders"], task["tainted"]) == ("2026-12-01T09:00:00+01:00", ["2026-12-01T07:30:00+00:00"], False)
    assert [t["title"] for t in c.get("/api/tasks").json()] == ["Call the dentist"]
    patched = c.patch(f"/api/tasks/{task['id']}", json={"title": "Call the dentist again", "due_date": None}, headers=O).json()
    assert (patched["title"], patched["due_date"], patched["reminder_at"]) == ("Call the dentist again", None, None)
    assert c.post(f"/api/tasks/{task['id']}/complete", headers=O).json()["status"] == "done"
    assert c.get("/api/tasks").json() == []
    assert c.delete(f"/api/tasks/{task['id']}", headers=O).status_code == 204
    assert c.get("/api/tasks?status=all").json() == []
    assert _frames()[-4:] == ["tasks_changed"] * 4


def test_an_unreadable_due_is_422_with_a_plain_reason():
    r = _client().post("/api/tasks", json={"title": "x", "due_date": "someday-ish"}, headers=O)
    assert r.status_code == 422 and "could not read a date" in r.json()["detail"]


def test_a_due_past_the_end_of_the_calendar_is_422_not_a_500():
    c = _client()
    for text in ("in 99999999 days", "9999-12-31T23:59:59+00:00"):
        created = c.post("/api/tasks", json={"title": "x", "due_date": text}, headers=O)
        assert created.status_code == 422, text
        assert created.json()["detail"] == f"I could not read a date in “{text}”. Try “tomorrow at 9” or 2026-10-20."
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    patched = c.patch(f"/api/tasks/{task['id']}", json={"due_date": "in 99999999 days"}, headers=O)
    assert patched.status_code == 422 and "could not read a date" in patched.json()["detail"]
    assert c.get("/api/tasks").json()[0]["due_date"] is None


def test_patching_priority_or_status_to_null_is_422_not_a_crash():
    """Fix round 1 (Important #2): a NOT NULL column patched to ``null``
    must be a 422 refusal, not an uncaught sqlite3.IntegrityError 500."""
    c = _client()
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    for field in ("priority", "status"):
        r = c.patch(f"/api/tasks/{task['id']}", json={field: None}, headers=O)
        assert r.status_code == 422 and "cannot be cleared" in r.json()["detail"]


def test_mutations_need_the_origin_and_a_login():
    c = _client()
    assert c.post("/api/tasks", json={"title": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert TestClient(create_app()).get("/api/tasks").status_code == 401


async def test_another_users_task_is_404():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        task = (await alice.post("/api/tasks", json={"title": "mine"}, headers=O)).json()
        assert (await bob.patch(f"/api/tasks/{task['id']}", json={"title": "x"}, headers=O)).status_code == 404
        assert (await bob.post(f"/api/tasks/{task['id']}/complete", headers=O)).status_code == 404
        assert (await bob.delete(f"/api/tasks/{task['id']}", headers=O)).status_code == 404
        assert (await bob.get("/api/tasks")).json() == []


async def test_keep_vouches_for_a_web_made_task_and_its_series_comes_back_clean():
    """Final review: one web-made task kept re-tainting every run that listed
    it, and its series respawned tainted forever. The user — trusted on this
    route — vouches for it with Keep; no tool can."""
    from roost.tasks.models import TaskDraft
    from roost.tasks.store import TaskStore

    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    task = await TaskStore(cfg).create(alice_id, TaskDraft(title="Water the plants", due_date="2026-10-12",
                                                           recurring="0 9 * * 1"), created_by_bot=None, tainted=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        assert (await bob.post(f"/api/tasks/{task.id}/keep", headers=O)).status_code == 404
        assert (await alice.post(f"/api/tasks/{task.id}/keep", headers={"Origin": "http://evil.example"})).status_code == 403
        kept = await alice.post(f"/api/tasks/{task.id}/keep", headers=O)
        assert kept.status_code == 200 and kept.json()["tainted"] is False
        assert _frames()[-1] == "tasks_changed"
        assert (await alice.post(f"/api/tasks/{task.id}/complete", headers=O)).status_code == 200
        [next_one] = (await alice.get("/api/tasks")).json()
        assert (next_one["title"], next_one["tainted"]) == ("Water the plants", False)
        assert (await alice.post("/api/tasks/no-such-task/keep", headers=O)).status_code == 404


def test_fail_closes_an_open_task_and_the_failed_filter_finds_it():
    """Hub H11: POST …/fail closes an open task as failed, with completed_at
    set. The failed filter lists it, while done and open leave it out. Only an
    open task can fail."""
    c = _client()
    tap = c.post("/api/tasks", json={"title": "Fix the tap"}, headers=O).json()
    paint = c.post("/api/tasks", json={"title": "Paint"}, headers=O).json()
    c.post(f"/api/tasks/{paint['id']}/complete", headers=O)

    failed = c.post(f"/api/tasks/{tap['id']}/fail", headers=O)

    assert (failed.status_code, failed.json()["status"]) == (200, "failed")
    assert failed.json()["completed_at"] is not None
    assert [t["title"] for t in c.get("/api/tasks", params={"status": "failed"}).json()] == ["Fix the tap"]
    assert [t["title"] for t in c.get("/api/tasks", params={"status": "done"}).json()] == ["Paint"]
    assert c.get("/api/tasks").json() == []
    again = c.post(f"/api/tasks/{tap['id']}/fail", headers=O)
    assert (again.status_code, again.json()["detail"]) == (404, "No open task with that id")
    assert c.post(f"/api/tasks/{paint['id']}/fail", headers={"Origin": "http://evil.example"}).status_code == 403
    assert _frames()[-1] == "tasks_changed"


async def test_tasks_join_a_project_with_a_budget_slice_and_filter_by_it():
    """Hub H11: a task joins one of the user's projects, on create or by
    PATCH, and may carry a budget slice (a task in no project too, owner 2026-10-26). ?project_id=
    lists that project's tasks. A project that isn't the user's is a 422."""
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    await register_user(cfg, "bob", "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        shed = (await bob.post("/api/projects", json={"name": "Shed"}, headers=O)).json()
        paint = await alice.post("/api/tasks", json={"title": "Paint", "project_id": house["id"],
                                                     "allocated_budget": "250"}, headers=O)
        await alice.post("/api/tasks", json={"title": "Loose"}, headers=O)
        listed = (await alice.get("/api/tasks", params={"project_id": house["id"]})).json()
        every = (await alice.get("/api/tasks", params={"project_id": ""})).json()
        task_id = paint.json()["id"]
        resliced = await alice.patch(f"/api/tasks/{task_id}", json={"allocated_budget": "12,5"}, headers=O)
        cleared = await alice.patch(f"/api/tasks/{task_id}", json={"allocated_budget": None}, headers=O)
        no_project = await alice.post("/api/tasks", json={"title": "x", "allocated_budget": "10"}, headers=O)
        foreign = await alice.post("/api/tasks", json={"title": "x", "project_id": shed["id"]}, headers=O)
        moved = await alice.patch(f"/api/tasks/{task_id}", json={"project_id": shed["id"]}, headers=O)
        zero = await alice.post("/api/tasks", json={"title": "x", "project_id": house["id"], "allocated_budget": "0"},
                                headers=O)
        unlinked = await alice.patch(f"/api/tasks/{task_id}", json={"project_id": None}, headers=O)
        failed = await alice.post(f"/api/tasks/{task_id}/fail", headers=O)
        frames = await app.state.events.since(alice_id, 0)
    assert paint.status_code == 201
    assert (paint.json()["project_id"], paint.json()["allocated_budget"]) == (house["id"], "250.00")
    assert [t["title"] for t in listed] == ["Paint"]
    assert sorted(t["title"] for t in every) == ["Loose", "Paint"]
    assert (resliced.json()["allocated_budget"], cleared.json()["allocated_budget"]) == ("12.50", None)
    assert (no_project.status_code, no_project.json()["allocated_budget"]) == (201, "10.00")
    assert [(r.status_code, r.json()["detail"]) for r in (foreign, moved)] == [(422, "No such project.")] * 2
    assert zero.status_code == 422
    assert (unlinked.json()["project_id"], failed.json()["status"]) == (None, "failed")
    assert [f["change"] for f in frames if f["type"] == "tasks_changed"][-1] == "failed"


async def test_another_users_task_cannot_be_failed_or_listed_by_project():
    app = create_app()
    cfg = load_config()
    await init_db(cfg)
    for name in ("alice", "bob"):
        await register_user(cfg, name, "pw-123456")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        task = (await alice.post("/api/tasks", json={"title": "mine", "project_id": house["id"]}, headers=O)).json()
        assert (await bob.post(f"/api/tasks/{task['id']}/fail", headers=O)).status_code == 404
        assert (await bob.patch(f"/api/tasks/{task['id']}", json={"project_id": None}, headers=O)).status_code == 404
        assert (await bob.get("/api/tasks", params={"status": "all", "project_id": house["id"]})).json() == []
        assert [(t["id"], t["status"], t["project_id"]) for t in (await alice.get("/api/tasks")).json()] == [
            (task["id"], "todo", house["id"])]



def test_a_due_in_year_one_is_422_with_a_plain_reason_not_a_500():
    c = _client()
    created = c.post("/api/tasks", json={"title": "x", "due_date": "0001-01-01T00:00"}, headers=O)
    assert created.status_code == 422
    assert "before the first day of the calendar" in created.json()["detail"]
    task = c.post("/api/tasks", json={"title": "x"}, headers=O).json()
    patched = c.patch(f"/api/tasks/{task['id']}", json={"due_date": "0001-01-01T00:00"}, headers=O)
    assert patched.status_code == 422 and "first day of the calendar" in patched.json()["detail"]
