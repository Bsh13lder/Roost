"""Projects over HTTP (projects hub Task 8): the Projects tab's list, a
project's page, create / change / delete, top-ups, and the money_changed
frame every change publishes (P7, H2, H4, H5, H8–H10, H14, H15).

Another user's project or top-up is a 404, never the object. Every mutating
route needs the Origin, and every route a login."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from roost.config import RoostConfig, load_config
from roost.constants import GENERAL_PROJECT_NAME, MAX_CATEGORY_NAME_LENGTH, PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.money.topup_store import BELOW_ZERO_TEXT, TAKEN_BACK_TEXT
from roost.projects.service import GENERAL_FIXED_TEXT, GENERAL_NAME_TEXT, LEAD_BOT_TEXT
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
EVIL = {"Origin": "http://evil.example"}
PROJECT_KEYS = {
    "id", "name", "color", "currency", "status", "start_date", "due_date", "lead_bot_id", "total", "month",
    "other_currencies", "starred_total", "money_in", "progress", "tainted", "pinned", "pinned_at",
}
PAGE_KEYS = PROJECT_KEYS | {"tasks", "expenses", "notes", "documents", "topups", "lead_bot_name", "task_money",
                                    "upcoming_charges", "counts", "repeating"}
TOPUP_KEYS = {"id", "amount", "currency", "source", "kind", "topup_id", "undone", "created_at", "can_change"}
NO_BUDGET = {"budget": None, "spent": "0.00", "remaining": None, "used_percent": None, "tone": None}


@dataclass(frozen=True)
class Rig:
    app: FastAPI
    cfg: RoostConfig
    alice_id: str
    bob_id: str
    alice: httpx.AsyncClient
    bob: httpx.AsyncClient


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    alice_id = (await register_user(cfg, "alice", "pw-123456")).id
    bob_id = (await register_user(cfg, "bob", "pw-123456")).id
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://roost.test") as alice, \
            httpx.AsyncClient(transport=transport, base_url="http://roost.test") as bob:
        for client, name in ((alice, "alice"), (bob, "bob")):
            login = await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
            assert login.status_code == 200
        yield Rig(app, cfg, alice_id, bob_id, alice, bob)


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


async def _project(client: httpx.AsyncClient, **fields: Any) -> dict:
    created = await client.post("/api/projects", json=fields, headers=O)
    assert created.status_code == 201, created.text
    return created.json()


async def _page(client: httpx.AsyncClient, project: dict) -> dict:
    page = await client.get(f"/api/projects/{project['id']}")
    assert page.status_code == 200, page.text
    return page.json()


async def _changes(rig: Rig) -> list[tuple[str, str]]:
    frames = await rig.app.state.events.since(rig.alice_id, 0)
    return [(frame["change"], frame["id"]) for frame in frames if frame["type"] == "money_changed"]


async def test_create_list_read_and_change_a_project(rig):
    created = await rig.alice.post("/api/projects", json={
        "name": " Renovation ", "budget": "500", "monthly_budget": "100", "color": PROJECT_COLORS[6],
        "start_date": "2026-10-01", "due_date": "2026-12-31",
    }, headers=O)

    assert created.status_code == 201
    house = created.json()
    assert set(house) == PROJECT_KEYS
    assert (house["name"], house["color"], house["currency"], house["status"], house["tainted"]) == (
        "Renovation", PROJECT_COLORS[6], "EUR", "active", False)
    assert (house["start_date"], house["due_date"], house["lead_bot_id"]) == ("2026-10-01", "2026-12-31", None)
    assert house["total"] == {"budget": "500.00", "spent": "0.00", "remaining": "500.00", "used_percent": 0,
                              "tone": "ok"}
    assert house["month"] == {"budget": "100.00", "spent": "0.00", "remaining": "100.00", "used_percent": 0,
                              "tone": "ok"}
    assert (house["other_currencies"], house["starred_total"], house["progress"]) == (
        {}, "0.00", {"done": 0, "failed": 0, "total": 0, "open": 0, "overdue": 0, "steps_done": 0, "steps_total": 0,
                          "planned_total": "0.00"})
    assert (await rig.alice.get("/api/projects")).json() == [house]
    assert set(await _page(rig.alice, house)) == PAGE_KEYS

    changed = await rig.alice.patch(f"/api/projects/{house['id']}", json={
        "name": "Home", "color": PROJECT_COLORS[2], "due_date": None, "monthly_budget": None,
    }, headers=O)

    assert changed.status_code == 200
    home = changed.json()
    assert (home["id"], home["name"], home["color"], home["due_date"], home["start_date"]) == (
        house["id"], "Home", PROJECT_COLORS[2], None, "2026-10-01")
    assert (home["month"], home["total"]["budget"]) == (NO_BUDGET, "500.00")
    limit = await rig.alice.patch(f"/api/projects/{house['id']}", json={"monthly_budget": "12,50"}, headers=O)
    assert limit.json()["month"]["budget"] == "12.50"


async def test_archived_projects_are_listed_only_when_asked(rig):
    house = await _project(rig.alice, name="House")
    attic = await _project(rig.alice, name="Attic")

    archived = await rig.alice.patch(f"/api/projects/{attic['id']}", json={"status": "archived"}, headers=O)

    assert archived.json()["status"] == "archived"
    assert [p["id"] for p in (await rig.alice.get("/api/projects")).json()] == [house["id"]]
    every = (await rig.alice.get("/api/projects", params={"include_archived": "true"})).json()
    assert [p["name"] for p in every] == ["House", "Attic"]
    assert (await _page(rig.alice, attic))["status"] == "archived"


async def test_general_is_hidden_and_can_be_neither_changed_nor_deleted(rig):
    loose = (await rig.alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)).json()
    general_id = loose["project_id"]
    assert loose["project"] == GENERAL_PROJECT_NAME

    deleted = await rig.alice.delete(f"/api/projects/{general_id}", headers=O)

    assert (deleted.status_code, deleted.json()["detail"]) == (422, GENERAL_FIXED_TEXT)
    for change in ({"name": "Misc"}, {"status": "archived"}, {"color": PROJECT_COLORS[1]}):
        refused = await rig.alice.patch(f"/api/projects/{general_id}", json=change, headers=O)
        assert (refused.status_code, refused.json()["detail"]) == (422, GENERAL_FIXED_TEXT), change
    taken = await rig.alice.post("/api/projects", json={"name": "general"}, headers=O)
    assert (taken.status_code, taken.json()["detail"]) == (422, GENERAL_NAME_TEXT)
    assert (await rig.alice.get("/api/projects", params={"include_archived": "true"})).json() == []
    assert [e["project"] for e in (await rig.alice.get("/api/money/expenses")).json()] == [GENERAL_PROJECT_NAME]


async def test_a_project_page_holds_its_tasks_money_notes_documents_and_top_ups(rig):
    alice = rig.alice
    house = await _project(alice, name="House", budget="300", monthly_budget="100")
    link = {"project_id": house["id"]}
    paint = (await alice.post("/api/tasks", json={"title": "Paint", "allocated_budget": "120", **link},
                              headers=O)).json()
    tiles = (await alice.post("/api/money/expenses", json={"amount": "80", **link}, headers=O)).json()
    taxi = (await alice.post("/api/money/expenses", json={"amount": "9", "currency": "USD", **link},
                             headers=O)).json()
    ideas = (await alice.post("/api/notes", json={"title": "Ideas", "content": "green tiles", **link},
                              headers=O)).json()
    plan = (await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)).json()
    bonus = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "100", "source": "bonus"},
                              headers=O)).json()
    await alice.post("/api/tasks", json={"title": "Loose"}, headers=O)
    await alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)
    await alice.put(f"/api/money/expenses/{tiles['id']}/star", json={"starred": True}, headers=O)

    page = await _page(alice, house)

    assert set(page) == PAGE_KEYS
    assert page["total"] == {"budget": "400.00", "spent": "80.00", "remaining": "320.00", "used_percent": 20,
                             "tone": "ok"}
    assert page["month"] == {"budget": "100.00", "spent": "80.00", "remaining": "20.00", "used_percent": 80,
                             "tone": "warn"}
    assert (page["other_currencies"], page["starred_total"]) == ({"USD": "9.00"}, "80.00")
    assert (page["progress"], page["lead_bot_name"], page["tainted"]) == (
        {"done": 0, "failed": 0, "total": 1, "open": 1, "overdue": 0, "steps_done": 0, "steps_total": 0,
         "planned_total": "120.00"}, None, False)
    assert [(t["id"], t["project_id"], t["allocated_budget"]) for t in page["tasks"]] == [
        (paint["id"], house["id"], "120.00")]
    assert page["task_money"] == {paint["id"]: {"planned": "120.00", "spent": "0.00", "left": "120.00"}}
    assert {e["id"] for e in page["expenses"]} == {tiles["id"], taxi["id"]}
    assert {(e["project"], e["project_id"]) for e in page["expenses"]} == {("House", house["id"])}
    assert [(n["id"], n["project_id"]) for n in page["notes"]] == [(ideas["id"], house["id"])]
    assert [(d["id"], d["project_id"]) for d in page["documents"]] == [(plan["id"], house["id"])]
    credits = [row for row in page["topups"] if row["kind"] == "credit"]
    assert [(row["id"], row["amount"], row["source"], row["undone"]) for row in credits] == [
        (bonus["id"], "100.00", "bonus", False)]
    assert all(set(row) == TOPUP_KEYS for row in page["topups"])
    assert [p["id"] for p in (await alice.get("/api/projects")).json()] == [house["id"]]


async def test_a_name_in_use_is_409_on_rename_and_422_on_create(rig):
    house = await _project(rig.alice, name="House")
    await _project(rig.alice, name="Trip")

    renamed = await rig.alice.patch(f"/api/projects/{house['id']}", json={"name": " trip "}, headers=O)
    created = await rig.alice.post("/api/projects", json={"name": "TRIP"}, headers=O)

    assert (renamed.status_code, renamed.json()["detail"]) == (409, "A project with that name exists.")
    assert created.status_code == 422
    assert sorted(p["name"] for p in (await rig.alice.get("/api/projects")).json()) == ["House", "Trip"]


async def test_bad_project_input_is_422_and_changes_nothing(rig):
    house = await _project(rig.alice, name="House")
    for body in (
        {"name": "   "}, {"name": "x" * (MAX_CATEGORY_NAME_LENGTH + 1)}, {"name": "Trip", "color": "#000000"},
        {"name": "Trip", "currency": "euro"}, {"name": "Trip", "budget": "0"},
        {"name": "Trip", "monthly_budget": "12.345"}, {"name": "Trip", "due_date": "2026-13-01"},
        {"name": "Trip", "start_date": "20261201"}, {"name": "Trip", "category": "travel"},
    ):
        assert (await rig.alice.post("/api/projects", json=body, headers=O)).status_code == 422, body
    for change in (
        {}, {"name": None}, {"color": None}, {"status": "done"}, {"monthly_budget": "-5"}, {"start_date": "soon"},
        {"budget": "10"},
    ):
        refused = await rig.alice.patch(f"/api/projects/{house['id']}", json=change, headers=O)
        assert refused.status_code == 422, change
    assert [(p["name"], p["color"], p["status"]) for p in (await rig.alice.get("/api/projects")).json()] == [
        ("House", house["color"], "active")]


async def test_the_lead_bot_must_be_one_of_your_bots(rig):
    mine = await make_bot(rig.cfg, rig.alice_id, "Fixer")
    bobs = await make_bot(rig.cfg, rig.bob_id, "Builder")

    refused = await rig.alice.post("/api/projects", json={"name": "House", "lead_bot_id": bobs.id}, headers=O)
    house = await _project(rig.alice, name="House", lead_bot_id=mine.id)
    moved = await rig.alice.patch(f"/api/projects/{house['id']}", json={"lead_bot_id": bobs.id}, headers=O)

    assert (refused.status_code, refused.json()["detail"]) == (422, LEAD_BOT_TEXT)
    assert (moved.status_code, moved.json()["detail"]) == (422, LEAD_BOT_TEXT)
    assert (house["lead_bot_id"], (await _page(rig.alice, house))["lead_bot_name"]) == (mine.id, "Fixer")
    cleared = await rig.alice.patch(f"/api/projects/{house['id']}", json={"lead_bot_id": None}, headers=O)
    assert (cleared.json()["lead_bot_id"], (await _page(rig.alice, house))["lead_bot_name"]) == (None, None)


async def test_deleting_a_project_keeps_its_items_unlinked_and_its_money_in_general(rig):
    alice = rig.alice
    house = await _project(alice, name="House")
    link = {"project_id": house["id"]}
    task = (await alice.post("/api/tasks", json={"title": "Buy tiles", **link}, headers=O)).json()
    note = (await alice.post("/api/notes", json={"title": "Ideas", "content": "green", **link}, headers=O)).json()
    doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", **link}, headers=O)).json()
    tiles = (await alice.post("/api/money/expenses", json={"amount": "40", **link}, headers=O)).json()

    deleted = await alice.delete(f"/api/projects/{house['id']}", headers=O)

    assert deleted.status_code == 204
    assert (await alice.get(f"/api/projects/{house['id']}")).status_code == 404
    assert [(t["id"], t["project_id"]) for t in (await alice.get("/api/tasks")).json()] == [(task["id"], None)]
    assert (await alice.get(f"/api/notes/{note['id']}")).json()["project_id"] is None
    assert (await alice.get(f"/api/documents/{doc['id']}")).json()["project_id"] is None
    [moved] = (await alice.get("/api/money/expenses")).json()
    assert (moved["id"], moved["project"], moved["amount"]) == (tiles["id"], GENERAL_PROJECT_NAME, "40.00")
    assert (await alice.get("/api/projects", params={"include_archived": "true"})).json() == []
    assert (await alice.delete(f"/api/projects/{house['id']}", headers=O)).status_code == 404


async def test_top_ups_are_added_edited_undone_and_kept_as_history(rig):
    alice = rig.alice
    house = await _project(alice, name="House")

    added = await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "100", "source": "  birthday "},
                             headers=O)

    assert added.status_code == 201
    topup = added.json()
    assert set(topup) == TOPUP_KEYS
    assert (topup["kind"], topup["amount"], topup["currency"], topup["source"], topup["topup_id"], topup["undone"]) == (
        "credit", "100.00", "EUR", "birthday", None, False)
    edited = await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "150"}, headers=O)
    assert edited.status_code == 200 and set(edited.json()) == TOPUP_KEYS
    assert (await _page(alice, house))["total"]["budget"] == "150.00"
    assert (await alice.post(f"/api/topups/{topup['id']}/undo", headers=O)).status_code == 200
    assert (await _page(alice, house))["total"]["budget"] in (None, "0.00")
    history = (await alice.get(f"/api/projects/{house['id']}/topups")).json()
    assert sorted(row["kind"] for row in history) == ["credit", "edit"]
    assert all(row["undone"] for row in history)
    assert [row["topup_id"] for row in history if row["kind"] == "edit"] == [topup["id"]]
    for bad in ({"amount": "0"}, {"amount": "abc"}, {"amount": "5", "note": "x"},
                {"amount": "5", "source": "x" * (TOPUP_SOURCE_MAX_CHARS + 1)}):
        refused = await alice.post(f"/api/projects/{house['id']}/topups", json=bad, headers=O)
        assert refused.status_code == 422, bad
    assert (await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "-1"}, headers=O)).status_code == 422


async def test_undoing_a_top_up_twice_is_409(rig):
    """H4: only an undone top-up is a conflict (409, Task 2's TopUpUndone). A
    top-up that clearing the total budget took back (H5) breaks a rule instead:
    422 with its own sentence."""
    house = await _project(rig.alice, name="House")
    topup = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "40"}, headers=O)).json()
    assert (await rig.alice.post(f"/api/topups/{topup['id']}/undo", headers=O)).status_code == 200

    again = await rig.alice.post(f"/api/topups/{topup['id']}/undo", headers=O)
    edit = await rig.alice.patch(f"/api/topups/{topup['id']}", json={"amount": "60"}, headers=O)

    assert (again.status_code, edit.status_code) == (409, 409)
    assert (await _page(rig.alice, house))["total"]["budget"] in (None, "0.00")
    assert [change for change, _ in await _changes(rig)].count("topup_undone") == 1
    missing = await rig.alice.post("/api/topups/no-such-top-up/undo", headers=O)
    assert (missing.status_code, missing.json()["detail"]) == (404, "Top-up not found")
    second = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "15"}, headers=O)).json()
    await ProjectStore(rig.cfg).set_budget(rig.alice_id, house["id"], None, created_by_bot=None, tainted=False)
    cleared = (
        await rig.alice.patch(f"/api/topups/{second['id']}", json={"amount": "20"}, headers=O),
        await rig.alice.post(f"/api/topups/{second['id']}/undo", headers=O),
    )
    assert [(answer.status_code, answer.json()["detail"]) for answer in cleared] == [(422, TAKEN_BACK_TEXT)] * 2


async def test_a_top_up_change_that_breaks_a_rule_is_422_not_409(rig):
    """A change that would take the total budget below 0 is a broken rule (422
    with the store's sentence), whether it is an edit or an undo."""
    house = await _project(rig.alice, name="House")
    topup = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "100"}, headers=O)).json()
    lowered = await rig.alice.put(f"/api/projects/{house['id']}/budget", json={"amount": "50"}, headers=O)
    assert lowered.json()["total"]["budget"] == "50.00"

    edit = await rig.alice.patch(f"/api/topups/{topup['id']}", json={"amount": "10"}, headers=O)
    undo = await rig.alice.post(f"/api/topups/{topup['id']}/undo", headers=O)

    assert [(answer.status_code, answer.json()["detail"]) for answer in (edit, undo)] == [(422, BELOW_ZERO_TEXT)] * 2
    page = await _page(rig.alice, house)
    assert (page["total"]["budget"], [row["undone"] for row in page["topups"]]) == ("50.00", [False, False])


async def test_the_total_budget_is_set_and_cleared_on_its_own_route(rig):
    """P3, H5: PUT …/budget sets the total budget and null clears it. Each
    change is a "Budget set" row and a budget_set frame. A bad amount or
    General is 422, an unknown project 404, and PATCH still refuses budget."""
    house = await _project(rig.alice, name="House", monthly_budget="100")
    budget = f"/api/projects/{house['id']}/budget"

    answer = await rig.alice.put(budget, json={"amount": "1200"}, headers=O)

    assert answer.status_code == 200 and set(answer.json()) == PROJECT_KEYS
    assert answer.json()["total"] == {"budget": "1200.00", "spent": "0.00", "remaining": "1200.00",
                                      "used_percent": 0, "tone": "ok"}
    assert answer.json()["month"]["budget"] == "100.00"
    cleared = await rig.alice.put(budget, json={"amount": None}, headers=O)
    assert (cleared.status_code, cleared.json()["total"]) == (200, NO_BUDGET)
    history = (await rig.alice.get(f"/api/projects/{house['id']}/topups")).json()
    assert sorted((row["kind"], row["amount"], row["topup_id"]) for row in history) == [
        ("edit", "-1200.00", None), ("edit", "1200.00", None)]
    for body in ({"amount": "0"}, {"amount": "abc"}, {"amount": "12.345"}, {}, {"amount": "5", "currency": "USD"}):
        assert (await rig.alice.put(budget, json=body, headers=O)).status_code == 422, body
    loose = (await rig.alice.post("/api/money/expenses", json={"amount": "5"}, headers=O)).json()
    general = await rig.alice.put(f"/api/projects/{loose['project_id']}/budget", json={"amount": "50"}, headers=O)
    assert (general.status_code, general.json()["detail"]) == (422, GENERAL_FIXED_TEXT)
    missing = await rig.alice.put("/api/projects/no-such-project/budget", json={"amount": "5"}, headers=O)
    assert (missing.status_code, missing.json()["detail"]) == (404, "Project not found")
    patched = await rig.alice.patch(f"/api/projects/{house['id']}", json={"budget": "10"}, headers=O)
    assert patched.status_code == 422
    assert (await _page(rig.alice, house))["total"] == NO_BUDGET
    assert [change for change in await _changes(rig) if change[0] == "budget_set"] == [
        ("budget_set", house["id"])] * 2


async def test_every_project_change_is_published_on_money_changed(rig):
    alice = rig.alice
    house = await _project(alice, name="House")
    await alice.patch(f"/api/projects/{house['id']}", json={"color": PROJECT_COLORS[3]}, headers=O)
    topup = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "10"}, headers=O)).json()
    await alice.patch(f"/api/topups/{topup['id']}", json={"amount": "12"}, headers=O)
    await alice.post(f"/api/topups/{topup['id']}/undo", headers=O)
    await alice.delete(f"/api/projects/{house['id']}", headers=O)

    assert await _changes(rig) == [
        ("project_created", house["id"]), ("project_updated", house["id"]), ("topup_added", topup["id"]),
        ("topup_edited", topup["id"]), ("topup_undone", topup["id"]), ("project_deleted", house["id"]),
    ]


def test_projects_need_a_login_and_the_origin():
    assert TestClient(create_app()).get("/api/projects").status_code == 401
    c = _client()
    house = c.post("/api/projects", json={"name": "House"}, headers=O).json()
    topup = c.post(f"/api/projects/{house['id']}/topups", json={"amount": "5"}, headers=O).json()
    for method, path, body in (
        ("POST", "/api/projects", {"name": "Trip"}),
        ("PATCH", f"/api/projects/{house['id']}", {"color": PROJECT_COLORS[1]}),
        ("DELETE", f"/api/projects/{house['id']}", None),
        ("PUT", f"/api/projects/{house['id']}/budget", {"amount": "9"}),
        ("PUT", f"/api/projects/{house['id']}/budget", {"amount": None}),
        ("POST", f"/api/projects/{house['id']}/topups", {"amount": "5"}),
        ("PATCH", f"/api/topups/{topup['id']}", {"amount": "6"}),
        ("POST", f"/api/topups/{topup['id']}/undo", None),
        ("POST", f"/api/projects/{house['id']}/keep", None),
    ):
        assert c.request(method, path, json=body, headers=EVIL).status_code == 403, (method, path)
    [kept] = c.get("/api/projects").json()
    assert (kept["name"], kept["color"], kept["total"]["budget"]) == ("House", house["color"], "5.00")


async def test_another_users_projects_and_top_ups_are_404(rig):
    house = await _project(rig.alice, name="House")
    topup = (await rig.alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "10"}, headers=O)).json()
    bob, project_id, topup_id = rig.bob, house["id"], topup["id"]

    answers = (
        await bob.get(f"/api/projects/{project_id}"),
        await bob.patch(f"/api/projects/{project_id}", json={"color": PROJECT_COLORS[1]}, headers=O),
        await bob.delete(f"/api/projects/{project_id}", headers=O),
        await bob.put(f"/api/projects/{project_id}/budget", json={"amount": "99"}, headers=O),
        await bob.put(f"/api/projects/{project_id}/budget", json={"amount": None}, headers=O),
        await bob.get(f"/api/projects/{project_id}/topups"),
        await bob.post(f"/api/projects/{project_id}/topups", json={"amount": "5"}, headers=O),
        await bob.patch(f"/api/topups/{topup_id}", json={"amount": "20"}, headers=O),
        await bob.post(f"/api/topups/{topup_id}/undo", headers=O),
        await bob.post(f"/api/projects/{project_id}/keep", headers=O),
    )

    assert [answer.status_code for answer in answers] == [404] * 10
    assert answers[0].json()["detail"] == "Project not found"
    assert (await bob.get("/api/projects", params={"include_archived": "true"})).json() == []
    page = await _page(rig.alice, house)
    assert (page["color"], page["total"]["budget"], [row["undone"] for row in page["topups"]]) == (
        house["color"], "10.00", [False])


async def test_keep_clears_the_from_web_content_mark_of_a_project(rig):
    """A project a bot made after reading a web page is stored tainted. Keep is the user vouching
    for it: the mark goes, the project is announced as updated, and Keep again is harmless."""
    made = await ProjectStore(rig.cfg).create(rig.alice_id, ProjectDraft(name="Trip", budget=Decimal("2000")),
                                              created_by_bot=None, tainted=True)
    assert [row["tainted"] for row in (await rig.alice.get("/api/projects")).json()] == [True]

    kept = await rig.alice.post(f"/api/projects/{made.id}/keep", headers=O)

    assert kept.status_code == 200
    body = kept.json()
    assert set(body) == PROJECT_KEYS
    assert (body["id"], body["name"], body["tainted"], body["total"]["budget"]) == (made.id, "Trip", False, "2000.00")
    assert [row["tainted"] for row in (await rig.alice.get("/api/projects")).json()] == [False]
    assert (await _page(rig.alice, {"id": made.id}))["tainted"] is False
    assert await _changes(rig) == [("project_updated", made.id)]
    again = await rig.alice.post(f"/api/projects/{made.id}/keep", headers=O)
    assert (again.status_code, again.json()["tainted"]) == (200, False)


async def test_keep_of_another_users_or_an_unknown_project_is_404_and_changes_nothing(rig):
    made = await ProjectStore(rig.cfg).create(rig.alice_id, ProjectDraft(name="Trip"), created_by_bot=None,
                                              tainted=True)

    theirs = await rig.bob.post(f"/api/projects/{made.id}/keep", headers=O)
    unknown = await rig.alice.post("/api/projects/no-such-project/keep", headers=O)

    assert [(a.status_code, a.json()["detail"]) for a in (theirs, unknown)] == [(404, "Project not found")] * 2
    assert [row["tainted"] for row in (await rig.alice.get("/api/projects")).json()] == [True]
    assert await _changes(rig) == []


async def test_keep_needs_the_origin(rig):
    made = await ProjectStore(rig.cfg).create(rig.alice_id, ProjectDraft(name="Trip"), created_by_bot=None,
                                              tainted=True)

    evil = await rig.alice.post(f"/api/projects/{made.id}/keep", headers=EVIL)

    assert evil.status_code == 403
    assert [row["tainted"] for row in (await rig.alice.get("/api/projects")).json()] == [True]


async def test_the_history_says_which_top_ups_can_still_be_changed(rig):
    """can_change is true only for a top-up that is neither undone nor already taken back when the
    total budget was cleared (H5): the web hides Change and Undo on the others, which would answer 422."""
    alice, store = rig.alice, ProjectStore(rig.cfg)
    house = await _project(alice, name="House", budget="300")
    old = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "50"}, headers=O)).json()
    undone = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "5"}, headers=O)).json()
    await alice.post(f"/api/topups/{undone['id']}/undo", headers=O)
    assert old["can_change"] is True
    await store.set_budget(rig.alice_id, house["id"], None, created_by_bot=None, tainted=False)
    await alice.put(f"/api/projects/{house['id']}/budget", json={"amount": "200"}, headers=O)
    fresh = (await alice.post(f"/api/projects/{house['id']}/topups", json={"amount": "20"}, headers=O)).json()
    edited = await alice.patch(f"/api/topups/{fresh['id']}", json={"amount": "25"}, headers=O)

    listed = (await alice.get(f"/api/projects/{house['id']}/topups")).json()
    page = (await _page(alice, house))["topups"]

    assert listed == page
    flags = {row["id"]: row["can_change"] for row in listed}
    assert flags[old["id"]] is False                      # the clearing took it back
    assert flags[undone["id"]] is False                   # undone
    assert flags[fresh["id"]] is True                     # made after the clearing
    assert (edited.json()["kind"], edited.json()["can_change"]) == ("edit", False)    # a change row is nothing to change
    assert [row["can_change"] for row in listed if row["kind"] == "edit"] == [False] * 4
    refused = await alice.patch(f"/api/topups/{old['id']}", json={"amount": "60"}, headers=O)
    assert (refused.status_code, refused.json()["detail"]) == (422, TAKEN_BACK_TEXT)


async def test_general_is_not_a_link_target_for_tasks_notes_and_documents(rig):
    """The tools refuse General (H2), so the routes do too, with the same sentence (422): General is
    where loose money goes, not a project to file work under. Unlinking (null) and real projects still work."""
    alice = rig.alice
    general_id = (await alice.post("/api/money/expenses", json={"amount": "5"}, headers=O))\
        .json()["project_id"]
    house = await _project(alice, name="House")
    task = (await alice.post("/api/tasks", json={"title": "Paint", "project_id": house["id"]}, headers=O)).json()
    note = (await alice.post("/api/notes", json={"title": "Ideas", "project_id": house["id"]}, headers=O)).json()
    doc = (await alice.post("/api/documents", json={"kind": "doc", "title": "Plan", "project_id": house["id"]},
                            headers=O)).json()

    attempts = (
        await alice.post("/api/tasks", json={"title": "Loose", "project_id": general_id}, headers=O),
        await alice.patch(f"/api/tasks/{task['id']}", json={"project_id": general_id}, headers=O),
        await alice.post("/api/notes", json={"title": "Loose", "project_id": general_id}, headers=O),
        await alice.put(f"/api/notes/{note['id']}/project", json={"project_id": general_id}, headers=O),
        await alice.post("/api/documents", json={"kind": "doc", "title": "Loose", "project_id": general_id},
                         headers=O),
        await alice.post("/api/documents", json={"kind": "sheet", "title": "Loose", "project_id": general_id},
                         headers=O),
        await alice.put(f"/api/documents/{doc['id']}/project", json={"project_id": general_id}, headers=O),
    )

    assert [(a.status_code, a.json()["detail"]) for a in attempts] == [(422, GENERAL_FIXED_TEXT)] * 7
    assert [t["title"] for t in (await alice.get("/api/tasks", params={"status": "all"})).json()] == ["Paint"]
    assert (await alice.get("/api/tasks")).json()[0]["project_id"] == house["id"]
    assert [n["project_id"] for n in (await alice.get("/api/notes")).json()] == [house["id"]]
    assert [d["project_id"] for d in (await alice.get("/api/documents")).json()] == [house["id"]]
    unlinked = (
        await alice.patch(f"/api/tasks/{task['id']}", json={"project_id": None}, headers=O),
        await alice.put(f"/api/notes/{note['id']}/project", json={"project_id": None}, headers=O),
        await alice.put(f"/api/documents/{doc['id']}/project", json={"project_id": None}, headers=O),
    )
    assert [a.status_code for a in unlinked] == [200] * 3


async def test_an_unknown_project_is_still_the_stores_no_such_project_on_the_link_routes(rig):
    refused = await rig.alice.post("/api/tasks", json={"title": "Loose", "project_id": "no-such-project"}, headers=O)
    assert (refused.status_code, refused.json()["detail"]) == (422, "No such project.")
