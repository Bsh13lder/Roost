"""The launcher posts a routine's instructions in its run-log thread and queues one routine item."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import TextDelta, TurnDone
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import ReportBody, RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.routines.texts import slot_line
from roost.work.models import WorkKind
from team_helpers import make_bot, make_rig, send, team_model, wait_idle
from roost.llm.scripted_team import ScriptedTeamModel
from roost.work.models import ORIGIN_YOU, WorkDraft

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 12, 22, tzinfo=UTC)          # 14:22 in Madrid
SLOT = datetime(2026, 10, 21, 8, 7, tzinfo=UTC)           # 10:07 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07"]})


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


async def _setup(cfg, user_id, bot, *, tainted=False, model=None):
    rig = make_rig(cfg, model or team_model({}))
    store = RoutineStore(cfg, rig.talk, clock=lambda: NOW)
    routine = await store.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Morning news", instructions="Read the headlines.", schedule=SCHEDULE,
        created_by="user", tainted=tainted))
    runs = RoutineRunStore(cfg, clock=lambda: NOW)
    launcher = RoutineLauncher(rig.talk, rig.runner, runs, rig.events)
    return rig, routine, runs, launcher


async def test_launch_posts_the_instructions_and_queues_a_routine_item(cfg, user_id, bot):
    rig, routine, runs, launcher = await _setup(cfg, user_id, bot)

    run = await launcher.launch(user_id, routine, SLOT, late=True, now=NOW)

    messages = await rig.talk.list_messages(user_id, routine.thread_id)
    assert [(m.role, m.kind) for m in messages][:1] == [("user", "routine")]
    assert messages[0].body == "Read the headlines.\n\n" + slot_line(SLOT, NOW, late=True)
    assert "Planned 10:07, running at 14:22 (late)." in messages[0].body
    item = await rig.runner.queue.get(user_id, run.work_item_id)
    assert item.kind is WorkKind.ROUTINE and item.origin == "routine Morning news"
    assert item.body == "Morning news" and item.thread_id == routine.thread_id
    assert run.state in ("queued", "running", "done")
    await wait_idle(rig.runner)


async def test_an_on_time_slot_line_says_running_now(cfg, user_id, bot):
    assert slot_line(SLOT, SLOT, late=False) == "Planned 10:07, running now."


async def test_a_tainted_routine_queues_a_tainted_item(cfg, user_id, bot):
    rig, routine, runs, launcher = await _setup(cfg, user_id, bot, tainted=True)

    run = await launcher.launch(user_id, routine, SLOT, late=False, now=NOW)

    assert (await rig.runner.queue.get(user_id, run.work_item_id)).tainted is True
    await wait_idle(rig.runner)


async def test_routine_threads_never_show_in_the_thread_list_or_as_the_main_chat(cfg, user_id, bot):
    rig, routine, runs, launcher = await _setup(cfg, user_id, bot)
    chat = await rig.talk.create_thread(user_id, bot.id)
    await rig.talk.add_message(user_id, chat.id, "user", "hi")
    await launcher.launch(user_id, routine, SLOT, late=False, now=NOW)
    await wait_idle(rig.runner)

    assert [t.id for t in await rig.talk.list_threads(user_id, bot.id)] == [chat.id]
    assert (await rig.talk.main_thread(user_id, bot.id)).id == chat.id
    assert (await rig.talk.latest_for_bot(user_id, bot.id)).thread_id == chat.id


async def test_a_report_reaches_the_model_as_text(cfg, user_id, bot):
    model = team_model({"Scout": [[TextDelta("Noted."), TurnDone("end_turn")]]})
    rig = make_rig(cfg, model)
    chat = await rig.talk.create_thread(user_id, bot.id)
    body = ReportBody(source="routine", headline="Morning news", text="Three stories.")
    await rig.talk.add_message(user_id, chat.id, "bot", body.model_dump_json(), kind="report",
                               author_bot_id=bot.id)
    await send(rig, user_id, bot.id, chat.id, "about that report")
    await wait_idle(rig.runner)

    texts = [t.text for t in model.requests[0].turns]
    assert "Report (routine): Morning news\n\nThree stories." in texts


async def test_routine_notes_and_proposals_never_reach_the_model(cfg, user_id, bot):
    model = team_model({"Scout": [[TextDelta("Ok."), TurnDone("end_turn")]]})
    rig = make_rig(cfg, model)
    chat = await rig.talk.create_thread(user_id, bot.id)
    for kind, text in (("routine_note", "NOTE-SECRET"), ("routine_proposal", "PROPOSAL-SECRET"),
                       ("question_note", "QUESTION-SECRET")):
        await rig.talk.add_message(user_id, chat.id, "activity" if kind != "routine_proposal" else "bot",
                                   json.dumps({"x": text}), kind=kind, author_bot_id=bot.id)
    await send(rig, user_id, bot.id, chat.id, "hello")
    await wait_idle(rig.runner)

    joined = " ".join(t.text for t in model.requests[0].turns)
    assert "SECRET" not in joined


async def test_a_reminder_reaches_the_model_naming_its_task(cfg, user_id, bot):
    """Owner, 2026-10-26: "Yeah I texted him" after a reminder ticks the right task off, so the bot must read the
    reminder as the task's title and id."""
    model = team_model({"Scout": [[TextDelta("Ticked off."), TurnDone("end_turn")]]})
    rig = make_rig(cfg, model)
    chat = await rig.talk.create_thread(user_id, bot.id)
    body = ReportBody(source="reminder", headline="Reminder: Reply to Jin Hu", task_id="task-9",
                      task_title="Reply to Jin Hu", text="Quick reminder: Reply to Jin Hu is due today.")
    await rig.talk.add_message(user_id, chat.id, "bot", body.model_dump_json(), kind="report", author_bot_id=bot.id)
    await send(rig, user_id, bot.id, chat.id, "Yeah I texted him")
    await wait_idle(rig.runner)

    texts = [t.text for t in model.requests[0].turns]
    assert ("Reminder for task Reply to Jin Hu (id task-9): Quick reminder: Reply to Jin Hu is due today."
            in texts)


async def test_an_answered_reminder_tells_the_model_the_answer(cfg, user_id, bot):
    model = team_model({"Scout": [[TextDelta("Ok."), TurnDone("end_turn")]]})
    rig = make_rig(cfg, model)
    chat = await rig.talk.create_thread(user_id, bot.id)
    body = ReportBody(source="reminder", headline="Reminder: Old title", task_id="task-9",
                      text="It's time: Old title (10:00 Madrid).", answer="done")
    await rig.talk.add_message(user_id, chat.id, "bot", body.model_dump_json(), kind="report", author_bot_id=bot.id)
    await send(rig, user_id, bot.id, chat.id, "thanks")
    await wait_idle(rig.runner)

    texts = [t.text for t in model.requests[0].turns]
    assert ("Reminder for task Old title (id task-9): It's time: Old title (10:00 Madrid). "
            "You already answered it: done." in texts)
