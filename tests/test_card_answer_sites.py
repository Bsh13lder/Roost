"""The run that carries on after a card keeps the sites it may open (Gela, 2026-11-04).

You asked "Now enter my Wizz Air with my Google account and try to start booking for two persons." The run opened
www.wizzair.com itself (``fresh_open``), asked you to sign in, and you signed in from the card. The run that carried
on then met an "Open www.wizzair.com" card for the booking page: the site the stuck card was about, and the site the
run of your own message had opened itself, were not carried into the continue item. They are now, after a Stuck
card you cleared and after an Ask card you answered. A page never widens the scope: a site only a page names asks."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from roost.approvals.executor import ApprovedCalls
from roost.approvals.service import ApprovalService
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk import DeskFactory, PageText
from roost.desk.control import ControlLock
from roost.desk.main_browser import FakeMainBrowser
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import Gate
from roost.talk.new_site import PageOpens
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.talk.carry import card_site_entries, carried_sites
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkItem, WorkKind, WorkState
from roost.work.queue import WorkQueue
from cu_run_helpers import make_cu_rig, run_step
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

REQUEST = "Now enter my Wizz Air with my Google account and try to start booking for two persons."
FRONT = "https://www.wizzair.com/"
BOOKING = "https://www.wizzair.com/en-gb/booking/select-flight/BCN/KUT/2026-12-13/null/2/0/0/null"
PLANTED = "https://cheap-flights.example/deal"
FRONT_PAGE = PageText(url=FRONT, title="Wizz Air", text=f"Fly cheap. Our partner: {PLANTED}", truncated=False,
                      status=200)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@dataclass(frozen=True)
class _Rig:
    runner: TurnRunner
    talk: TalkStore
    desks: DeskFactory
    cards: ApprovalStore
    answers: ApprovalService
    stuck: StuckStore
    stuck_service: StuckService


def _rig(cfg, script) -> _Rig:
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    cards, sessions, stuck, control = ApprovalStore(cfg), SessionOks(), StuckStore(cfg), ControlLock()
    domain = build_domain_tools(cfg, events, sessions=sessions, desks=desks)
    model = RecordingModel(ScriptedTeamModel({"Gela": script}))
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard(),
                        approvals=ApprovalWiring(cards, sessions, None, None), domain=domain,
                        control=control, stuck=stuck)
    executor = ApprovedCalls(runner.domain, Gate(cfg), talk, events, pages=PageOpens(bots, desks))
    answers = ApprovalService(cards, talk, events, runner, executor, sessions)
    stuck_service = StuckService(stuck, talk, events, runner, control, FakeMainBrowser())
    return _Rig(runner, talk, desks, cards, answers, stuck, stuck_service)


def _call(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _stuck_then_cleared(cfg, user_id: str, after: list) -> tuple[_Rig, str]:
    """Your message: the run opens Wizz Air itself and asks you to sign in. You clear the card; ``after`` is the
    continue run's script."""
    bot = await make_bot(cfg, user_id, "Gela")
    script = [_call("c1", "open_page", url=FRONT),
              _call("c2", "request_sign_in", site="www.wizzair.com", why="Sign in with your Google account"),
              *after]
    rig = _rig(cfg, script)
    rig.desks.for_bot(bot.id).serve(FRONT, FRONT_PAGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, REQUEST)    # type: ignore[arg-type]
    await wait_idle(rig.runner, timeout=8)
    card = await rig.stuck.open_for_bot(user_id, bot.id)
    assert card is not None and card.host == "www.wizzair.com"
    await rig.stuck_service.clear(user_id, card.id)
    await wait_idle(rig.runner, timeout=8)
    return rig, bot.id


async def test_after_you_clear_the_stuck_card_the_bot_opens_the_booking_page_with_no_card(cfg, user_id):
    rig, bot_id = await _stuck_then_cleared(cfg, user_id, [_call("c3", "open_page", url=BOOKING),
                                                           say("Started booking.")])
    assert tuple(await rig.cards.list_open(user_id)) == ()            # no "Open www.wizzair.com" card
    assert BOOKING in rig.desks.for_bot(bot_id).open_page_calls


async def test_the_continue_run_is_still_your_own_chat_so_any_safe_site_opens(cfg, user_id):
    """Owner, 2026-11-05 ("Gela too much hard floors, Grok is much freer"): your Yes or your cleared card carries
    your own chat on, so the run opens any safe site with no Open card, as your own message's run does."""
    rig, bot_id = await _stuck_then_cleared(cfg, user_id, [_call("c3", "open_page", url="https://www.kiwi.com/"),
                                                           say("Opened it.")])
    assert tuple(await rig.cards.list_open(user_id)) == ()
    assert "https://www.kiwi.com/" in rig.desks.for_bot(bot_id).open_page_calls


async def test_an_unsafe_address_still_never_opens_in_the_continue_run(cfg, user_id):
    rig, bot_id = await _stuck_then_cleared(cfg, user_id, [_call("c3", "open_page", url="http://localhost/admin"),
                                                           say("Couldn't.")])
    assert "http://localhost/admin" not in rig.desks.for_bot(bot_id).open_page_calls


async def test_the_continue_item_carries_the_cards_site_and_the_sites_the_run_opened_itself(cfg, user_id):
    rig, _ = await _stuck_then_cleared(cfg, user_id, [say("Done.")])
    assert await rig.stuck.list_open(user_id) == ()
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT answer_item_id FROM stuck_cards WHERE user_id = ?",
                                      (user_id,))).fetchone()
    item = await WorkQueue(cfg).get(user_id, row["answer_item_id"])
    assert item is not None
    assert set(item.link_scope) == {FRONT, "host:wizzair.com"}
    assert not any("cheap-flights" in entry for entry in item.link_scope)   # a page's link never rides along


async def test_after_your_yes_on_an_ask_card_the_site_the_run_opened_still_opens(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Gela")                              # Ask every time: add_task asks
    script = [_call("c1", "open_page", url=FRONT), _call("c2", "add_task", title="Book Wizz Air for two"),
              _call("c3", "open_page", url=BOOKING), say("Started booking.")]
    rig = _rig(cfg, script)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, REQUEST)    # type: ignore[arg-type]
    await wait_idle(rig.runner, timeout=8)
    [card] = await rig.cards.list_open(user_id)
    await rig.answers.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner, timeout=8)
    assert tuple(await rig.cards.list_open(user_id)) == ()
    assert BOOKING in rig.desks.for_bot(bot.id).open_page_calls


# -- on a Linux computer: the carried sites join the continue run's fence --------------------------------------

async def test_a_continue_run_on_a_linux_computer_browses_the_carried_site(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")   # names no site
    runner = rig.tool_runner(tainted=True, user_started=False, sees_records=True,
                             own_sites=frozenset({"shop.example"}))
    await run_step(runner, "look")
    assert rig.desk.guard_fences[-1].allows("shop.example")
    assert not rig.desk.guard_fences[-1].allows("partner.example")   # only the carried site, never a page's
    assert runner.own_sites == frozenset({"shop.example"})


async def test_the_sites_a_fresh_run_opened_are_what_it_hands_on(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://www.shop.example/")
    assert runner.own_sites == frozenset({"shop.example"})


def _item(kind: WorkKind, scope: tuple[str, ...]) -> WorkItem:
    return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin=ORIGIN_CARD, body="go",
                    tainted=True, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED,
                    run_id="r", inflight=None, result=None, result_tainted=False, created_at="now",
                    updated_at="now", link_scope=scope)


def test_only_a_continue_items_site_entries_are_carried_in():
    assert carried_sites([_item(WorkKind.CARD_ANSWER, (FRONT, "host:wizzair.com"))]) == frozenset({"wizzair.com"})
    assert carried_sites([_item(WorkKind.HANDOFF, ("host:cheap-flights.example",))]) == frozenset()


def test_the_cards_own_site_entries():
    assert card_site_entries(FRONT) == (FRONT, "host:wizzair.com")
    assert card_site_entries("") == ()
    assert card_site_entries("http://localhost/") == ("http://localhost/",)


async def test_a_routine_run_logs_card_answer_is_not_your_own_chat(cfg, user_id):
    """A card answered in a routine's run log carries a routine on, not your chat: a new site still asks there."""
    bot = await make_bot(cfg, user_id, "Gela")
    rig = _rig(cfg, [_call("c1", "open_page", url="https://www.kiwi.com/"), say("Asked.")])
    thread = await rig.talk.create_thread(user_id, bot.id, "Price check", kind="routine")
    await rig.runner.submit(user_id, WorkDraft(bot_id=bot.id, thread_id=thread.id, kind=WorkKind.CARD_ANSWER,
                                               origin=ORIGIN_CARD, body="Yes, go on.", tainted=True))
    await wait_idle(rig.runner, timeout=8)
    assert "https://www.kiwi.com/" not in rig.desks.for_bot(bot.id).open_page_calls
