"""Comments on a task or one of its steps (redesign P3): encrypted on disk, scoped to their user,
only the user's own can change, and every change publishes tasks_changed."""

from __future__ import annotations

import sqlite3

import pytest

from roost.config import load_config
from roost.constants import MAX_COMMENT_LENGTH
from roost.db.connection import db_session, get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.tasks.comment_service import NOT_YOURS_TEXT, CommentNotYours, CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.comments import EMPTY_COMMENT_TEXT, LONG_COMMENT_TEXT
from roost.tasks.models import STEP_NOT_FOUND_TEXT, TaskDraft
from roost.tasks.store import TaskStore


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def service(cfg):
    return CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg))


async def _task(cfg, user_id: str, title: str = "Fix the sink", steps: tuple[str, ...] = ("Buy a washer",)):
    return await TaskStore(cfg).create(user_id, TaskDraft(title=title, steps=steps), created_by_bot=None, tainted=False)


def _frames(cfg) -> list[str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


async def test_a_comment_is_ciphertext_on_disk_and_reads_back(cfg, user_id, service):
    task = await _task(cfg, user_id)
    comment = await service.add(user_id, task.id, "  The plumber comes at 9  ")
    assert (comment.body, comment.author, comment.step_id, comment.tainted) == ("The plumber comes at 9", "user", None, False)
    async with db_session(cfg) as db:
        [row] = await (await db.execute("SELECT body FROM task_comments")).fetchall()
    assert row[0].startswith("enc:v2:") and "plumber" not in row[0]
    assert [c.body for c in await service.list(user_id, task.id)] == ["The plumber comes at 9"]
    assert _frames(cfg)[-1] == "tasks_changed"


async def test_a_thread_is_oldest_first_and_keeps_the_newest_when_capped(cfg, user_id, service):
    task = await _task(cfg, user_id)
    for word in ("one", "two", "three"):
        await service.add(user_id, task.id, word)
    assert [c.body for c in await service.list(user_id, task.id)] == ["one", "two", "three"]
    assert [c.body for c in await service.list(user_id, task.id, limit=2)] == ["two", "three"]


async def test_a_comment_on_a_step_must_name_one_of_the_tasks_steps(cfg, user_id, service):
    task = await _task(cfg, user_id)
    on_step = await service.add(user_id, task.id, "Size 15 mm", step_id=task.steps[0].id)
    assert on_step.step_id == task.steps[0].id
    with pytest.raises(ValueError, match=STEP_NOT_FOUND_TEXT):
        await service.add(user_id, task.id, "x", step_id="s-nope")


@pytest.mark.parametrize(("body", "reason"), [("   ", EMPTY_COMMENT_TEXT), ("x" * (MAX_COMMENT_LENGTH + 1), LONG_COMMENT_TEXT)])
async def test_an_empty_or_long_comment_is_refused(cfg, user_id, service, body, reason):
    task = await _task(cfg, user_id)
    with pytest.raises(ValueError, match=reason):
        await service.add(user_id, task.id, body)
    assert await service.list(user_id, task.id) == ()


async def test_a_bot_comment_keeps_its_author_and_taint_and_the_user_cannot_change_it(cfg, user_id, service):
    task = await _task(cfg, user_id)
    bots = await service.add(user_id, task.id, "Found it on shop.example", author="bot-1", tainted=True)
    assert (bots.author, bots.tainted, bots.by_user) == ("bot-1", True, False)
    with pytest.raises(CommentNotYours, match=NOT_YOURS_TEXT):
        await service.edit(user_id, bots.id, "rewritten")
    with pytest.raises(CommentNotYours):
        await service.delete(user_id, bots.id)
    assert [c.body for c in await service.list(user_id, task.id)] == ["Found it on shop.example"]


async def test_the_user_edits_and_deletes_their_own_comment(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Call first")
    edited = await service.edit(user_id, mine.id, "Call first, then go")
    assert (edited.body, edited.edited_at is not None) == ("Call first, then go", True)
    assert await service.delete(user_id, mine.id) is True
    assert await service.list(user_id, task.id) == ()
    assert await service.delete(user_id, mine.id) is False
    assert await service.edit(user_id, mine.id, "back?") is None


async def test_another_users_task_and_comment_are_not_found(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Mine")
    other = (await register_user(cfg, "bob", "pw-123456")).id
    assert await service.list(other, task.id) is None
    assert await service.add(other, task.id, "Sneaky") is None
    assert await service.edit(other, mine.id, "Sneaky") is None
    assert await service.delete(other, mine.id) is False
    assert [c.body for c in await service.list(user_id, task.id)] == ["Mine"]


async def test_a_deleted_tasks_comments_are_gone_with_it(cfg, user_id, service):
    task = await _task(cfg, user_id)
    mine = await service.add(user_id, task.id, "Mine")
    await TaskStore(cfg).delete(user_id, task.id)
    assert await service.list(user_id, task.id) is None
    assert await service.add(user_id, task.id, "Late") is None
    assert await service.edit(user_id, mine.id, "Late") is None


async def test_unlinking_a_step_keeps_its_comments_on_the_task(cfg, user_id):
    task = await _task(cfg, user_id)
    store = CommentStore(cfg)
    await store.add(user_id, task.id, step_id=task.steps[0].id, author="user", body="On the step", tainted=False)
    assert await store.unlink_step(user_id, task.id, task.steps[0].id) == 1
    [comment] = await store.list(user_id, task.id, limit=10)
    assert (comment.body, comment.step_id) == ("On the step", None)
