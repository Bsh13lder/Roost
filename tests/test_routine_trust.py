"""Trust in a routine run (Task 8): its taint, "nobody is watching", the Ask-card deadline, and Amendment R1's
retry-once and quiet overlap note. Everything runs on a fake clock and the scripted model."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import roost.talk.tool_runner as tool_runner_module

from roost.approvals.models import CardState
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import ROUTINE_ASK_MAX_WAIT_HOURS
from roost.db.connection import init_db
from roost.desk import DeskFactory, PageText
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import ReportBody, RoutineDraft, RoutinePatch
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.scheduler import RoutineScheduler
from roost.routines.store import RoutineStore
from roost.routines.texts import RETRY_NOTE
from roost.stuck.store import StuckStore
from roost.talk.instructions import routine_section
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.turn import RunInputs, _routine_run, _user_started
from roost.work.models import WorkItem, WorkKind, WorkState
from team_helpers import RecordingModel, make_bot, send, wait_idle

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)            # 10:00 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})
NEWS = "https://news.example/"
NEWS_PAGE = PageText(url=NEWS, title="News", text="Quiet day.", truncated=False, status=200)
SHOP = "https://shop.example/"
CHALLENGE = PageText(url=SHOP, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now = self.now + timedelta(**delta)


class Boom:
    """Raises on its first ``fails`` calls, then answers from ``inner``."""

    def __init__(self, inner, fails: int) -> None:
        self._inner, self._fails = inner, fails
        self.calls = 0

    async def stream(self, request):
        self.calls += 1
        if self.calls <= self._fails:
            raise RuntimeError("model down")
        async for event in self._inner.stream(request):
            yield event


def _tool(*calls):
    return [*calls, TurnDone("tool_use")]


def _say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


def _add_task(call_id="c1"):
    return ToolCallRequested(id=call_id, name="add_task", arguments={"title": "Call bank"})


class Rigged:
    def __init__(self, cfg, clock, scripts, *, fails: int = 0):
        self.cfg, self.clock = cfg, clock
        self.bots, self.talk, self.events, self.desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
        scripted = RecordingModel(ScriptedTeamModel(scripts))
        self.model = scripted
        self.cards = ApprovalStore(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=clock)
        self.runs = RoutineRunStore(cfg, clock=clock)
        self.hooks = RoutineHooks(self.talk, self.events, self.runs, self.routines, clock=clock)
        self.runner = TurnRunner(
            cfg, self.bots, self.talk, self.events, self.desks, Boom(scripted, fails), ActivityBoard(),
            approvals=ApprovalWiring(self.cards, SessionOks()), routines=self.hooks)
        self.hooks.attach(self.runner, self.cards, self.bots)
        self.scheduler = RoutineScheduler(
            cfg, clock=clock, launcher=RoutineLauncher(self.talk, self.runner, self.runs, self.events),
            runs=self.runs, routines=self.routines, turns=self.runner, bots=self.bots, hooks=self.hooks)

    async def routine(self, user_id, bot, *, tainted=False, name="Morning news", instructions="Read the headlines."):
        return await self.routines.create(user_id, RoutineDraft(
            bot_id=bot.id, name=name, instructions=instructions, schedule=SCHEDULE, created_by="user",
            tainted=tainted))

    async def fire(self, minutes=9):
        self.clock.advance(minutes=minutes)
        await self.scheduler.tick()
        await wait_idle(self.runner)

    async def reports(self, user_id, bot_id) -> list[ReportBody]:
        thread, _ = await self.talk.ensure_main_thread(user_id, bot_id)
        messages = await self.talk.list_messages(user_id, thread.id)
        return [ReportBody.model_validate_json(m.body) for m in messages if m.kind == "report"]


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


async def _ask_mode(cfg, user_id, bot):
    from roost.approvals.models import BotApproval
    assert await BotStore(cfg).set_approval(user_id, bot.id, BotApproval("ask", frozenset())) is not None


# ---- starting taint -------------------------------------------------------------------------------------------

async def test_a_tainted_routine_starts_its_run_tainted(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("Headlines: quiet day.")]})
    await rig.routine(user_id, bot, tainted=True)

    await rig.fire()

    [report] = await rig.reports(user_id, bot.id)
    assert report.tainted is True


async def test_a_clean_routine_turns_tainted_on_a_tainted_plan_item(cfg, clock, user_id, bot):
    """Outside content met mid-run (here a page; a tainted Plan item takes the same path) taints the run."""
    rig = Rigged(cfg, clock, {"Scout": [_tool(ToolCallRequested(id="o1", name="open_page", arguments={"url": NEWS})),
                                         _say("Headlines: quiet day.")]})
    rig.desks.for_bot(bot.id).serve(NEWS, NEWS_PAGE)
    await rig.routine(user_id, bot)

    await rig.fire()

    [report] = await rig.reports(user_id, bot.id)
    assert report.tainted is True


WHATSAPP = "https://web.whatsapp.com/"
WHATSAPP_PAGE = PageText(url=WHATSAPP, title="WhatsApp", text="Chats.", truncated=False, status=200)


async def _opens(cfg, clock, user_id, bot, instructions: str, url: str, page: PageText) -> list[str]:
    rig = Rigged(cfg, clock, {"Scout": [_tool(ToolCallRequested(id="o1", name="open_page", arguments={"url": url})),
                                         _say("Nothing new.")]})
    rig.desks.for_bot(bot.id).serve(url, page)
    await rig.routine(user_id, bot, tainted=True, instructions=instructions)
    await rig.fire()
    return [card.steps[0].title for card in await rig.cards.list_open(user_id)]


async def test_a_tainted_routine_opens_a_well_known_site_its_own_instructions_name(cfg, clock, user_id, bot):
    # Owner, 2026-11-04: "Watch physio chat" read WhatsApp once, and its next run asked to open WhatsApp Web.
    cards = await _opens(cfg, clock, user_id, bot, "Open WhatsApp Web and read the physio chat.", WHATSAPP,
                         WHATSAPP_PAGE)
    assert cards == []


async def test_a_tainted_routine_still_asks_for_a_site_its_instructions_never_name(cfg, clock, user_id, bot):
    cards = await _opens(cfg, clock, user_id, bot, "Open WhatsApp Web and read the physio chat.", NEWS, NEWS_PAGE)
    assert cards == ["Open news.example"]


WIZZ = "https://www.wizzair.com/en-gb/booking/select-flight/BCN/KUT"
WIZZ_PAGE = PageText(url=WIZZ, title="Wizz Air", text="Prices.", truncated=False, status=200)
WIZZ_ROUTINE = "On the official Wizz Air site (wizzair.com, signed in), list the prices for 1-13 Dec."


async def _chat_opened(cfg, user_id, bot_id, url: str) -> None:
    """The gate's audit row for an open from your own chat (reason ``fresh_open``)."""
    import json

    from roost.crypto.encryption import encrypt, user_aad
    from roost.crypto.key_manager import get_user_dek
    from roost.db.connection import db_session

    dek = await get_user_dek(cfg, user_id)
    detail = encrypt(json.dumps({"url": url}), dek, user_aad(user_id, "audit:detail"))
    async with db_session(cfg) as db:
        await db.execute(
            "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
            "VALUES (?,?,'open_page','do',?,?,'fresh_open',0)",
            (user_id, bot_id, detail, datetime.now(timezone.utc).isoformat()))
        await db.commit()


async def test_a_routine_opens_a_site_it_names_that_your_chat_opened_with_no_card(cfg, clock, user_id, bot):
    # Owner, 2026-11-05: Gela opened Wizz Air in your chat, then her 09:00 check asked "Open www.wizzair.com".
    await _chat_opened(cfg, user_id, bot.id, "https://www.wizzair.com/")
    assert await _opens(cfg, clock, user_id, bot, WIZZ_ROUTINE, WIZZ, WIZZ_PAGE) == []


async def test_a_routine_still_asks_for_a_site_it_names_that_your_chat_never_opened(cfg, clock, user_id, bot):
    assert await _opens(cfg, clock, user_id, bot, WIZZ_ROUTINE, WIZZ, WIZZ_PAGE) == ["Open www.wizzair.com"]


# ---- the section -----------------------------------------------------------------------------------------------

def test_the_routine_section_says_nobody_is_watching_and_quotes_answers():
    section = routine_section("News <b>", "Planned 10:07, running now.", ("weekly <script>alert(1)</script>",))

    assert "Nobody is watching live" in section and "next run" in section and "note_question" in section
    assert "[nothing new]" in section and "Planned 10:07, running now." in section
    assert "<script>" not in section and "&lt;script&gt;" in section and "News &lt;b&gt;" in section


async def test_a_routine_run_is_told_its_section_and_a_chat_run_is_not(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("[nothing new]"), _say("Hello.")]})
    await rig.routine(user_id, bot)
    await rig.fire()
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Hi")
    await wait_idle(rig.runner)

    routine_system, chat_system = (r.system for r in rig.model.requests)
    assert "Nobody is watching live" in routine_system and "Planned 10:07" in routine_system
    assert "Nobody is watching" not in chat_system


async def test_a_routine_run_never_creates_bots_or_captures_memory(cfg, clock, user_id):
    items = (_item(WorkKind.ROUTINE),)
    assert _user_started(items) is False
    assert _routine_run(RunInputs(items=items)) is True and _routine_run(RunInputs(items=(_item(WorkKind.MESSAGE),))) is False
    from roost.memory.capture import FinishedRun, capture_eligible
    run = FinishedRun(user_id=user_id, bot_id="b", thread_id="t", items=items, in_room=False, tainted=False,
                      answered=True, blocked=False)
    assert capture_eligible(run) is False
    main = await BotStore(cfg).list(user_id)
    rig = Rigged(cfg, FakeClock(NOW), {"Chief": [_say("[nothing new]")]})
    chief = next((b for b in main if b.is_primary), None) or await make_bot(cfg, user_id, "Chief")
    await rig.routine(user_id, chief)
    await rig.fire()
    assert all(t.name != "create_bot" for t in rig.model.requests[-1].tools)


def _item(kind: WorkKind) -> WorkItem:
    return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin="o", body="", tainted=False,
                    depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r", inflight=None,
                    result=None, result_tainted=False, created_at="", updated_at="")


async def test_a_routine_run_that_meets_a_wall_reports_it(cfg, clock, user_id, bot, monkeypatch):
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)
    rig = Rigged(cfg, clock, {"Scout": [_tool(ToolCallRequested(id="o1", name="open_page", arguments={"url": SHOP})),
                                         _say("The shop would not let me in.")]})
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    routine = await rig.routine(user_id, bot)

    await rig.fire()

    [report] = await rig.reports(user_id, bot.id)
    assert report.headline.startswith("Stuck: Morning news")
    assert await StuckStore(cfg).open_for_bot(user_id, bot.id) is None     # no Stuck card: nobody is there
    [run] = await rig.runs.list_for_routine(user_id, routine.id)
    assert run.state == "error"
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.STUCK


# ---- Ask cards from a routine run -----------------------------------------------------------------------------

async def _parked(cfg, clock, user_id, bot):
    await _ask_mode(cfg, user_id, bot)
    rig = Rigged(cfg, clock, {"Scout": [_tool(_add_task()), _say("Done.")]})
    routine = await rig.routine(user_id, bot)
    await rig.fire()
    return rig, routine


async def test_a_routine_run_parks_on_an_ask_card_and_stays_open(cfg, clock, user_id, bot):
    rig, routine = await _parked(cfg, clock, user_id, bot)

    [card] = await rig.cards.list_open(user_id)
    assert card.work_item_id
    [run] = await rig.runs.list_for_routine(user_id, routine.id)
    assert run.state == "running" and await rig.reports(user_id, bot.id) == []


async def test_an_unanswered_card_expires_at_the_next_slot(cfg, clock, user_id, bot):
    rig, routine = await _parked(cfg, clock, user_id, bot)
    clock.advance(hours=5)           # 15:09, past the 15:07 slot

    await rig.scheduler.tick()
    await wait_idle(rig.runner)

    assert await rig.cards.list_open(user_id) == ()
    runs = {r.slot_at: r for r in await rig.runs.list_for_routine(user_id, routine.id)}
    first = min(runs)
    assert runs[first].state == "expired"
    [report] = [r for r in await rig.reports(user_id, bot.id) if r.headline.startswith("Waited for you")]
    assert "Add a task" in report.text and "won't ask again" in report.text
    assert (await rig.bots.get(user_id, bot.id)).status is not BotStatus.ASKING_YOU


async def test_a_card_waits_no_longer_than_a_day(cfg, clock, user_id, bot):
    rig, routine = await _parked(cfg, clock, user_id, bot)
    # a weekly routine: the next slot is days away, but the card still stops at the cap
    await rig.routines.update(user_id, routine.id, RoutinePatch(
        {"schedule": parse_schedule({"kind": "times", "days": [(NOW + timedelta(days=3)).isoweekday()], "times": ["10:07"]})}))
    clock.advance(hours=ROUTINE_ASK_MAX_WAIT_HOURS - 1)
    await rig.hooks.sweep_asks(user_id, clock())
    assert len(await rig.cards.list_open(user_id)) == 1
    clock.advance(hours=2)

    await rig.hooks.sweep_asks(user_id, clock())

    assert await rig.cards.list_open(user_id) == ()


async def test_a_slot_is_skipped_while_a_card_waits(cfg, clock, user_id, bot):
    rig, routine = await _parked(cfg, clock, user_id, bot)
    run = (await rig.runs.open_runs(user_id))[0]
    assert await rig.hooks.parked_on_card(user_id, run) is True

    routine = await rig.routines.get(user_id, routine.id)
    await rig.scheduler._skip_overlap(routine, clock.now)      # the next slot comes while it waits

    states = sorted(r.state for r in await rig.runs.list_for_routine(user_id, routine.id))
    assert states == ["running", "skipped"]
    skipped = next(r for r in await rig.runs.list_for_routine(user_id, routine.id) if r.state == "skipped")
    assert skipped.note == "still waiting for you"


async def test_a_run_waiting_on_a_card_is_not_called_lost_by_the_reconcile(cfg, clock, user_id, bot):
    rig, routine = await _parked(cfg, clock, user_id, bot)
    clock.advance(minutes=10)        # past the reconcile grace, still before the next slot

    await rig.scheduler.tick()

    assert [r.state for r in await rig.runs.list_for_routine(user_id, routine.id)] == ["running"]


async def test_a_chat_card_keeps_its_own_deadline(cfg, clock, user_id, bot):
    await _ask_mode(cfg, user_id, bot)
    rig = Rigged(cfg, clock, {"Scout": [_tool(_add_task()), _say("Added.")]})
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Add a task")
    await wait_idle(rig.runner)
    [card] = await rig.cards.list_open(user_id)
    item = await rig.runner.queue.get(user_id, card.work_item_id)

    assert await rig.hooks.ask_deadline(user_id, (item,), clock.now) is None
    clock.advance(days=5)
    await rig.hooks.sweep_asks(user_id, clock())
    assert [c.state for c in await rig.cards.list_open(user_id)] == [CardState.OPEN]


# ---- Amendment R1 ---------------------------------------------------------------------------------------------

async def test_an_errored_run_retries_once_and_then_reports(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("Headlines: quiet day.")]}, fails=1)
    routine = await rig.routine(user_id, bot)

    await rig.fire()

    [run] = await rig.runs.list_for_routine(user_id, routine.id)
    assert run.state == "done" and run.note == RETRY_NOTE
    [report] = await rig.reports(user_id, bot.id)
    assert report.headline.startswith("Headlines")


async def test_a_run_that_errors_twice_goes_stuck_with_a_reason_and_a_next_step(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": []}, fails=2)
    routine = await rig.routine(user_id, bot)

    await rig.fire()

    [run] = await rig.runs.list_for_routine(user_id, routine.id)
    assert run.state == "error"
    [report] = await rig.reports(user_id, bot.id)
    assert report.headline == "Didn't finish: Morning news"
    assert "failed twice" in report.text and "Next step" in report.text
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.STUCK


async def test_an_overlap_skip_leaves_one_quiet_note_a_day(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": []})
    routine = await rig.routine(user_id, bot)
    clock.advance(minutes=9)
    await rig.scheduler.tick()                       # queued, never finished: the next slots overlap
    routine = await rig.routines.get(user_id, routine.id)

    for _ in range(3):
        await rig.scheduler._skip_overlap(routine, clock.now)
        clock.advance(minutes=1)

    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    notes = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "routine_note"]
    assert len(notes) == 1 and "still going" in json.loads(notes[0].body)["text"]
    clock.advance(days=1)
    await rig.scheduler._skip_overlap(routine, clock.now)
    notes = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "routine_note"]
    assert len(notes) == 2
