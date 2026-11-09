"""The end-of-day summary: never seeded on its own any more (the owner, 2026-10-21: "If I ask, I ask"). A row that
already exists stays an ordinary routine: posted with no model run while on, and deletable like any other."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from roost.routines.models import RoutineDraft
from roost.routines.schedule import parse_schedule
from roost.routines.scheduler import RoutineScheduler
from roost.routines.store import DAY_SUMMARY_BUILTIN, DAY_SUMMARY_NAME
from roost.routines.system_reports import jobs_for_parts
from roost.tasks.models import TaskDraft
from sys_report_helpers import FakeClock, make_rig
from team_helpers import make_rig as make_runner_rig, team_model

UTC = timezone.utc
EVENING = datetime(2026, 10, 21, 19, 5, tzinfo=UTC)      # 21:05 in Madrid


@pytest.fixture
async def rig():
    return await make_rig()


def _jobs(rig):
    return jobs_for_parts(rig.deps, rig.routines, rig.tasks, rig.expenses)


async def _existing(rig, routines=None):
    """A day summary row from before the change: an ordinary routine now."""
    store = routines or rig.routines
    return await store.create(rig.user_id, RoutineDraft(
        bot_id=rig.main.id, name=DAY_SUMMARY_NAME, instructions="", created_by="user",
        schedule=parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["21:00"]}),
        builtin=DAY_SUMMARY_BUILTIN, enabled=False))


async def test_no_job_seeds_a_day_summary(rig):
    for job in _jobs(rig):
        await job.run(rig.user_id, EVENING)

    assert await rig.routines.builtin_for(rig.user_id, rig.main.id, DAY_SUMMARY_BUILTIN) is None
    assert await rig.count("routines") == 0


def test_the_scheduler_runs_no_budget_alert_job(rig):
    names = {job.name for job in _jobs(rig)}
    assert names == {"day_summary", "reminders"}


async def test_the_day_summary_posts_when_on(rig):
    await rig.tasks.create(rig.user_id, TaskDraft(title="Send invoice", due_date="2026-10-20"),
                           created_by_bot=None, tainted=False)
    clock = FakeClock(EVENING - timedelta(hours=3))
    routines = type(rig.routines)(rig.cfg, rig.talk, clock=clock)
    routine = await _existing(rig, routines)
    await routines.set_enabled(rig.user_id, routine.id, True)

    runner_rig = make_runner_rig(rig.cfg, team_model({}))
    scheduler = RoutineScheduler(
        rig.cfg, clock=clock, launcher=None, runs=rig.runs, routines=routines, turns=runner_rig.runner,
        bots=rig.bots, jobs=_jobs(rig))
    clock.now = EVENING
    await scheduler.tick()
    await scheduler.tick()                                    # the same slot never posts twice

    sent = await rig.reports(rig.main)
    assert [r.headline for r in sent] == ["Your day, 2026-10-21"]
    assert sent[0].source == "day_summary" and "Send invoice" in sent[0].text
    runs = await rig.runs.list_for_routine(rig.user_id, routine.id)
    assert [r.state for r in runs] == ["done"]
    assert (await routines.get(rig.user_id, routine.id)).next_run_at > EVENING


async def test_a_switched_off_summary_posts_nothing(rig):
    await _existing(rig)
    clock = FakeClock(EVENING)
    runner_rig = make_runner_rig(rig.cfg, team_model({}))
    scheduler = RoutineScheduler(
        rig.cfg, clock=clock, launcher=None, runs=rig.runs, routines=rig.routines, turns=runner_rig.runner,
        bots=rig.bots, jobs=_jobs(rig))
    await scheduler.tick()
    assert await rig.reports(rig.main) == ()


async def test_spending_past_a_budget_posts_no_report_on_a_tick(rig):
    from decimal import Decimal

    from roost.money.models import ExpenseDraft, ProjectDraft
    project = await rig.projects.create(rig.user_id, ProjectDraft(name="Casa", monthly_budget=Decimal("100")))
    await rig.expenses.add(rig.user_id, ExpenseDraft(project.id, Decimal("150"), spent_at="2026-10-15"),
                           created_by_bot=None, tainted=False)
    runner_rig = make_runner_rig(rig.cfg, team_model({}))
    scheduler = RoutineScheduler(
        rig.cfg, clock=FakeClock(EVENING), launcher=None, runs=rig.runs, routines=rig.routines,
        turns=runner_rig.runner, bots=rig.bots, jobs=_jobs(rig))

    await scheduler.tick()

    assert await rig.reports(rig.main) == ()
    assert await rig.count("budget_alerts") == 0


async def test_an_existing_day_summary_can_be_deleted(rig):
    from roost.routines.runs import RoutineRunStore
    from roost.routines.service import RoutineService
    routine = await _existing(rig)
    service = RoutineService(rig.routines, RoutineRunStore(rig.cfg), rig.bots, rig.talk, rig.events, None, None)

    await service.delete(rig.user_id, routine.id)

    assert await rig.routines.get(rig.user_id, routine.id) is None
