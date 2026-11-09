"""Tasks learn projects (projects hub, H11): the project link and its budget
slice (enc:v2 under tasks:allocated_budget), the failed status and its
respawn, the failed and project filters, closed_between and unlink_project.

A project that isn't the user's (another user's, a deleted one, an unknown
id) is refused with "No such project." and nothing is written."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.tasks.format import task_line, task_out
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.service import TaskService, respawn_draft
from roost.tasks.store import TaskStore

_REFUSED = r"^No such project\.$"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg):
    return TaskStore(cfg)


async def _project(cfg, user_id, name="Renovation"):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name), created_by_bot=None, tainted=False)


async def _task(store, user_id, title="Paint the hall", **fields):
    return await store.create(user_id, TaskDraft(title=title, **fields), created_by_bot=None, tainted=False)


async def _set_completed_at(cfg, task_id, completed_at):
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (completed_at, task_id))
        await db.commit()


async def test_a_task_keeps_its_project_and_budget_slice(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("250"))
    again = await store.get(user_id, task.id)
    assert (task.project_id, task.allocated_budget) == (project.id, Decimal("250.00"))
    assert (again.project_id, again.allocated_budget) == (project.id, Decimal("250.00"))


async def test_a_task_with_no_project_has_no_slice(cfg, store, user_id):
    task = await _task(store, user_id)
    assert (task.project_id, task.allocated_budget) == (None, None)
    out = task_out(task)
    assert (out["project_id"], out["allocated_budget"]) == (None, None)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id, allocated_budget FROM tasks WHERE id = ?",
                                      (task.id,))).fetchone()
    assert (row["project_id"], row["allocated_budget"]) == (None, None)


async def test_the_budget_slice_is_ciphertext_under_its_own_aad(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("12.5"))
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id, allocated_budget FROM tasks WHERE id = ?",
                                      (task.id,))).fetchone()
    assert row["project_id"] == project.id                    # ids stay plaintext
    assert row["allocated_budget"].startswith("enc:v2:") and "12.50" not in row["allocated_budget"]
    dek = await get_user_dek(cfg, user_id)
    assert decrypt(row["allocated_budget"], dek, user_aad(user_id, "tasks:allocated_budget")) == "12.50"


async def test_a_slice_copied_from_another_column_reads_as_none(cfg, store, user_id, caplog):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("40"))
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET allocated_budget = title WHERE id = ?", (task.id,))
        await db.commit()
    with caplog.at_level(logging.WARNING, logger="roost.tasks.store"):
        again = await store.get(user_id, task.id)
    assert (again.title, again.allocated_budget) == ("Paint the hall", None)
    assert any(task.id in record.getMessage() and "unreadable budget slice" in record.getMessage()
               for record in caplog.records)


async def test_another_users_project_is_refused(cfg, store, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await _project(cfg, bob, "Garage")
    with pytest.raises(ValueError, match=_REFUSED):
        await _task(store, user_id, "Fix the door", project_id=bobs.id)
    task = await _task(store, user_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await store.update(user_id, task.id, TaskPatch({"project_id": bobs.id}))
    assert [(t.title, t.project_id) for t in await store.list(user_id, status="all")] == [("Paint the hall", None)]


async def test_an_unknown_or_deleted_project_is_refused(cfg, store, user_id):
    gone = await _project(cfg, user_id, "Old flat")
    assert await ProjectStore(cfg).delete(user_id, gone.id) is True
    for project_id in ("no-such-project", gone.id):
        with pytest.raises(ValueError, match=_REFUSED):
            await _task(store, user_id, project_id=project_id)
    assert await store.list(user_id, status="all") == ()


async def test_a_task_in_no_project_may_have_a_budget_slice(cfg, store, user_id):
    """Owner, 2026-10-26: the drawer sets a budget on any task; one in no project counts in General's currency."""
    made = await _task(store, user_id, allocated_budget=Decimal("10"))
    task = await _task(store, user_id)
    sliced = await store.update(user_id, task.id, TaskPatch({"allocated_budget": Decimal("12.5")}))
    assert (made.allocated_budget, sliced.allocated_budget) == (Decimal("10.00"), Decimal("12.50"))
    assert (await store.get(user_id, task.id)).allocated_budget == Decimal("12.50")
    assert await store.money_currency(user_id, task) == "EUR"


@pytest.mark.parametrize(("amount", "reason"), (
    (Decimal("0"), "more than 0"), (Decimal("-5"), "more than 0"), (Decimal("1000001"), "more than 0"),
    (Decimal("1.005"), "at most 2 decimals"),
))
async def test_a_budget_slice_follows_the_amount_rules(cfg, store, user_id, amount, reason):
    project = await _project(cfg, user_id)
    with pytest.raises(ValueError, match=reason):
        await _task(store, user_id, project_id=project.id, allocated_budget=amount)
    assert await store.list(user_id, status="all") == ()


async def test_the_project_and_its_slice_can_be_changed_and_cleared(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    task = await _task(store, user_id, project_id=house.id, allocated_budget=Decimal("100"))
    moved = await store.update(user_id, task.id, TaskPatch({"project_id": garden.id, "allocated_budget": Decimal("40")}))
    assert (moved.project_id, moved.allocated_budget) == (garden.id, Decimal("40.00"))
    cleared = await store.update(user_id, task.id, TaskPatch({"allocated_budget": None}))
    assert (cleared.project_id, cleared.allocated_budget) == (garden.id, None)
    await store.update(user_id, task.id, TaskPatch({"project_id": None}))
    again = await store.get(user_id, task.id)
    assert (again.project_id, again.allocated_budget) == (None, None)


async def test_an_unrelated_change_leaves_a_slice_with_no_project_alone(cfg, store, user_id):
    """An older delete kept the slices of its tasks. A later title change on such a task must still go
    through, and leave the slice as it was."""
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("30"))
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET project_id = NULL WHERE id = ?", (task.id,))
        await db.commit()
    renamed = await store.update(user_id, task.id, TaskPatch({"title": "Paint the hall white"}))
    assert (renamed.title, renamed.project_id, renamed.allocated_budget) == ("Paint the hall white", None, Decimal("30.00"))


def test_a_patch_can_carry_the_project_and_the_slice():
    patch = TaskPatch({"project_id": None, "allocated_budget": None})
    assert dict(patch.changes) == {"project_id": None, "allocated_budget": None}


async def test_list_filters_by_project(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    await _task(store, user_id, "Paint", project_id=house.id)
    await _task(store, user_id, "Tiles", project_id=house.id)
    await _task(store, user_id, "Mow", project_id=garden.id)
    await _task(store, user_id, "Dentist")
    plaster = await _task(store, user_id, "Plaster", project_id=house.id)
    await store.complete(user_id, plaster.id)
    assert {t.title for t in await store.list(user_id, project_id=house.id)} == {"Paint", "Tiles"}
    assert {t.title for t in await store.list(user_id, status="all", project_id=house.id)} == {"Paint", "Tiles", "Plaster"}
    assert [t.title for t in await store.list(user_id, status="done", project_id=house.id)] == ["Plaster"]
    assert len(await store.list(user_id)) == 4
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.list(bob, status="all", project_id=house.id) == ()


async def test_fail_closes_an_open_task_once_and_leaves_its_steps_open(cfg, store, user_id):
    task = await _task(store, user_id, steps=("buy paint",))
    failed = await store.fail(user_id, task.id)
    assert (failed.status, failed.steps[0].done) == ("failed", False) and failed.completed_at
    again = await store.get(user_id, task.id)
    assert (again.status, again.completed_at, again.steps[0].done) == ("failed", failed.completed_at, False)
    assert await store.fail(user_id, task.id) is None             # already failed
    assert await store.complete(user_id, task.id) is None         # and no longer open


async def test_only_an_open_task_of_your_own_can_fail(cfg, store, user_id):
    done = await _task(store, user_id, "done")
    await store.complete(user_id, done.id)
    cancelled = await _task(store, user_id, "cancelled")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    started = await _task(store, user_id, "started")
    await store.update(user_id, started.id, TaskPatch({"status": "in_progress"}))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.fail(user_id, done.id) is None
    assert await store.fail(user_id, cancelled.id) is None
    assert await store.fail(bob, started.id) is None
    assert await store.fail(user_id, "no-such-task") is None
    assert (await store.fail(user_id, started.id)).status == "failed"


async def test_the_done_filter_leaves_failed_tasks_out_and_the_failed_filter_has_them(cfg, store, user_id):
    done = await _task(store, user_id, "done")
    failed = await _task(store, user_id, "failed")
    await _task(store, user_id, "open")
    await store.complete(user_id, done.id)
    await store.fail(user_id, failed.id)
    assert [t.title for t in await store.list(user_id, status="done")] == ["done"]
    assert [t.title for t in await store.list(user_id, status="failed")] == ["failed"]
    assert [t.title for t in await store.list(user_id)] == ["open"]
    assert len(await store.list(user_id, status="all")) == 3


async def test_closed_between_has_the_done_and_failed_tasks_of_the_window(cfg, store, user_id):
    window = ("2026-10-13T22:00:00+00:00", "2026-10-14T22:00:00+00:00")       # 2026-10-14 in Madrid
    for title, close, at in (
        ("too early", store.complete, "2026-10-13T21:59:59.999999+00:00"),
        ("first", store.complete, "2026-10-13T22:00:00+00:00"),
        ("failed", store.fail, "2026-10-14T12:30:00.250000+00:00"),
        ("last", store.complete, "2026-10-14T21:59:59.999999+00:00"),
        ("too late", store.fail, "2026-10-14T22:00:00+00:00"),
    ):
        task = await _task(store, user_id, title)
        await close(user_id, task.id)
        await _set_completed_at(cfg, task.id, at)
    gone = await _task(store, user_id, "deleted")
    await store.complete(user_id, gone.id)
    await _set_completed_at(cfg, gone.id, "2026-10-14T10:00:00+00:00")
    await store.delete(user_id, gone.id)
    cancelled = await _task(store, user_id, "cancelled")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    await _set_completed_at(cfg, cancelled.id, "2026-10-14T10:00:00+00:00")
    await _task(store, user_id, "open")
    closed = await store.closed_between(user_id, *window)
    assert [(t.title, t.status) for t in closed] == [("first", "done"), ("failed", "failed"), ("last", "done")]


async def test_closed_between_reads_any_offset_as_utc_and_refuses_a_bare_time(cfg, store, user_id):
    task = await _task(store, user_id)
    await store.complete(user_id, task.id)
    await _set_completed_at(cfg, task.id, "2026-10-14T21:30:00+00:00")         # 23:30 in Madrid
    madrid = ("2026-10-14T00:00:00+02:00", "2026-10-15T00:00:00+02:00")
    assert [t.id for t in await store.closed_between(user_id, *madrid)] == [task.id]
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.closed_between(bob, *madrid) == ()
    with pytest.raises(ValueError, match="has no time zone"):
        await store.closed_between(user_id, "2026-10-14T00:00:00", "2026-10-15T00:00:00")
    with pytest.raises(ValueError, match="is not a time"):
        await store.closed_between(user_id, "yesterday", "2026-10-15T00:00:00+00:00")


async def test_unlink_project_keeps_the_tasks_and_drops_the_link(cfg, store, user_id):
    house, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    paint = await _task(store, user_id, "Paint", project_id=house.id, allocated_budget=Decimal("80"))
    await _task(store, user_id, "Tiles", project_id=house.id)
    binned = await _task(store, user_id, "Old quote", project_id=house.id)
    await store.delete(user_id, binned.id)
    mow = await _task(store, user_id, "Mow", project_id=garden.id)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.unlink_project(bob, house.id) == 0
    assert await store.unlink_project(user_id, house.id) == 3          # the deleted one too, as H9's delete does
    assert await store.list(user_id, status="all", project_id=house.id) == ()
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT project_id FROM tasks WHERE id = ?", (binned.id,))).fetchone()
    assert row["project_id"] is None
    kept = await store.get(user_id, paint.id)
    assert (kept.title, kept.project_id, kept.allocated_budget) == ("Paint", None, None)   # the slice goes with the link
    assert (await store.get(user_id, mow.id)).project_id == garden.id


async def test_failing_publishes_failed_and_a_recurring_task_comes_back_in_its_project(cfg, store, user_id):
    events = EventHub(cfg)
    service = TaskService(store, events)
    project = await _project(cfg, user_id)
    task = await service.add(user_id, TaskDraft(title="Water the plants", due_date="2026-10-12",
                                                recurring="0 9 * * 1", project_id=project.id,
                                                allocated_budget=Decimal("15")))
    outcome = await service.fail(user_id, task.id)
    assert (outcome.done.id, outcome.done.status) == (task.id, "failed")
    nxt = outcome.next
    assert (nxt.title, nxt.status, nxt.project_id, nxt.allocated_budget) == (
        "Water the plants", "todo", project.id, Decimal("15.00"))
    changes = [(e["change"], e["task_id"]) for e in await events.since(user_id, 0) if e["type"] == "tasks_changed"]
    assert changes == [("created", task.id), ("failed", task.id), ("created", nxt.id)]
    assert await service.fail(user_id, task.id) is None


async def test_a_failed_one_off_task_does_not_come_back(cfg, store, user_id):
    service = TaskService(store, EventHub(cfg))
    task = await service.add(user_id, TaskDraft(title="Call the plumber"))
    assert (await service.fail(user_id, task.id)).next is None
    assert [t.title for t in await service.list(user_id, status="failed")] == ["Call the plumber"]
    assert await service.list(user_id) == ()


async def test_a_recurring_task_whose_project_is_gone_comes_back_without_it(cfg, store, user_id, caplog):
    """The project is deleted between the fail and the respawn, so H9 had no
    chance to unlink the task: the next occurrence is still made, unlinked."""
    service = TaskService(store, EventHub(cfg))
    project = await _project(cfg, user_id)
    task = await service.add(user_id, TaskDraft(title="Sweep the yard", due_date="2026-10-12",
                                                recurring="0 9 * * 1", project_id=project.id,
                                                allocated_budget=Decimal("5")))
    async with db_session(cfg) as db:
        await db.execute("UPDATE money_projects SET deleted_at = ? WHERE id = ?",
                         (datetime.now(timezone.utc).isoformat(), project.id))
        await db.commit()
    with caplog.at_level(logging.WARNING, logger="roost.tasks.service"):
        outcome = await service.fail(user_id, task.id)
    assert outcome.done.status == "failed"
    assert (outcome.next.title, outcome.next.project_id, outcome.next.allocated_budget) == ("Sweep the yard", None, None)
    assert any(task.id in record.getMessage() and "comes back without it" in record.getMessage()
               for record in caplog.records)


async def test_the_service_lists_one_projects_tasks(cfg, store, user_id):
    service = TaskService(store, EventHub(cfg))
    house = await _project(cfg, user_id)
    await service.add(user_id, TaskDraft(title="Paint", project_id=house.id))
    await service.add(user_id, TaskDraft(title="Dentist"))
    assert [t.title for t in await service.list(user_id, project_id=house.id)] == ["Paint"]
    assert len(await service.list(user_id)) == 2


async def test_respawn_keeps_the_project_and_the_slice_even_without_one(cfg, store, user_id):
    project = await _project(cfg, user_id)
    linked = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("20"))
    draft = respawn_draft(linked, "2026-10-19", None)
    assert (draft.project_id, draft.allocated_budget) == (project.id, Decimal("20.00"))
    unlinked = respawn_draft(replace(linked, project_id=None), "2026-10-19", None)
    assert (unlinked.project_id, unlinked.allocated_budget) == (None, Decimal("20.00"))


async def test_a_failed_task_has_its_own_mark_and_the_board_shape_carries_the_project(cfg, store, user_id):
    project = await _project(cfg, user_id)
    task = await _task(store, user_id, project_id=project.id, allocated_budget=Decimal("250"))
    failed = await store.fail(user_id, task.id)
    assert task_line(failed).startswith("[✗] - Paint the hall ")
    out = task_out(failed)
    assert (out["status"], out["project_id"], out["allocated_budget"]) == ("failed", project.id, "250.00")
    plain = task_out(await _task(store, user_id, "Dentist"))
    assert (plain["project_id"], plain["allocated_budget"]) == (None, None)
