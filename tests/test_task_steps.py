"""A task's checklist, one change at a time (redesign P3): stable ids, compare-and-set writes, and a
deleted step's money and comments stay on its task."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.constants import MAX_TASK_STEPS, STEP_WRITE_ATTEMPTS
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.projects.numbers import task_money
from roost.tasks.comment_store import CommentStore
from roost.tasks.models import Step, TaskDraft
from roost.tasks.step_service import StepService
from roost.tasks.steps import (
    STEP_TITLE_TEXT, TOO_MANY_STEPS_TEXT, StepNotFound, with_step_added, with_step_done, with_step_moved,
    with_step_renamed, without_step,
)
from roost.tasks.store import STEPS_BUSY_TEXT, StepsBusy, TaskStore

A, B, C = (Step(id=f"s-{name}", title=name, done=False) for name in ("a", "b", "c"))


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _service(cfg, store: TaskStore | None = None) -> StepService:
    return StepService(store or TaskStore(cfg), ExpenseStore(cfg), CommentStore(cfg), EventHub(cfg))


async def _task(cfg, user_id: str, steps: tuple[str, ...] = ("Buy a washer", "Fit it")):
    return await TaskStore(cfg).create(user_id, TaskDraft(title="Fix the sink", steps=steps),
                                       created_by_bot=None, tainted=False)


def _frames(cfg) -> list[str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return [row[0] for row in con.execute("SELECT kind FROM events ORDER BY seq")]
    finally:
        con.close()


def test_adding_gives_a_fresh_id_and_keeps_the_others():
    added = with_step_added((A, B), "  Call the plumber  ")
    assert [step.title for step in added] == ["a", "b", "Call the plumber"]
    assert added[:2] == (A, B) and added[2].id not in {A.id, B.id} and added[2].done is False
    with pytest.raises(ValueError, match=STEP_TITLE_TEXT):
        with_step_added((A,), "   ")
    full = tuple(Step(id=f"s-{n}", title=str(n), done=False) for n in range(MAX_TASK_STEPS))
    with pytest.raises(ValueError, match=TOO_MANY_STEPS_TEXT):
        with_step_added(full, "one more")


def test_rename_tick_untick_keep_the_id():
    renamed = with_step_renamed((A, B), "s-b", "Fit the washer")
    assert (renamed[1].id, renamed[1].title) == ("s-b", "Fit the washer")
    ticked = with_step_done(renamed, "s-a", True)
    assert ticked[0].done is True and ticked[0].completed_at is not None
    unticked = with_step_done(ticked, "s-a", False)
    assert (unticked[0].done, unticked[0].completed_at, unticked[0].id) == (False, None, "s-a")
    assert with_step_done((A,), "s-a", False) == (A,)


@pytest.mark.parametrize(("step_id", "position", "order"), [
    ("s-c", 0, ["c", "a", "b"]),
    ("s-a", 2, ["b", "c", "a"]),
    ("s-a", 99, ["b", "c", "a"]),
    ("s-c", -5, ["c", "a", "b"]),
    ("s-b", 1, ["a", "b", "c"]),
])
def test_moving_puts_the_step_at_its_place_and_clamps_past_either_end(step_id, position, order):
    assert [step.title for step in with_step_moved((A, B, C), step_id, position)] == order


@pytest.mark.parametrize("change", [
    lambda steps: with_step_renamed(steps, "s-x", "y"), lambda steps: with_step_done(steps, "s-x", True),
    lambda steps: with_step_moved(steps, "s-x", 0), lambda steps: without_step(steps, "s-x"),
])
def test_an_unknown_step_is_not_found(change):
    with pytest.raises(StepNotFound):
        change((A, B))


async def test_each_change_is_stored_encrypted_and_published(cfg, user_id):
    task = await _task(cfg, user_id)
    service = _service(cfg)
    added = await service.add(user_id, task.id, "Test for leaks")
    new_id = added.steps[-1].id
    await service.set_done(user_id, task.id, new_id, True)
    await service.move(user_id, task.id, new_id, 0)
    await service.rename(user_id, task.id, new_id, "Test for leaks twice")
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [
        ("Test for leaks twice", True), ("Buy a washer", False), ("Fit it", False)]
    assert stored.steps[0].id == new_id
    assert _frames(cfg)[-4:] == ["tasks_changed"] * 4


async def test_two_step_changes_at_once_both_land(cfg, user_id):
    """Review Focus 1: a bot ticks one step while the user renames another; neither change is lost."""
    task = await _task(cfg, user_id)
    first, second = task.steps
    racer = _service(cfg)

    class RacingStore(TaskStore):
        raced = False

        async def get(self, user_id, task_id):
            found = await super().get(user_id, task_id)
            if not RacingStore.raced:
                RacingStore.raced = True
                await racer.set_done(user_id, task_id, second.id, True)    # lands between this read and its write
            return found

    renamed = await _service(cfg, RacingStore(cfg)).rename(user_id, task.id, first.id, "Buy two washers")
    assert [(step.title, step.done) for step in renamed.steps] == [("Buy two washers", False), ("Fit it", True)]
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert stored.steps == renamed.steps


async def test_a_change_that_keeps_losing_the_race_says_try_again(cfg, user_id):
    task = await _task(cfg, user_id)
    racer = TaskStore(cfg)
    calls = []

    class AlwaysRaced(TaskStore):
        async def get(self, user_id, task_id):
            found = await super().get(user_id, task_id)
            calls.append(1)
            await racer.edit_steps(user_id, task_id, lambda steps: steps)    # bumps updated_at every time
            return found

    with pytest.raises(StepsBusy, match=STEPS_BUSY_TEXT):
        await _service(cfg, AlwaysRaced(cfg)).rename(user_id, task.id, task.steps[0].id, "x")
    assert len(calls) == STEP_WRITE_ATTEMPTS


async def test_a_step_added_by_a_tainted_run_marks_the_task(cfg, user_id):
    task = await _task(cfg, user_id)
    added = await _service(cfg).add(user_id, task.id, "Order the gadget", tainted=True)
    assert added.tainted is True
    assert (await TaskStore(cfg).get(user_id, task.id)).tainted is True


async def test_another_users_or_a_deleted_task_is_none(cfg, user_id):
    task = await _task(cfg, user_id)
    other = (await register_user(cfg, "bob", "pw-123456")).id
    service = _service(cfg)
    assert await service.add(other, task.id, "Sneaky") is None
    assert await service.delete(other, task.id, task.steps[0].id) is None
    await TaskStore(cfg).delete(user_id, task.id)
    assert await service.set_done(user_id, task.id, task.steps[0].id, True) is None


async def test_deleting_a_step_keeps_its_money_and_comments_on_the_task(cfg, user_id):
    """Review Focus 2: the expense and the comment filed under the step stay on the task, and the
    task's spent is the same before and after."""
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Home"), created_by_bot=None, tainted=False)
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Fix the sink", steps=("Buy a washer",),
                                                          project_id=project.id, allocated_budget=Decimal("50")),
                                       created_by_bot=None, tainted=False)
    step = task.steps[0]
    expenses = ExpenseStore(cfg)
    spent = await expenses.add(user_id, ExpenseDraft(project.id, Decimal("12.50"), spent_at=today_madrid(),
                                                     task_id=task.id, step_id=step.id),
                               created_by_bot=None, tainted=False)
    await CommentStore(cfg).add(user_id, task.id, step_id=step.id, author="user", body="15 mm", tainted=False)
    before = task_money(task, await expenses.for_tasks(user_id, [task.id]), project.currency)

    removal = await _service(cfg).delete(user_id, task.id, step.id)

    assert removal.task.steps == () and removal.moved_expenses == (spent.id,) and removal.moved_comments == 1
    [moved] = await expenses.for_tasks(user_id, [task.id])
    assert (moved.task_id, moved.step_id) == (task.id, None)
    [comment] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert comment.step_id is None
    after = task_money(removal.task, (moved,), project.currency)
    assert after == before
    assert _frames(cfg)[-2:] == ["tasks_changed", "money_changed"]
