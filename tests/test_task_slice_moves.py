"""A task's budget slice is in its project's currency (projects hub H11), so it follows the task's
project (polish round A, item 6):

- deleting a project clears its tasks' slices together with the link, in one transaction;
- moving a task to a project in another currency clears the slice, and the reply says why;
- moving it to a project in the same currency, or sending the same project again, keeps it;
- a slice sent in the same change wins; unlinking the task keeps the slice when General (where a task in
  no project counts its money, owner 2026-10-26) uses the same currency, and clears it otherwise."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

import httpx
import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.store import TaskStore
from roost.llm.types import ToolCallRequested, TurnDone
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
CLEARED = "Its budget slice was cleared because {project} uses {currency}."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _project(cfg, user_id, name, currency="EUR"):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name, currency=currency),
                                          created_by_bot=None, tainted=False)


async def _sliced_task(cfg, user_id, project, title="Paint the hall", amount="100"):
    return await TaskStore(cfg).create(
        user_id, TaskDraft(title=title, project_id=project.id, allocated_budget=Decimal(amount)),
        created_by_bot=None, tainted=False)


async def _row(cfg, task_id):
    async with db_session(cfg) as db:
        return await (await db.execute(
            "SELECT project_id, allocated_budget, updated_at FROM tasks WHERE id = ?", (task_id,))).fetchone()


# -- deleting a project ------------------------------------------------------------------------


async def test_deleting_a_project_clears_the_slices_of_its_tasks_with_the_link(cfg, user_id):
    house, garden = await _project(cfg, user_id, "House"), await _project(cfg, user_id, "Garden")
    paint = await _sliced_task(cfg, user_id, house)
    binned = await _sliced_task(cfg, user_id, house, "Old quote")
    await TaskStore(cfg).delete(user_id, binned.id)
    mow = await _sliced_task(cfg, user_id, garden, "Mow", "20")

    assert await ProjectStore(cfg).delete(user_id, house.id) is True

    for task_id in (paint.id, binned.id):
        row = await _row(cfg, task_id)
        assert (row["project_id"], row["allocated_budget"]) == (None, None)
    assert (await TaskStore(cfg).get(user_id, paint.id)).allocated_budget is None
    kept = await TaskStore(cfg).get(user_id, mow.id)
    assert (kept.project_id, kept.allocated_budget) == (garden.id, Decimal("20.00"))


async def test_unlink_project_clears_the_slices_too(cfg, user_id):
    house = await _project(cfg, user_id, "House")
    task = await _sliced_task(cfg, user_id, house)
    assert await TaskStore(cfg).unlink_project(user_id, house.id) == 1
    row = await _row(cfg, task.id)
    assert (row["project_id"], row["allocated_budget"]) == (None, None)


async def test_a_failed_delete_leaves_the_task_linked_with_its_slice(cfg, user_id, monkeypatch):
    """One transaction: if the project can't be deleted, nothing of the hand-over stays."""
    house = await _project(cfg, user_id, "House")
    task = await _sliced_task(cfg, user_id, house)
    import roost.money.project_store as store_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store_module, "_general_id", _boom)
    with pytest.raises(RuntimeError):
        await ProjectStore(cfg).delete(user_id, house.id)
    row = await _row(cfg, task.id)
    assert row["project_id"] == house.id and row["allocated_budget"] is not None


# -- moving a task (the store) -----------------------------------------------------------------


async def test_moving_to_a_project_in_another_currency_clears_the_slice(cfg, user_id):
    house, trip = await _project(cfg, user_id, "House"), await _project(cfg, user_id, "Trip", "USD")
    task = await _sliced_task(cfg, user_id, house)
    moved = await TaskStore(cfg).update(user_id, task.id, TaskPatch({"project_id": trip.id}))
    assert (moved.project_id, moved.allocated_budget) == (trip.id, None)
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert (stored.project_id, stored.allocated_budget) == (trip.id, None)


async def test_moving_to_a_project_in_the_same_currency_keeps_the_slice(cfg, user_id):
    house, garden = await _project(cfg, user_id, "House", "USD"), await _project(cfg, user_id, "Garden", "USD")
    task = await _sliced_task(cfg, user_id, house)
    moved = await TaskStore(cfg).update(user_id, task.id, TaskPatch({"project_id": garden.id}))
    assert (moved.project_id, moved.allocated_budget) == (garden.id, Decimal("100.00"))


async def test_sending_the_same_project_again_keeps_the_slice(cfg, user_id):
    house = await _project(cfg, user_id, "House")
    task = await _sliced_task(cfg, user_id, house)
    again = await TaskStore(cfg).update(user_id, task.id, TaskPatch({"project_id": house.id, "priority": "high"}))
    assert (again.project_id, again.allocated_budget) == (house.id, Decimal("100.00"))


async def test_a_slice_sent_with_the_move_wins(cfg, user_id):
    house, trip = await _project(cfg, user_id, "House"), await _project(cfg, user_id, "Trip", "USD")
    task = await _sliced_task(cfg, user_id, house)
    moved = await TaskStore(cfg).update(
        user_id, task.id, TaskPatch({"project_id": trip.id, "allocated_budget": Decimal("40")}))
    assert (moved.project_id, moved.allocated_budget) == (trip.id, Decimal("40.00"))


async def test_unlinking_a_task_keeps_its_slice_only_in_generals_currency(cfg, user_id):
    house, trip = await _project(cfg, user_id, "House"), await _project(cfg, user_id, "Trip", "USD")
    euros, dollars = await _sliced_task(cfg, user_id, house), await _sliced_task(cfg, user_id, trip, "Fly")
    kept = await TaskStore(cfg).update(user_id, euros.id, TaskPatch({"project_id": None}))
    cleared = await TaskStore(cfg).update(user_id, dollars.id, TaskPatch({"project_id": None}))
    assert (kept.project_id, kept.allocated_budget) == (None, Decimal("100.00"))
    assert (cleared.project_id, cleared.allocated_budget) == (None, None)


async def test_a_change_that_does_not_touch_the_project_keeps_the_slice(cfg, user_id):
    house = await _project(cfg, user_id, "House")
    task = await _sliced_task(cfg, user_id, house)
    renamed = await TaskStore(cfg).update(user_id, task.id, TaskPatch({"title": "Paint it white"}))
    assert (renamed.title, renamed.allocated_budget) == ("Paint it white", Decimal("100.00"))


async def test_a_slice_left_without_a_project_before_this_fix_is_dropped_when_the_task_joins_a_project(cfg, user_id):
    """An old delete kept the slice; its currency is unknown now, so it can't be vouched for."""
    house, trip = await _project(cfg, user_id, "House"), await _project(cfg, user_id, "Trip", "USD")
    task = await _sliced_task(cfg, user_id, house)
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET project_id = NULL WHERE id = ?", (task.id,))
        await db.commit()
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert (stored.project_id, stored.allocated_budget) == (None, Decimal("100.00"))
    assert (await TaskStore(cfg).update(user_id, task.id, TaskPatch({"title": "Paint"}))).allocated_budget == Decimal("100.00")
    moved = await TaskStore(cfg).update(user_id, task.id, TaskPatch({"project_id": trip.id}))
    assert (moved.project_id, moved.allocated_budget) == (trip.id, None)


async def test_a_move_into_a_project_that_is_not_yours_is_refused_and_keeps_the_slice(cfg, user_id):
    house = await _project(cfg, user_id, "House")
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    theirs = await _project(cfg, bob, "Shed", "USD")
    task = await _sliced_task(cfg, user_id, house)
    with pytest.raises(ValueError, match=r"^No such project\.$"):
        await TaskStore(cfg).update(user_id, task.id, TaskPatch({"project_id": theirs.id}))
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert (stored.project_id, stored.allocated_budget) == (house.id, Decimal("100.00"))


# -- the reply: HTTP ---------------------------------------------------------------------------


@asynccontextmanager
async def _api(app, name):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        await client.post("/api/auth/login", json={"username": name, "password": "pw-123456"}, headers=O)
        yield client


async def test_patch_says_when_a_move_cleared_the_slice(cfg, user_id):
    app = create_app()
    async with _api(app, "alice") as alice:
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        trip = (await alice.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O)).json()
        garden = (await alice.post("/api/projects", json={"name": "Garden"}, headers=O)).json()
        task = (await alice.post("/api/tasks", json={"title": "Paint", "project_id": house["id"],
                                                     "allocated_budget": "100"}, headers=O)).json()
        to_garden = await alice.patch(f"/api/tasks/{task['id']}", json={"project_id": garden["id"]}, headers=O)
        to_trip = await alice.patch(f"/api/tasks/{task['id']}", json={"project_id": trip["id"]}, headers=O)
        retitled = await alice.patch(f"/api/tasks/{task['id']}", json={"title": "Paint more"}, headers=O)
    assert (to_garden.json()["allocated_budget"], "notice" in to_garden.json()) == ("100.00", False)
    assert to_trip.json()["allocated_budget"] is None
    assert to_trip.json()["notice"] == CLEARED.format(project="Trip", currency="USD")
    assert "notice" not in retitled.json()


async def test_patch_that_sends_its_own_slice_with_the_move_has_no_notice(cfg, user_id):
    app = create_app()
    async with _api(app, "alice") as alice:
        house = (await alice.post("/api/projects", json={"name": "House"}, headers=O)).json()
        trip = (await alice.post("/api/projects", json={"name": "Trip", "currency": "USD"}, headers=O)).json()
        task = (await alice.post("/api/tasks", json={"title": "Paint", "project_id": house["id"],
                                                     "allocated_budget": "100"}, headers=O)).json()
        moved = await alice.patch(f"/api/tasks/{task['id']}",
                                  json={"project_id": trip["id"], "allocated_budget": "30"}, headers=O)
    assert (moved.json()["allocated_budget"], "notice" in moved.json()) == ("30.00", False)


# -- the reply: the tool -----------------------------------------------------------------------


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def test_update_task_says_when_a_move_cleared_the_slice(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    house = await _project(cfg, user_id, "House")
    await _project(cfg, user_id, "Trip", "USD")
    await _project(cfg, user_id, "Garden")
    await _sliced_task(cfg, user_id, house)
    rig = make_rig(cfg, team_model({"Life admin": [
        _tool("u1", "update_task", task="Paint the hall", project="Garden"),
        _tool("u2", "update_task", task="Paint the hall", project="Trip"),
        say("Done."),
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "move the paint task around")
    await wait_idle(rig.runner)

    same, other = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]
    assert same.endswith(" Project: “Garden”, budget 100.00 EUR.")
    assert other.endswith(" Project: “Trip”. " + CLEARED.format(project="Trip", currency="USD"))


async def test_unlinking_a_task_says_its_slice_went_too_in_the_tool_and_in_patch(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    house = await _project(cfg, user_id, "House", "USD")   # General is in euros, so the slice can't stay
    await _sliced_task(cfg, user_id, house, "Paint the hall")
    by_http = await _sliced_task(cfg, user_id, house, "Tile the floor", "50")
    rig = make_rig(cfg, team_model({"Life admin": [
        _tool("u", "update_task", task="Paint the hall", project=""),
        say("Done."),
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "take the paint task out of its project")
    await wait_idle(rig.runner)
    [unlinked] = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]
    assert unlinked.endswith(" No project. Its budget slice was cleared because it has no project now.")

    app = create_app()
    async with _api(app, "alice") as alice:
        patched = await alice.patch(f"/api/tasks/{by_http.id}", json={"project_id": None}, headers=O)
    assert patched.json()["allocated_budget"] is None
    assert patched.json()["notice"] == "Its budget slice was cleared because it has no project now."
