"""A routine run's final reply becomes a Report in the bot's main chat; failures always report (fake clock)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import roost.routines.reports as reports_module
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import ReportBody, RoutineDraft
from roost.routines.reports import post_report
from roost.routines.runs import RoutineRunStore
from roost.routines.scheduler import RoutineScheduler
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.turn import TurnResult
from roost.work.models import ClaimedBatch, RunOutcome, WorkDraft, WorkKind, ORIGIN_YOU
from team_helpers import frames_so_far, make_bot, wait_idle

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now = self.now + timedelta(**delta)


def say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


class Rigged:
    def __init__(self, cfg, scripts, clock):
        self.bots, self.talk, self.events = BotStore(cfg), TalkStore(cfg), EventHub(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=clock)
        self.runs = RoutineRunStore(cfg, clock=clock)
        self.hooks = RoutineHooks(self.talk, self.events, self.runs, self.routines, clock=clock)
        self.model = ScriptedTeamModel(scripts)
        self.runner = TurnRunner(cfg, self.bots, self.talk, self.events, DeskFactory(cfg), self.model,
                                 ActivityBoard(), routines=self.hooks)
        self.launcher = RoutineLauncher(self.talk, self.runner, self.runs, self.events)
        self.scheduler = RoutineScheduler(
            cfg, clock=clock, launcher=self.launcher, runs=self.runs, routines=self.routines, turns=self.runner,
            bots=self.bots, hooks=self.hooks)

    async def routine(self, user_id, bot, name="Morning news"):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions="Read the headlines.", schedule=SCHEDULE, created_by="user"))

    async def main_messages(self, user_id, bot):
        thread = await self.talk.main_thread(user_id, bot.id)
        return [] if thread is None else await self.talk.list_messages(user_id, thread.id)


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


@pytest.fixture
def clock():
    return FakeClock(NOW)


async def _fire(rigged, clock, user_id):
    clock.advance(minutes=9)
    await rigged.scheduler.tick()
    await wait_idle(rigged.runner)


async def test_the_final_reply_becomes_a_report_in_the_main_chat(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("# Morning headlines\n\nThree stories today.")]}, clock)
    routine = await rigged.routine(user_id, bot)
    subscription = rigged.events.subscribe(user_id)

    await _fire(rigged, clock, user_id)

    reports = [m for m in await rigged.main_messages(user_id, bot) if m.kind == "report"]
    assert len(reports) == 1 and reports[0].role == "bot" and reports[0].author_bot_id == bot.id
    body = json.loads(reports[0].body)
    assert body["headline"] == "Morning headlines" and "Three stories today." in body["text"]
    assert body["source"] == "routine" and body["routine_id"] == routine.id
    assert body["log_thread_id"] == routine.thread_id and body["tainted"] is False
    run = (await rigged.runs.list_for_routine(user_id, routine.id))[0]
    assert run.state == "done" and run.finished_at is not None and body["run_id"] == run.id
    types = [f["type"] for f in await frames_so_far(subscription)]
    assert "routine_run" in types and "message" in types


async def test_the_quiet_sentinel_posts_nothing_in_your_chat(cfg, clock, user_id, bot):
    """Owner, 2026-11-05 ("empty routine runs, so noisy"): a run with nothing new leaves your chat alone; its
    reply stays in the run log."""
    rigged = Rigged(cfg, {"Scout": [say("On it: checking.\n\n  [nothing new]  ")]}, clock)
    routine = await rigged.routine(user_id, bot)

    await _fire(rigged, clock, user_id)

    assert await rigged.main_messages(user_id, bot) == []
    assert (await rigged.runs.list_for_routine(user_id, routine.id))[0].state == "done"


async def test_a_tainted_run_gives_a_marked_report(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("Found it.")]}, clock)
    routine = await rigged.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Tainted", instructions="Go.", schedule=SCHEDULE, created_by="bot", tainted=True))

    await _fire(rigged, clock, user_id)

    report = next(m for m in await rigged.main_messages(user_id, bot) if m.kind == "report")
    assert report.tainted is True and json.loads(report.body)["tainted"] is True


async def test_reports_past_the_hourly_cap_fold_into_the_run_log(cfg, clock, monkeypatch, user_id, bot):
    monkeypatch.setattr(reports_module, "REPORTS_PER_BOT_PER_HOUR", 1)
    rigged = Rigged(cfg, {"Scout": [say("First."), say("Second.")]}, clock)
    routine = await rigged.routine(user_id, bot)
    now = datetime.now(UTC)
    clock.now = now
    body = ReportBody(source="routine", headline="First", text="First.", routine_id=routine.id,
                      log_thread_id=routine.thread_id)

    first = await post_report(rigged.talk, rigged.events, user_id, bot.id, body, runs=rigged.runs, now=now)
    second = await post_report(rigged.talk, rigged.events, user_id, bot.id, body, runs=rigged.runs, now=now)
    failure = await post_report(rigged.talk, rigged.events, user_id, bot.id, body, runs=rigged.runs, now=now,
                                always=True)

    assert first is not None and second is None and failure is not None
    log = await rigged.talk.list_messages(user_id, routine.thread_id)
    assert [json.loads(m.body)["text"] for m in log if m.kind == "routine_note"] == [
        "More reports this hour than the limit; this one is in the log"]


async def _run_with(rigged, user_id, bot, routine, result: TurnResult, outcome: RunOutcome):
    """Run the after-run pass for a queued routine item with a result we choose (the bot is off duty, so the
    item is never drained by a real run)."""
    await rigged.bots.set_off_duty(user_id, bot.id, True)
    run = await rigged.launcher.launch(user_id, routine, NOW, late=False, now=NOW)
    item = await rigged.runner.queue.get(user_id, run.work_item_id)
    await rigged.runs.set_state(user_id, run.id, "running")
    batch = ClaimedBatch(run_id="r", bot=bot, thread_id=routine.thread_id, items=(item,))
    await rigged.hooks.after_run(user_id, batch, result, outcome)


async def test_failures_always_report(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("x")]}, clock)
    routine = await rigged.routine(user_id, bot)
    block = Block(reason="login", url="https://shop.example/x", host="shop.example", note="")

    await _run_with(rigged, user_id, bot, routine, TurnResult("", False, False, block=block), "done")

    reports = [json.loads(m.body) for m in await rigged.main_messages(user_id, bot) if m.kind == "report"]
    assert [r["headline"] for r in reports] == ["Stuck: Morning news on shop.example"]
    assert [r["headline"] for r in reports][-1] == "Stuck: Morning news on shop.example"
    run = (await rigged.runs.list_for_routine(user_id, routine.id))[0]
    assert run.state == "error"


@pytest.mark.parametrize("outcome", ["time_cap", "step_cap", "error"])
async def test_a_run_that_did_not_finish_reports_it(cfg, clock, user_id, bot, outcome):
    rigged = Rigged(cfg, {"Scout": [say("x")]}, clock)
    routine = await rigged.routine(user_id, bot)

    await _run_with(rigged, user_id, bot, routine, TurnResult("", False, False), outcome)

    reports = [json.loads(m.body) for m in await rigged.main_messages(user_id, bot) if m.kind == "report"]
    assert [r["headline"] for r in reports] == ["Didn't finish: Morning news"]
    assert (await rigged.runs.list_for_routine(user_id, routine.id))[0].state == "error"


async def test_a_stopped_run_is_skipped_with_no_report(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("x")]}, clock)
    routine = await rigged.routine(user_id, bot)

    await _run_with(rigged, user_id, bot, routine, TurnResult("", False, False), "stopped")

    run = (await rigged.runs.list_for_routine(user_id, routine.id))[0]
    assert (run.state, run.note) == ("skipped", "Stopped")
    assert [m for m in await rigged.main_messages(user_id, bot) if m.kind == "report"] == []


async def test_a_stopped_routine_run_is_closed_as_skipped(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {}, clock)
    routine = await rigged.routine(user_id, bot)
    await BotStore(cfg).set_off_duty(user_id, bot.id, True)       # nothing drains, so the item stays queued
    run = await rigged.launcher.launch(user_id, routine, NOW, late=False, now=NOW)
    await rigged.runner.queue.drop_for_bot(user_id, bot.id)

    await rigged.scheduler.tick()

    closed = (await rigged.runs.list_for_routine(user_id, routine.id))[0]
    assert (closed.id, closed.state, closed.note) == (run.id, "skipped", "Stopped")


async def test_a_finished_item_with_no_after_run_pass_is_closed_as_error(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {}, clock)
    routine = await rigged.routine(user_id, bot)
    await BotStore(cfg).set_off_duty(user_id, bot.id, True)
    run = await rigged.launcher.launch(user_id, routine, NOW, late=False, now=NOW)
    claimed = await rigged.runner.queue.claim_batch(user_id, bot.id, "run-x")
    await rigged.runner.queue.complete(user_id, "run-x", "done", False)
    clock.now = datetime.now(UTC) + timedelta(hours=1)

    await rigged.scheduler.tick()

    states = {r.id: r.state for r in await rigged.runs.list_for_routine(user_id, routine.id)}
    assert claimed and states[run.id] == "error"


async def test_a_claimed_item_moves_its_run_to_running(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {}, clock)
    routine = await rigged.routine(user_id, bot)
    await BotStore(cfg).set_off_duty(user_id, bot.id, True)
    await rigged.launcher.launch(user_id, routine, NOW, late=False, now=NOW)
    await rigged.runner.queue.claim_batch(user_id, bot.id, "run-x")

    await rigged.scheduler.tick()

    assert (await rigged.runs.list_for_routine(user_id, routine.id))[0].state == "running"


async def test_a_non_routine_run_never_reports(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("Hello there")]}, clock)
    chat = await rigged.talk.create_thread(user_id, bot.id)
    message = await rigged.talk.add_message(user_id, chat.id, "user", "hi")
    await rigged.runner.submit(user_id, WorkDraft(
        bot_id=bot.id, thread_id=chat.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body="hi",
        message_id=message.id))
    await wait_idle(rigged.runner)

    assert [m.kind for m in await rigged.talk.list_messages(user_id, chat.id)] == ["text", "text"]
    assert await rigged.runs.open_runs(user_id) == ()


async def test_held_at_the_daily_cap_with_one_report(cfg, clock, monkeypatch, user_id, bot):
    import roost.talk.runner as runner_module
    rigged = Rigged(cfg, {}, clock)
    first = await rigged.routine(user_id, bot, name="First")
    second = await rigged.routine(user_id, bot, name="Second")
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    await rigged.runner._runs.start(user_id, bot.id, "thread", "run-1")
    clock.now = NOW + timedelta(minutes=9)
    await rigged.scheduler.tick()

    held = [r for rid in (first.id, second.id) for r in await rigged.runs.list_for_routine(user_id, rid)]
    assert [r.state for r in held] == ["held", "held"]
    reports = [json.loads(m.body) for m in await rigged.main_messages(user_id, bot) if m.kind == "report"]
    assert len(reports) == 1 and reports[0]["text"].startswith("Held: ")
    assert reports[0]["text"].endswith("Paused my routines: I've used today's 1 runs. They start again after midnight.")


async def test_a_missed_slot_and_a_slot_skipped_while_waiting_report(cfg, clock, user_id, bot):
    rigged = Rigged(cfg, {"Scout": [say("Done.")]}, clock)
    await rigged.routine(user_id, bot)
    clock.advance(days=1, hours=4)

    await rigged.scheduler.tick()
    await wait_idle(rigged.runner)

    headlines = [json.loads(m.body)["headline"] for m in await rigged.main_messages(user_id, bot)
                 if m.kind == "report"]
    assert "Missed: Morning news" in headlines


@pytest.mark.parametrize("reply", [
    "[nothing new]",
    "On it: checking your open tasks for urgent overdue ones.\n\n[nothing new]",
    "On it: checking your open tasks.\n[nothing new]\n",
    # Owner, 2026-10-28: the bot said its "On it" line again after its tool step, and the Report still came.
    "On it: checking your open tasks for urgent overdue ones.\n\nOn it: checking your open tasks for urgent overdue"
    " ones.\n\n[nothing new]",
    "**[nothing new]**",
    "On it: checking.\n\\[Nothing new\\].",
])
def test_nothing_new_after_the_on_it_line_is_still_quiet(reply):
    # Owner, 2026-10-26: "If its no overdue and etc why he bothers me?" The first-line rule put "On it: …" first.
    assert reports_module.is_quiet(reply)


@pytest.mark.parametrize("reply", [
    "Checking the Deduci chat.\n[nothing new]",
    "Checking the Deduci chat. [nothing new]",
    "On it: checking.\nLooking at the WhatsApp chat with Deduci…\n\n**[nothing new]**",
    "Revisando el chat de Deduci.\n[nothing new]",
])
def test_a_line_that_only_says_what_it_is_checking_is_still_quiet(reply):
    # Owner, 2026-11-07: "if its there no message and nothing why it shows me?" The watch said
    # "Checking the Deduci chat." before its [nothing new], and that came to the chat as a Report.
    assert reports_module.is_quiet(reply)


@pytest.mark.parametrize("reply", [
    "Two tasks are overdue: Pay rent, Call Francis.",
    "On it: checking.\n\nPay rent is overdue.\n\n[nothing new]",
    "[nothing new] except Pay rent is overdue.",
    "Deduci replied: the flat is free on Monday.\n[nothing new]",
    "Checking the chat.\nDeduci replied: the flat is free on Monday.\n[nothing new]",
    "Checking the Deduci chat, which now has a long new message about the rent, the keys and the visit on Monday "
    "at noon.\n[nothing new]",
])
def test_a_reply_with_anything_else_in_it_is_a_report(reply):
    assert not reports_module.is_quiet(reply)


def test_the_headline_skips_the_on_it_line():
    reply = "On it: checking your open tasks.\n\nPay rent is overdue since Friday."
    assert reports_module.headline_of(reply, "Overdue check") == "Pay rent is overdue since Friday."
    assert reports_module.headline_of("On it: checking.", "Overdue check") == "On it: checking."


def test_a_report_body_drops_the_on_it_line_from_its_text():
    """Owner, 2026-10-26: a Report reads as a plain bot message, without the first-line rule's "On it: …"."""
    body = reports_module.report_body(
        "On it: checking your open tasks.\n\nPay rent is overdue since Friday.", name="Overdue check",
        routine_id="r-1", run_id="run-1", log_thread_id="t-log", tainted=False)
    assert body.text == "Pay rent is overdue since Friday."
    assert body.routine_name == "Overdue check"


def test_a_report_body_drops_every_leading_on_it_line():
    reply = "On it: checking.\n\nOn it: checking.\n\nPay rent is overdue since Friday."
    body = reports_module.report_body(reply, name="Check", routine_id="r", run_id="u", log_thread_id="t",
                                      tainted=False)
    assert body.text == "Pay rent is overdue since Friday."
    assert body.headline == "Pay rent is overdue since Friday."


def test_a_report_body_that_is_only_the_on_it_line_keeps_it():
    body = reports_module.report_body("On it: checking.", name="Check", routine_id="r", run_id="u",
                                      log_thread_id="t", tainted=False)
    assert body.text == "On it: checking."
