"""TaskStore — the user's encrypted tasks (M1 D2, D6)."""

from __future__ import annotations

import asyncio

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.service import TaskService
from roost.tasks.store import TaskStore
from team_helpers import make_bot


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


async def test_user_content_is_ciphertext_on_disk(cfg, store, user_id):
    task = await store.create(user_id, TaskDraft(title="Call the dentist", category="Health", tags=("teeth",),
                                                 steps=("find the number",)), created_by_bot=None, tainted=False)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT title, category, tags, steps FROM tasks WHERE id = ?", (task.id,))).fetchone()
    assert all(value.startswith("enc:v2:") for value in row)
    assert "dentist" not in row["title"]
    again = await store.get(user_id, task.id)
    assert (again.title, again.category, again.tags, again.steps[0].title) == ("Call the dentist", "Health", ("teeth",), "find the number")


async def test_another_user_sees_nothing(cfg, store, user_id):
    task = await store.create(user_id, TaskDraft(title="mine"), created_by_bot=None, tainted=False)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.get(bob, task.id) is None
    assert await store.list(bob) == ()
    assert await store.update(bob, task.id, TaskPatch({"title": "x"})) is None
    assert await store.delete(bob, task.id) is False


async def test_open_tasks_come_by_priority_then_due(store, user_id):
    for title, priority, due in (("later", "medium", "2026-12-01"), ("soon", "medium", "2026-11-01"),
                                 ("urgent", "urgent", None), ("someday", "medium", None)):
        await store.create(user_id, TaskDraft(title=title, priority=priority, due_date=due), created_by_bot=None, tainted=False)
    assert [t.title for t in await store.list(user_id)] == ["urgent", "soon", "later", "someday"]


async def test_update_can_clear_a_due_date(store, user_id):
    task = await store.create(user_id, TaskDraft(title="t", due_date="2026-11-01"), created_by_bot=None, tainted=False)
    updated = await store.update(user_id, task.id, TaskPatch({"due_date": None, "priority": "high"}))
    assert (updated.due_date, updated.priority) == (None, "high")


async def test_a_patch_with_an_unknown_field_is_refused():
    with pytest.raises(ValueError, match="no field"):
        TaskPatch({"owner_id": "x"})


@pytest.mark.parametrize("field", ("title", "priority", "status"))
async def test_a_patch_cannot_null_a_not_null_field(field):
    """Fix round 1 (Important #2): ``title``/``priority``/``status`` are
    NOT NULL columns; a patch clearing one must be refused here — the one
    gate both the HTTP route and the tool call go through — instead of
    reaching sqlite as an uncaught IntegrityError."""
    with pytest.raises(ValueError, match="cannot be cleared"):
        TaskPatch({field: None})


async def test_concurrent_completes_of_a_recurring_task_respawn_only_once(cfg, store, user_id):
    """Fix round 1 (Important #1): store.complete()'s UPDATE is now a
    compare-and-set on the status it read (``AND status IN (...)``), so two
    callers racing to complete the same task can't both see it as open —
    exactly one Completion, exactly one respawned occurrence. Before the
    fix this produced 2 completions and 2 open next-occurrences."""
    service = TaskService(store, EventHub(cfg))
    task = await store.create(user_id, TaskDraft(title="Water the plants", due_date="2026-10-12",
                                                 recurring="0 9 * * 1"), created_by_bot=None, tainted=False)
    first, second = await asyncio.gather(service.complete(user_id, task.id), service.complete(user_id, task.id))
    completions = [c for c in (first, second) if c is not None]
    assert len(completions) == 1
    assert len(await store.list(user_id, status="done")) == 1
    assert len(await store.list(user_id, status="open")) == 1


async def test_concurrent_complete_and_update_do_not_clobber_each_other(cfg, store, user_id):
    """Fix round 1 (Important #1, second half): ``update`` now writes only
    the columns its own patch touches, so a racing ``update_task`` (e.g. a
    bot changing the category) can no longer carry a stale ``status``/
    ``completed_at`` back over a concurrent complete."""
    task = await store.create(user_id, TaskDraft(title="t"), created_by_bot=None, tainted=False)
    await asyncio.gather(store.complete(user_id, task.id), store.update(user_id, task.id, TaskPatch({"category": "life"})))
    after = await store.get(user_id, task.id)
    assert (after.status, after.category) == ("done", "life")
    assert after.completed_at is not None


async def test_complete_marks_done_once_and_delete_is_soft(cfg, store, user_id):
    task = await store.create(user_id, TaskDraft(title="t", steps=("a",)), created_by_bot=None, tainted=False)
    done = await store.complete(user_id, task.id)
    assert (done.status, done.steps[0].done) == ("done", True) and done.completed_at
    assert await store.complete(user_id, task.id) is None           # already done
    assert [t.id for t in await store.list(user_id, status="done")] == [task.id]
    assert await store.delete(user_id, task.id) is True
    assert await store.list(user_id, status="all") == ()
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT deleted_at FROM tasks WHERE id = ?", (task.id,))).fetchone()
    assert row["deleted_at"] is not None


async def test_retiring_the_creating_bot_keeps_the_task(cfg, store, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    task = await store.create(user_id, TaskDraft(title="t"), created_by_bot=bot.id, tainted=True)
    await BotStore(cfg).delete(user_id, bot.id)
    kept = await store.get(user_id, task.id)
    assert (kept.created_by_bot, kept.tainted) == (None, True)
