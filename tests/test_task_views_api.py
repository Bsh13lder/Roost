"""Task views, reopen, move-overdue and restore-dues over HTTP (Task 10)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from money_http import two_users
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


def test_view_query_and_sort_on_the_route():
    c = client()
    add(c, "Pay rent", due_date=day(-2))
    add(c, "Book flights", due_date=day(0), priority="high")
    add(c, "Café con Ana", due_date=day(3))
    add(c, "Someday thing")
    assert [t["title"] for t in c.get("/api/tasks?view=overdue").json()] == ["Pay rent"]
    assert [t["title"] for t in c.get("/api/tasks?view=today").json()] == ["Book flights"]
    assert [t["title"] for t in c.get("/api/tasks?view=upcoming").json()] == ["Café con Ana"]
    assert [t["title"] for t in c.get("/api/tasks?view=someday").json()] == ["Someday thing"]
    assert [t["title"] for t in c.get("/api/tasks?q=CAFE").json()] == ["Café con Ana"]
    assert [t["title"] for t in c.get("/api/tasks?sort=due").json()][:3] == ["Pay rent", "Book flights", "Café con Ana"]
    assert c.get("/api/tasks?view=nope").status_code == 422
    assert c.get("/api/tasks?sort=nope").status_code == 422
    assert c.get("/api/tasks?q=" + "x" * 101).status_code == 422
    done = add(c, "Finished")
    c.post(f"/api/tasks/{done['id']}/complete", headers=O)
    assert [t["title"] for t in c.get("/api/tasks?view=done").json()] == ["Finished"]


def test_reopen_and_undo_a_recurring_complete():
    c = client()
    task = add(c, "Water plants", due_date=day(0), recurring="0 9 * * *")
    done = c.post(f"/api/tasks/{task['id']}/complete", headers=O).json()
    assert done["status"] == "done" and done["next_id"]
    reopened = c.post(f"/api/tasks/{task['id']}/reopen", headers=O)
    assert reopened.status_code == 200 and reopened.json()["status"] == "todo" and reopened.json()["completed_at"] is None
    assert c.delete(f"/api/tasks/{done['next_id']}", headers=O).status_code == 204
    assert [t["id"] for t in c.get("/api/tasks").json()] == [task["id"]]
    assert c.post(f"/api/tasks/{task['id']}/reopen", headers=O).status_code == 404   # open already
    plain = add(c, "No repeat")
    assert c.post(f"/api/tasks/{plain['id']}/complete", headers=O).json()["next_id"] is None


async def test_reopen_of_another_users_task_is_404():
    async with two_users() as (alice, bob, _):
        task = (await alice.post("/api/tasks", json={"title": "Mine"}, headers=O)).json()
        await alice.post(f"/api/tasks/{task['id']}/complete", headers=O)
        assert (await bob.post(f"/api/tasks/{task['id']}/reopen", headers=O)).status_code == 404
        assert (await alice.get(f"/api/tasks/{task['id']}")).json()["status"] == "done"


def test_move_overdue_to_words_answers_the_old_values():
    c = client()
    a = add(c, "Late one", due_date=day(-3))
    b = add(c, "Late timed", due_date=f"{day(-1)}T09:30")
    add(c, "On time", due_date=day(2))
    moved = c.post("/api/tasks/move-overdue", json={"to": "tomorrow"}, headers=O)
    assert moved.status_code == 200
    before = {m["id"]: m for m in moved.json()["moved"]}
    assert set(before) == {a["id"], b["id"]}
    assert before[a["id"]]["due_date"] == day(-3)
    assert before[b["id"]]["due_date"].startswith(f"{day(-1)}T09:30") and before[b["id"]]["reminder_at"]
    now = {t["id"]: t for t in c.get("/api/tasks").json()}
    assert now[a["id"]]["due_date"] == day(1)
    assert now[b["id"]]["due_date"].startswith(f"{day(1)}T09:30")   # a timed task keeps its time
    assert c.post("/api/tasks/move-overdue", json={"to": "today"}, headers=O).json() == {"moved": []}


def test_restore_dues_puts_them_back():
    c = client()
    a = add(c, "Late one", due_date=day(-3))
    b = add(c, "Late timed", due_date=f"{day(-1)}T09:30")
    moved = c.post("/api/tasks/move-overdue", json={"to": "today"}, headers=O).json()["moved"]
    restored = c.post("/api/tasks/restore-dues", json={"items": moved}, headers=O)
    assert restored.status_code == 200 and restored.json() == {"restored": 2}
    now = {t["id"]: t for t in c.get("/api/tasks").json()}
    assert now[a["id"]]["due_date"] == day(-3)
    assert now[b["id"]]["due_date"].startswith(f"{day(-1)}T09:30")
    assert now[b["id"]]["reminder_at"] and now[b["id"]]["pre_reminders"]


async def test_another_users_task_in_restore_dues_refuses_all():
    async with two_users() as (alice, bob, _):
        mine = (await alice.post("/api/tasks", json={"title": "Mine", "due_date": day(1)}, headers=O)).json()
        theirs = (await bob.post("/api/tasks", json={"title": "Theirs", "due_date": day(1)}, headers=O)).json()
        items = [{"id": mine["id"], "due_date": day(5), "reminder_at": None, "pre_reminders": []},
                 {"id": theirs["id"], "due_date": day(5), "reminder_at": None, "pre_reminders": []}]
        assert (await alice.post("/api/tasks/restore-dues", json={"items": items}, headers=O)).status_code == 404
        assert (await alice.get(f"/api/tasks/{mine['id']}")).json()["due_date"] == day(1)
        assert (await bob.get(f"/api/tasks/{theirs['id']}")).json()["due_date"] == day(1)


def test_restore_dues_validates_iso():
    c = client()
    t = add(c, "x", due_date=day(1))
    for bad in ({"due_date": "soon"}, {"reminder_at": "9 o'clock"}, {"pre_reminders": ["nope"]}):
        item = {"id": t["id"], "due_date": day(4), "reminder_at": None, "pre_reminders": [], **bad}
        assert c.post("/api/tasks/restore-dues", json={"items": [item]}, headers=O).status_code == 422
    assert c.get(f"/api/tasks/{t['id']}").json()["due_date"] == day(1)


def test_writes_need_the_origin():
    c = client()
    assert c.post("/api/tasks/move-overdue", json={"to": "today"}).status_code in (401, 403)
    assert c.post("/api/tasks/restore-dues", json={"items": []}).status_code in (401, 403)


def test_move_overdue_to_an_iso_day_and_time():
    c = client()
    a = add(c, "Late", due_date=day(-3))
    moved = c.post("/api/tasks/move-overdue", json={"to": f"{day(2)}T09:30"}, headers=O)
    assert moved.status_code == 200 and [m["id"] for m in moved.json()["moved"]] == [a["id"]]
    now = c.get(f"/api/tasks/{a['id']}").json()
    assert now["due_date"].startswith(f"{day(2)}T09:30") and now["reminder_at"]
    b = add(c, "Late too", due_date=day(-2))
    c.post("/api/tasks/move-overdue", json={"to": day(4)}, headers=O)
    assert c.get(f"/api/tasks/{b['id']}").json()["due_date"] == day(4)


def test_move_overdue_to_null_clears_dues():
    c = client()
    a = add(c, "Late", due_date=f"{day(-3)}T09:30")
    moved = c.post("/api/tasks/move-overdue", json={"to": None}, headers=O).json()["moved"]
    assert [m["id"] for m in moved] == [a["id"]]
    now = c.get(f"/api/tasks/{a['id']}").json()
    assert (now["due_date"], now["reminder_at"], now["pre_reminders"]) == (None, None, [])


def test_move_overdue_refuses_a_bad_time():
    c = client()
    a = add(c, "Late", due_date=day(-3))
    for bad in (f"{day(2)}T25:99", "whenever-ish"):
        r = c.post("/api/tasks/move-overdue", json={"to": bad}, headers=O)
        assert r.status_code == 422 and "could not read" in r.json()["detail"]
    assert c.get(f"/api/tasks/{a['id']}").json()["due_date"] == day(-3)


def _restore(c, task_id, **fields):
    item = {"id": task_id, "due_date": day(4), "reminder_at": None, "pre_reminders": [], **fields}
    return c.post("/api/tasks/restore-dues", json={"items": [item]}, headers=O)


def test_restore_dues_refuses_unnormalised_forms_with_a_plain_422():
    c = client()
    t = add(c, "x", due_date=day(1))
    bad = ({"due_date": f"{day(4)}T09:30"},                       # naive moment
           {"due_date": f"{day(4)}T09:30:00+05:00"},              # foreign offset
           {"due_date": f"{day(4)}T09:30:00Z"},
           {"due_date": day(4).replace("-", "")},                 # compact day
           {"due_date": f"{day(4).replace('-', '')}T0930"},       # compact moment
           {"reminder_at": f"{day(4)}T09:30"},                    # naive reminder
           {"reminder_at": f"{day(4).replace('-', '')}T0930Z"},
           {"pre_reminders": [f"{day(4)}T09:00"]})
    for fields in bad:
        got = _restore(c, t["id"], **fields)
        assert got.status_code == 422, fields
    assert c.get(f"/api/tasks/{t['id']}").json()["due_date"] == day(1)


def test_restore_dues_stores_the_shape_a_patch_stores():
    c = client()
    patched = add(c, "patched", due_date=f"{day(3)}T09:30")
    restored = add(c, "restored", due_date=day(1))
    local = datetime.fromisoformat(f"{day(3)}T09:30").replace(tzinfo=MADRID_TZ)
    item = {"id": restored["id"], "due_date": local.isoformat(), "reminder_at": local.isoformat(), "pre_reminders": []}
    assert c.post("/api/tasks/restore-dues", json={"items": [item]}, headers=O).status_code == 200
    a, b = (c.get(f"/api/tasks/{i['id']}").json() for i in (patched, restored))
    assert b["reminder_at"] == a["reminder_at"]       # UTC, same shape
    assert b["due_date"] == a["due_date"]             # Madrid, seconds, offset
