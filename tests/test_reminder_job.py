"""Reminders fire as Reports: once per fire time, advance ones before, late ones as one Report."""

from __future__ import annotations

from datetime import timedelta

import pytest

from roost.routines.system_reports import ReminderJob
from roost.tasks.models import TaskDraft, TaskPatch
from sys_report_helpers import NOW, make_rig, rig_for


@pytest.fixture
async def rig():
    return await make_rig()


def _at(minutes: float) -> str:
    return (NOW + timedelta(minutes=minutes)).isoformat()


async def _task(rig, title, minutes, *, pre=(), owner="user", by=None):
    return await rig.tasks.create(
        rig.user_id, TaskDraft(title=title, reminder_at=_at(minutes), pre_reminders=tuple(pre), owner=owner),
        created_by_bot=by, tainted=False)


async def test_a_reminder_fires_once_at_its_time(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    await _task(rig, "Call Ana", 30)

    await job.run(rig.user_id, NOW)
    assert await rig.reports(rig.main) == ()           # not yet

    later = NOW + timedelta(minutes=31)
    await job.run(rig.user_id, later)
    await job.run(rig.user_id, later + timedelta(minutes=1))
    sent = await rig.reports(rig.main)
    assert [r.headline for r in sent] == ["Reminder: Call Ana"]
    assert sent[0].source == "reminder" and "Madrid" not in sent[0].text


async def test_advance_reminders_fire_before_it(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    await _task(rig, "Dentist", 60, pre=(_at(30), "-45m"))      # an instant and an offset

    await job.run(rig.user_id, NOW + timedelta(minutes=20))     # 08:20: the -45m one (08:15)
    assert len(await rig.reports(rig.main)) == 1
    await job.run(rig.user_id, NOW + timedelta(minutes=35))     # 08:35: the 08:30 one
    assert len(await rig.reports(rig.main)) == 2
    await job.run(rig.user_id, NOW + timedelta(minutes=61))     # 09:01: the reminder itself
    assert len(await rig.reports(rig.main)) == 3
    assert await rig.count("reminder_sends") == 3


async def test_a_changed_reminder_fires_again(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    task = await _task(rig, "Pay rent", -5)
    await job.run(rig.user_id, NOW)
    assert len(await rig.reports(rig.main)) == 1

    await rig.tasks.update(rig.user_id, task.id, TaskPatch({"reminder_at": _at(-1)}))
    await job.run(rig.user_id, NOW)
    await job.run(rig.user_id, NOW)
    assert len(await rig.reports(rig.main)) == 2


async def test_done_and_deleted_tasks_never_remind(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    done = await _task(rig, "Done one", -5)
    gone = await _task(rig, "Gone one", -5)
    await rig.tasks.complete(rig.user_id, done.id)
    await rig.tasks.delete(rig.user_id, gone.id)

    await job.run(rig.user_id, NOW)
    assert await rig.reports(rig.main) == ()
    assert await rig.count("reminder_sends") == 0


async def test_reminders_missed_while_off_come_as_one_report(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    await _task(rig, "Old one", -600)         # 10 h late
    await _task(rig, "Older one", -480)       # 8 h late
    await _task(rig, "Fresh one", -5)

    await job.run(rig.user_id, NOW)

    sent = await rig.reports(rig.main)
    assert sorted(r.headline for r in sent) == ["Reminder: Fresh one", "While Roost was off, reminders passed"]
    combined = next(r for r in sent if r.headline.startswith("While"))
    assert "Old one" in combined.text and "Older one" in combined.text
    assert await rig.count("reminder_sends", missed="1") == 2


async def test_an_assigned_task_reminds_through_its_bot(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    from team_helpers import make_bot
    scout = await make_bot(rig.cfg, rig.user_id, "Scout")
    await _task(rig, "Scout it", -5, owner=scout.id)
    await _task(rig, "Retired owner", -5, owner="00000000-0000-0000-0000-000000000000")

    await job.run(rig.user_id, NOW)

    assert [r.headline for r in await rig.reports(scout)] == ["Reminder: Scout it"]
    assert [r.headline for r in await rig.reports(rig.main)] == ["Reminder: Retired owner"]


async def test_a_task_a_bot_made_reminds_through_that_bot(rig):
    """Owner, 2026-10-26: Gela made "Go to sleep" but Chief, the main bot, sent its reminder."""
    job = ReminderJob(rig.deps, rig.tasks)
    from team_helpers import make_bot
    gela = await make_bot(rig.cfg, rig.user_id, "Gela")
    scout = await make_bot(rig.cfg, rig.user_id, "Scout")
    await _task(rig, "Go to sleep", -5, by=gela.id)
    await _task(rig, "Assigned wins", -5, owner=scout.id, by=gela.id)
    await _task(rig, "Nobody made it", -5)

    await job.run(rig.user_id, NOW)

    assert [r.headline for r in await rig.reports(gela)] == ["Reminder: Go to sleep"]
    assert [r.headline for r in await rig.reports(scout)] == ["Reminder: Assigned wins"]
    assert [r.headline for r in await rig.reports(rig.main)] == ["Reminder: Nobody made it"]


async def test_a_reminder_carries_its_task_for_the_card_buttons(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    task = await _task(rig, "Buy milk", -5)
    await job.run(rig.user_id, NOW)
    [report] = await rig.reports(rig.main)
    assert report.task_id == task.id


async def test_reminders_are_scoped_by_user(rig):
    bob = await rig_for(rig.cfg, "bob")
    job = ReminderJob(rig.deps, rig.tasks)
    await bob.tasks.create(bob.user_id, TaskDraft(title="Bob's", reminder_at=_at(-5)), created_by_bot=None,
                           tainted=False)

    await job.run(rig.user_id, NOW)
    assert await bob.reports(bob.main) == () and await rig.reports(rig.main) == ()

    await job.run(bob.user_id, NOW)
    assert [r.headline for r in await bob.reports(bob.main)] == ["Reminder: Bob's"]
    assert await rig.reports(rig.main) == ()


async def test_a_tick_sends_at_most_the_cap(rig, monkeypatch):
    import roost.routines.system_reports as module
    monkeypatch.setattr(module, "REMINDERS_PER_TICK_MAX", 2)
    job = ReminderJob(rig.deps, rig.tasks)
    for n in range(4):
        await _task(rig, f"T{n}", -5)

    await job.run(rig.user_id, NOW)
    assert await rig.count("reminder_sends") == 2
    await job.run(rig.user_id, NOW)
    assert await rig.count("reminder_sends") == 4


async def test_a_reminder_report_names_its_task_so_the_chat_can_draw_its_card(rig):
    """Owner, 2026-10-26: a reminder is a card with Done · Failed · Reschedule · Skip, so it carries its task id;
    the missed-reminders summary names several tasks and carries none."""
    job = ReminderJob(rig.deps, rig.tasks)
    task = await _task(rig, "Call Ana", -5)
    await _task(rig, "Old one", -600)
    await job.run(rig.user_id, NOW)
    sent = await rig.reports(rig.main)
    single = next(r for r in sent if r.headline == "Reminder: Call Ana")
    missed = next(r for r in sent if r.headline.startswith("While"))
    assert (single.task_id, missed.task_id) == (task.id, None)


async def test_a_reminder_reads_like_a_friendly_chat_message(rig):
    """Owner, 2026-10-26 ("like Grok"): "Quick reminder: … is due today." and its kin, no "· reminder for"."""
    job = ReminderJob(rig.deps, rig.tasks)
    task = await rig.tasks.create(
        rig.user_id, TaskDraft(title="Reply to Jin Hu", reminder_at=_at(-5), due_date="2026-10-21T18:00"),
        created_by_bot=None, tainted=False)
    await job.run(rig.user_id, NOW)
    [report] = await rig.reports(rig.main)
    assert report.text == "Quick reminder: Reply to Jin Hu is due today at 18:00."
    assert report.task_title == "Reply to Jin Hu" and report.task_id == task.id


async def test_advance_and_on_time_reminders_are_worded_by_which_they_are(rig):
    job = ReminderJob(rig.deps, rig.tasks)
    await _task(rig, "Dentist", 120, pre=("-2h",))
    await job.run(rig.user_id, NOW)                              # 10:00: the -2h one
    await job.run(rig.user_id, NOW + timedelta(minutes=121))     # 12:01: the reminder itself
    texts = [r.text for r in await rig.reports(rig.main)]
    assert sorted(texts) == ["Heads-up: Dentist is in 2 h.", "It's time: Dentist (12:00)."]
