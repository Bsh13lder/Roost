"""The whole booking in one run of your own chat (owner, 2026-11-05: "like Grok: do everything said in chat, ask
only for payment"), on the scripted Fake shop's bus tickets (``ROOST_FAKE_SCREEN=shop``, roost/desk/fake_shop.py).

The bot opens the shop and reads it (the run is tainted from then on), types the two names and the passport number
from your message into the form, clicks the POST form's Continue, Accept terms and Confirm booking with no card, and
only Pay asks; Yes pays. The same script in a routine run stops at the first submit: the hard floor still holds
there."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from roost.approvals.executor import ApprovedCalls
from roost.approvals.service import ApprovalService
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.models import BotDraft, BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.computer_use.reruns import ScreenReruns
from roost.computer_use.session import ComputerUseLease
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.desk import DeskFactory
from roost.desk.control import ControlLock
from roost.desk.fake import FAKE_SCREEN_ENV
from roost.desk.fake_shop import FAKE_SHOP
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.routines.hooks import RoutineHooks
from roost.routines.launcher import RoutineLauncher
from roost.routines.models import RoutineDraft
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.scheduler import RoutineScheduler
from roost.routines.store import RoutineStore
from roost.stuck.store import StuckStore
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import Gate
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore

from cu_run_helpers import AVATAR
from team_helpers import RecordingModel, send, wait_idle

WAIT = 10
SHOP_URL = "https://shop.test/"
NAMES = ("Maka Eremadze", "Nino Beridze")
PASSPORT = "13AB45678"
YOUR_MESSAGE = (f"Book 2 bus tickets on shop.test for {NAMES[0]} and {NAMES[1]}, passport {PASSPORT}, "
                "accept the terms and pay.")
DONE_TEXT = "Booked and paid: 2 seats."
ACT_TOOLS = ("click", "type", "press_key")
UTC = timezone.utc
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)            # 10:00 in Madrid
SCHEDULE = parse_schedule({"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]})


def _tool(name: str, **args) -> list[dict]:
    return [{"tool": name, "args": args}]


def _click(text: str, kind: str) -> list[dict]:
    return _tool("click", target={"text": text, "kind": kind}, expect=f"{text} is done")


def _fill(label: str, text: str) -> list[list[dict]]:
    return [_click(label, "field"), _tool("type", text=text, source={"from": "message"}, expect=f"{label} holds it")]


def _booking_steps() -> list[list[dict]]:
    """Open and read the shop, fill the form from your message, commit three times, then pay."""
    return [
        _tool("open_page", url=SHOP_URL),
        _tool("look"),
        _click("Bus tickets", "link"),
        *_fill("Passenger 1 name", NAMES[0]),
        *_fill("Passenger 2 name", NAMES[1]),
        *_fill("Passport number", PASSPORT),
        _click("Continue", "button"),
        _click("Accept terms", "button"),
        _click("Confirm booking", "button"),
        _click("Pay 36 EUR", "button"),
        [{"text": DONE_TEXT}],
    ]


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Rig:
    """One gateway's worth of the pieces: the runner, the cards and their answers, and the routine scheduler."""

    def __init__(self, cfg, steps: list[list[dict]]) -> None:
        self.cfg, self.clock = cfg, FakeClock(NOW)
        self.bots, self.talk, self.events, self.desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
        self.model = RecordingModel(ScriptedTeamModel.from_json({"Booker": steps}))
        self.cards, sessions, leases, control = ApprovalStore(cfg), SessionOks(), ComputerUseLease(), ControlLock()
        self.leases, self.control = leases, control
        self.routines = RoutineStore(cfg, self.talk, clock=self.clock)
        runs = RoutineRunStore(cfg, clock=self.clock)
        hooks = RoutineHooks(self.talk, self.events, runs, self.routines, clock=self.clock)
        self.runner = TurnRunner(cfg, self.bots, self.talk, self.events, self.desks, self.model, ActivityBoard(),
                                 approvals=ApprovalWiring(self.cards, sessions), domain=build_domain_tools(cfg, self.events),
                                 control=control, stuck=StuckStore(cfg), cu_leases=leases, routines=hooks)
        hooks.attach(self.runner, self.cards, self.bots)
        gate = Gate(cfg)
        executor = ApprovedCalls(self.runner.domain, gate, self.talk, self.events,
                                 screen=ScreenReruns(cfg, self.bots, self.desks, gate, self.events, leases, control))
        self.service = ApprovalService(self.cards, self.talk, self.events, self.runner, executor, sessions)
        self.scheduler = RoutineScheduler(
            cfg, clock=self.clock, launcher=RoutineLauncher(self.talk, self.runner, runs, self.events), runs=runs,
            routines=self.routines, turns=self.runner, bots=self.bots, hooks=hooks)

    async def setup(self) -> None:
        user = await register_user(self.cfg, "alice", "pw-123456")
        bot = await self.bots.create(user.id, BotDraft(name="Booker", job="books trips", instructions="", avatar=AVATAR))
        await self.bots.update(user.id, bot.id, BotPatch(computer="linux"))
        await self.desks.for_bot(bot.id, "linux").start_browser()
        self.user_id, self.bot_id = user.id, bot.id

    @property
    def page(self):
        return self.desks.for_bot(self.bot_id, "linux").page()

    async def open_cards(self):
        return await self.cards.list_open(self.user_id)


def _audit(cfg) -> list[tuple[str, str, str, int]]:
    """The gate's audit rows for the screen acts, oldest first: (tool, decision, reason, tainted)."""
    con = sqlite3.connect(get_db_path(cfg))
    try:
        rows = con.execute("SELECT action, decision, reason, tainted FROM audit ORDER BY id").fetchall()
    finally:
        con.close()
    return [tuple(row) for row in rows if row[0] in ACT_TOOLS]


def _acts(cfg) -> list[tuple[str, str, str]]:
    return [row[:3] for row in _audit(cfg)]


def _form_boxes(page) -> dict[str, str]:
    """What the booking form's boxes hold (the fake keeps each box's text by its node)."""
    return {t.text: page._boxes.get(t.node_id, "") for t in FAKE_SHOP["tickets"].targets if t.editable}


@pytest.fixture
async def cfg(monkeypatch):
    monkeypatch.setenv(FAKE_SCREEN_ENV, "shop")
    monkeypatch.setattr("roost.desk.ready.CU_READY_STABLE_MS", 0)
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg, steps: list[list[dict]]) -> Rig:
    built = Rig(cfg, steps)
    await built.setup()
    return built


async def test_your_own_chat_books_with_one_card_and_it_is_for_paying(cfg):
    rig = await _rig(cfg, _booking_steps())
    thread = await rig.talk.create_thread(rig.user_id, rig.bot_id)
    await send(rig, rig.user_id, rig.bot_id, thread.id, YOUR_MESSAGE)
    await wait_idle(rig.runner, timeout=WAIT)

    # Before Pay: the form was filled from your message, and every act just ran (the run read the page: tainted).
    assert _form_boxes(rig.page) == {"Passenger 1 name": NAMES[0], "Passenger 2 name": NAMES[1],
                                     "Passport number": PASSPORT}
    assert all(tainted == 1 for *_, tainted in _audit(rig.cfg))
    assert _acts(rig.cfg) == [
        ("click", "do", "allowed"),                                      # Bus tickets
        *[("click", "do", "allowed"), ("type", "do", "allowed")] * 3,    # two names and the passport number
        *[("click", "do", "owner_chat_act")] * 3,                        # Continue, Accept terms, Confirm booking
        ("click", "ask", "hard_floor"),                                  # Pay 36 EUR
    ]
    assert rig.page.state_name == "pay"

    # Exactly one card, for the Pay button; Yes clicks it and the bot carries on.
    [card] = await rig.open_cards()
    rows = {row.label: row.value for row in card.steps[0].rows}
    assert card.steps[0].floor == "commit_click" and rows["Button text"] == "Pay 36 EUR"
    assert rows["What it does"] == "Buys or pays for something"
    await rig.service.answer(rig.user_id, card.id, "yes")
    await wait_idle(rig.runner, timeout=WAIT)

    assert rig.page.state_name == "paid"
    assert await rig.open_cards() == ()
    texts = [m.body for m in await rig.talk.list_messages(rig.user_id, thread.id) if m.role == "bot" and m.kind == "text"]
    assert texts[-1] == DONE_TEXT


async def test_the_same_script_in_a_routine_run_stops_at_the_first_submit(cfg):
    # Your chat opened the shop once, so the routine that names it may browse there (owner, 2026-11-05).
    rig = await _rig(cfg, [_tool("open_page", url=SHOP_URL), [{"text": "Open."}], *_booking_steps()])
    thread = await rig.talk.create_thread(rig.user_id, rig.bot_id)
    await send(rig, rig.user_id, rig.bot_id, thread.id, f"Open {SHOP_URL}")
    await wait_idle(rig.runner, timeout=WAIT)
    await rig.routines.create(rig.user_id, RoutineDraft(
        bot_id=rig.bot_id, name="Bus tickets", instructions=YOUR_MESSAGE, schedule=SCHEDULE, created_by="user"))
    rig.clock.now = NOW + timedelta(minutes=9)
    await rig.scheduler.tick()
    await wait_idle(rig.runner, timeout=WAIT)

    # Browsing and typing ran; the POST form's Continue hit the hard floor and the run stopped on its card.
    acts = _acts(rig.cfg)
    assert acts == [("click", "do", "allowed"), *[("click", "do", "allowed"), ("type", "do", "allowed")] * 3,
                    ("click", "ask", "hard_floor")]
    [card] = await rig.open_cards()
    assert card.thread_id != thread.id                       # the routine's run log, not your chat
    assert (card.steps[0].title, card.steps[0].floor) == ("Click 'Continue'", "commit_click")
    assert rig.page.state_name == "tickets"                  # Continue never ran: no booking, no payment
