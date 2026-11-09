"""The end-of-day summary's content (projects hub, H13). For one Madrid day it
holds the tasks closed that day (done and failed), the open tasks already
overdue, and that day's counted expenses per currency, plus its text. Nothing
sends it yet; the scheduler (part 2) will."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ExpensePatch, ProjectDraft
from roost.money.project_store import ProjectStore
from roost.tasks.day_summary import DaySummary, build_day_summary, day_summary_text, madrid_day_bounds_utc
from roost.tasks.format import task_line
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.store import TaskStore

_NOON_MADRID = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)      # 12:00 on 2026-10-14 in Madrid (CEST)


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


async def _task(store, user_id, title, **fields):
    return await store.create(user_id, TaskDraft(title=title, **fields), created_by_bot=None, tainted=False)


async def _closed(cfg, store, user_id, title, how, at):
    """A task closed by ``complete`` or ``fail``, with ``completed_at`` moved to ``at``."""
    task = await _task(store, user_id, title)
    closed = await (store.fail if how == "fail" else store.complete)(user_id, task.id)
    async with db_session(cfg) as db:
        await db.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (at, task.id))
        await db.commit()
    return closed


async def _spend(expenses, user_id, project_id, amount, currency, day):
    draft = ExpenseDraft(project_id=project_id, amount=Decimal(amount), currency=currency, spent_at=day)
    return await expenses.add(user_id, draft, created_by_bot=None, tainted=False)


async def _summary(cfg, store, user_id, day="2026-10-14", now=_NOON_MADRID):
    return await build_day_summary(user_id, day, tasks=store, expenses=ExpenseStore(cfg), now=now)


@pytest.mark.parametrize(("day", "bounds"), (
    ("2026-10-14", ("2026-10-13T22:00:00+00:00", "2026-10-14T22:00:00+00:00")),   # summer time, UTC+2
    ("2026-12-01", ("2026-11-30T23:00:00+00:00", "2026-12-01T23:00:00+00:00")),   # winter time, UTC+1
    ("2026-10-25", ("2026-10-24T22:00:00+00:00", "2026-10-25T23:00:00+00:00")),   # clocks go back: 25 hours
    ("2026-03-29", ("2026-03-28T23:00:00+00:00", "2026-03-29T22:00:00+00:00")),   # clocks go forward: 23 hours
))
def test_a_madrid_day_runs_from_midnight_to_midnight_in_utc(day, bounds):
    assert madrid_day_bounds_utc(day) == bounds


@pytest.mark.parametrize("day", ("2026-13-01", "2026-02-30", "14/10/2026", "20261014", "", "2026-10-14T00:00"))
def test_a_day_that_is_not_a_date_is_refused(day):
    with pytest.raises(ValueError, match="is not a day like 2026-10-14"):
        madrid_day_bounds_utc(day)


async def test_the_summary_has_the_tasks_closed_that_madrid_day(cfg, store, user_id):
    # 2026-10-25 is 25 hours long in Madrid: 2026-10-24T22:00Z up to 2026-10-25T23:00Z.
    await _closed(cfg, store, user_id, "Too early", "complete", "2026-10-24T21:59:00+00:00")      # 23:59 on the 24th
    await _closed(cfg, store, user_id, "Fixed the tap", "complete", "2026-10-24T22:00:00+00:00")  # 00:00 on the 25th
    await _closed(cfg, store, user_id, "Ran out of tiles", "fail", "2026-10-25T01:30:00+00:00")   # 02:30, the repeated hour
    await _closed(cfg, store, user_id, "Paid the builder", "complete", "2026-10-25T22:59:59.999999+00:00")
    await _closed(cfg, store, user_id, "Too late", "fail", "2026-10-25T23:00:00+00:00")           # 00:00 on the 26th
    summary = await _summary(cfg, store, user_id, "2026-10-25", datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc))
    assert summary.day == "2026-10-25"
    assert [t.title for t in summary.done] == ["Fixed the tap", "Paid the builder"]
    assert [t.title for t in summary.failed] == ["Ran out of tiles"]


async def test_overdue_is_an_open_task_past_its_madrid_day_or_its_time(cfg, store, user_id):
    for title, due in (("Yesterday", "2026-10-13"), ("Today", "2026-10-14"), ("Tomorrow", "2026-10-15"),
                       ("Earlier today", "2026-10-14T11:00:00+02:00"), ("Later today", "2026-10-14T13:00:00+02:00"),
                       ("Earlier, no offset", "2026-10-14T11:00:00"), ("No due", None)):
        await _task(store, user_id, title, due_date=due)
    started = await _task(store, user_id, "Started last week", due_date="2026-10-07")
    await store.update(user_id, started.id, TaskPatch({"status": "in_progress"}))
    for title, close in (("Done late", store.complete), ("Failed late", store.fail)):
        task = await _task(store, user_id, title, due_date="2026-10-01")
        await close(user_id, task.id)
    cancelled = await _task(store, user_id, "Cancelled", due_date="2026-10-01")
    await store.update(user_id, cancelled.id, TaskPatch({"status": "cancelled"}))
    summary = await _summary(cfg, store, user_id)
    assert {t.title for t in summary.overdue} == {"Yesterday", "Earlier today", "Earlier, no offset", "Started last week"}


async def test_a_date_only_due_is_overdue_from_madrid_midnight(cfg, store, user_id):
    await _task(store, user_id, "Renew the parking permit", due_date="2026-10-13")
    just_before = datetime(2026, 10, 13, 21, 59, tzinfo=timezone.utc)    # 23:59 on the 13th in Madrid
    just_after = datetime(2026, 10, 13, 22, 1, tzinfo=timezone.utc)      # 00:01 on the 14th; UTC is still the 13th
    before = await _summary(cfg, store, user_id, "2026-10-13", just_before)
    after = await _summary(cfg, store, user_id, "2026-10-14", just_after)
    assert before.overdue == ()
    assert [t.title for t in after.overdue] == ["Renew the parking permit"]


async def test_an_unreadable_due_is_left_out_of_overdue_and_logged(cfg, store, user_id, caplog):
    odd = await _task(store, user_id, "Odd one", due_date="when the shop opens")
    short = await _task(store, user_id, "Short one", due_date="next week")    # 9 characters, not a date
    tenth = await _task(store, user_id, "Tenth one", due_date="2026-1x-01")   # 10 characters, not a date
    with caplog.at_level(logging.WARNING, logger="roost.tasks.day_summary"):
        summary = await _summary(cfg, store, user_id)
    assert summary.overdue == ()
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert all(task.id in logged for task in (odd, short, tenth)) and "unreadable due date" in logged


async def test_spent_is_the_days_counted_expenses_per_currency(cfg, store, user_id):
    projects, expenses = ProjectStore(cfg), ExpenseStore(cfg)
    house = await projects.create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None, tainted=False)
    await _spend(expenses, user_id, house.id, "12.50", "EUR", "2026-10-14")
    await _spend(expenses, user_id, house.id, "7.50", "EUR", "2026-10-14")
    await _spend(expenses, user_id, house.id, "3", "USD", "2026-10-14")
    await _spend(expenses, user_id, house.id, "100", "EUR", "2026-10-13")             # the day before
    voided = await _spend(expenses, user_id, house.id, "5", "EUR", "2026-10-14")
    deleted = await _spend(expenses, user_id, house.id, "9", "EUR", "2026-10-14")
    assert (await expenses.update(user_id, voided.id, ExpensePatch({"status": "void"}))).status == "void"
    assert await expenses.delete(user_id, deleted.id) is True
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    garage = await projects.create(bob, ProjectDraft(name="Garage"), created_by_bot=None, tainted=False)
    await _spend(expenses, bob, garage.id, "40", "EUR", "2026-10-14")
    summary = await _summary(cfg, store, user_id)
    assert dict(summary.spent) == {"EUR": Decimal("20.00"), "USD": Decimal("3.00")}
    assert list(summary.spent) == ["EUR", "USD"]
    assert isinstance(summary.spent, MappingProxyType)


async def test_another_users_tasks_stay_out_of_the_summary(cfg, store, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await _closed(cfg, store, bob, "Bob's tap", "complete", "2026-10-14T08:00:00+00:00")
    await _closed(cfg, store, bob, "Bob's tiles", "fail", "2026-10-14T09:00:00+00:00")
    await _task(store, bob, "Bob's late call", due_date="2026-10-01")
    summary = await _summary(cfg, store, user_id)
    assert (summary.done, summary.failed, summary.overdue, dict(summary.spent)) == ((), (), (), {})


async def test_a_quiet_day_has_an_empty_summary(cfg, store, user_id):
    summary = await build_day_summary(user_id, "2026-10-14", tasks=store, expenses=ExpenseStore(cfg))
    assert (summary.day, summary.done, summary.failed, summary.overdue, dict(summary.spent)) == (
        "2026-10-14", (), (), (), {})


async def test_the_summary_time_must_carry_a_time_zone(cfg, store, user_id):
    with pytest.raises(ValueError, match="time zone"):
        await _summary(cfg, store, user_id, now=datetime(2026, 10, 14, 12, 0))


async def test_the_text_lists_done_failed_overdue_and_spent(cfg, store, user_id):
    done = await _closed(cfg, store, user_id, "Fixed the tap", "complete", "2026-10-14T08:00:00+00:00")
    failed = await _closed(cfg, store, user_id, "Ran out of tiles", "fail", "2026-10-14T09:00:00+00:00")
    late = await _task(store, user_id, "Call the plumber", due_date="2026-10-10")
    summary = DaySummary(day="2026-10-14", done=(done,), failed=(failed,), overdue=(late,),
                         spent=MappingProxyType({"EUR": Decimal("20"), "USD": Decimal("3.5")}))
    assert day_summary_text(summary).splitlines() == [
        "Your day, 2026-10-14",
        "Done (1):", task_line(done),
        "Failed (1):", task_line(failed),
        "Overdue (1):", task_line(late),
        "Spent: 20.00 EUR, 3.50 USD",
    ]
    assert task_line(failed).startswith("[✗] - Ran out of tiles")


async def test_a_part_with_nothing_in_it_is_left_out(cfg, store, user_id):
    late = await _task(store, user_id, "Call the <plumber>", due_date="2026-10-10")
    summary = DaySummary(day="2026-10-14", done=(), failed=(), overdue=(late,), spent=MappingProxyType({}))
    text = day_summary_text(summary)
    assert text.splitlines() == ["Your day, 2026-10-14", "Overdue (1):", task_line(late)]
    assert "&lt;plumber&gt;" in text                     # titles are escaped by task_line


def test_an_empty_day_says_so():
    empty = DaySummary(day="2026-10-14", done=(), failed=(), overdue=(), spent=MappingProxyType({}))
    assert day_summary_text(empty) == (
        "Your day, 2026-10-14\nNothing was done or failed, nothing is overdue and nothing was spent.")
