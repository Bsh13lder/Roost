"""The Stuck flow's run side (Piece A, Task 5): a blocked chat run stops and
leaves a Stuck card, the bot shows Stuck while a card is open, and a continue
run blocked again on the same host marks its card blocked (rung 4)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import get_args
from uuid import uuid4

import pytest

import roost.talk.runner as runner_module
import roost.talk.tool_runner as tool_runner_module
from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import CHAT_PREVIEW_CHARS
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.stuck import Block
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.rooms.models import RoomContext
from roost.rooms.store import RoomStore
from roost.stuck.models import CardDraft, CardState, StuckCard, stuck_card_out
from roost.stuck.store import StuckStore
from roost.stuck.texts import (
    already_waiting_line, blocked_line, continue_text, stuck_line, stuck_message_body,
)
from roost.talk.chats import chat_preview, chat_rows
from roost.talk.instructions import blocked_result_text
from roost.talk.notices import preview
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, MessageKind, TalkStore
from roost.talk.turn import RunInputs, _may_open_cards
from roost.work.models import ORIGIN_CARD, ORIGIN_YOU, RunOutcome, WorkDraft, WorkItem, WorkKind, WorkState
from roost.work.runs import RunLog
from team_helpers import (
    GatedModel, Rig, ask, frames_so_far, make_bot, make_rig, say, send, team_model, until, wait_idle,
)

SHOP = "https://shop.example/"
NEWS = "https://news.example/"
BANK = "https://bank.example/"

CHALLENGE = PageText(url=SHOP, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)
CLEAR = PageText(url=SHOP, title="Kettles", text="Blue kettle, 30 EUR. Red kettle, 35 EUR.", truncated=False,
                 status=200)
# A code check is a wall that still opens a card (a sign-in page no longer does, owner 2026-11-03).
LOGIN_WALL = PageText(url=BANK, title="Two-step verification", text="Enter the verification code we sent to your phone.",
                      truncated=False, status=200)
SHOP_LOGIN = PageText(url=SHOP, title="Two-step verification", text="Enter the verification code we sent to your phone.",
                      truncated=False, status=200)
ROOM = RoomContext(room_id="r1", name="Saturday", members=(), coordinator_id=None)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture(autouse=True)
def _no_challenge_wait(monkeypatch):
    """Rung 1 waits STUCK_CHALLENGE_WAIT_SECONDS (8 s) before it repeats the call; tests don't."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _call(call_id: str, name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


def _open_step(url: str, call_id: str = "p"):
    return [_call(call_id, "open_page", url=url), TurnDone("tool_use")]


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _status(rig: Rig, user_id: str, bot_id: str) -> BotStatus:
    return (await rig.bots.get(user_id, bot_id)).status


def _draft(bot_id: str, thread_id: str) -> CardDraft:
    return CardDraft(bot_id=bot_id, thread_id=thread_id, work_item_id=None,
                     block=Block(reason="login", url=BANK, host="bank.example"), request="pay the bill",
                     tainted=False)


async def _run_in_new_chat(rig: Rig, user_id: str, bot_id: str, text: str):
    """Send ``text`` in a new chat with ``bot_id`` and wait until the run is over; returns the thread."""
    thread = await rig.talk.create_thread(user_id, bot_id)
    await send(rig, user_id, bot_id, thread.id, text)
    await wait_idle(rig.runner, timeout=8)
    return thread


async def _clear(rig: Rig, stuck: StuckStore, user_id: str, card: StuckCard) -> tuple[StuckCard, WorkItem]:
    """What Task 7's ``/clear`` does (without the control hold and the frame):
    close the card, post the continue line, queue the continue item."""
    item_id = str(uuid4())
    cleared = await stuck.close(user_id, card.id, CardState.CLEARED, answer_item_id=item_id)
    text = continue_text(cleared)
    line = await rig.talk.add_message(user_id, cleared.thread_id, "user", text, cleared.tainted, kind="card_answer")
    item = await rig.runner.submit(user_id, WorkDraft(
        bot_id=cleared.bot_id, thread_id=cleared.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
        body=text, tainted=cleared.tainted, message_id=line.id, link_scope=(cleared.url,),
    ), item_id=item_id)
    return cleared, item


def _item(kind: WorkKind, n: int = 0) -> WorkItem:
    return WorkItem(
        id=f"i{n}", user_id="u", bot_id="b", thread_id="t", kind=kind, origin=ORIGIN_YOU, body="hi",
        tainted=False, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r",
        inflight=None, result=None, result_tainted=False, created_at="2026-10-14T10:00:00+00:00",
        updated_at="2026-10-14T10:00:00+00:00",
    )


def _message(body: str, *, role: str = "bot", kind: str = "text") -> Message:
    return Message(id="m", user_id="u", thread_id="t", role=role, body=body, tainted=False, seq=1,
                   created_at="2026-10-14T10:00:00+00:00", kind=kind)


class _HeldFinish(RunLog):
    """A run log whose ``finish`` waits for ``release``. ``_run_batch`` calls it
    after the turn and after the run's own status settle, so the run is held
    while it ends: the status is already settled, and the drain task is alive."""

    def __init__(self, config) -> None:
        super().__init__(config)
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    async def finish(self, user_id: str, run_id: str, outcome: RunOutcome) -> None:
        self.reached.set()
        await self.release.wait()
        await super().finish(user_id, run_id, outcome)


async def _ending_run(cfg, user_id: str, bot_id: str) -> tuple[Rig, _HeldFinish]:
    """Send "hello" to ``bot_id`` and hold that run at ``finish``: it has
    answered and settled its status, and its drain task is still alive."""
    runs = _HeldFinish(cfg)
    rig = make_rig(cfg, team_model({"Helper": [say("Done.")]}))
    rig = replace(rig, runner=TurnRunner(cfg, rig.bots, rig.talk, rig.events, rig.desks, rig.model,
                                         ActivityBoard(), runs=runs))
    thread = await rig.talk.create_thread(user_id, bot_id)
    await send(rig, user_id, bot_id, thread.id, "hello")
    await asyncio.wait_for(runs.reached.wait(), timeout=3)
    return rig, runs


async def test_a_challenge_that_stays_ends_the_run_with_a_stuck_card(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        [_call("n", "open_page", url=NEWS), _call("s", "open_page", url=SHOP), TurnDone("tool_use")],
        say("never asked"),
    ]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    request = f"check {NEWS} then {SHOP}"
    item = await send(rig, user_id, bot.id, thread.id, request)
    await wait_idle(rig.runner, timeout=8)

    assert len(rig.model.requests) == 1                     # the turn stopped calling the model
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    assert (card.reason, card.host, card.url, card.thread_id, card.state) == (
        "challenge", "shop.example", SHOP, thread.id, CardState.OPEN)
    assert (card.work_item_id, card.request, card.tainted) == (item.id, request, True)   # it read news.example
    [line] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert (line.role, line.author_bot_id, line.tainted, line.body) == ("bot", bot.id, True, stuck_message_body(card))
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK
    frames = await frames_so_far(sub)
    assert [f["card"] for f in frames if f["type"] == "stuck_card"] == [stuck_card_out(card).model_dump(mode="json")]
    assert [f["status"] for f in frames if f["type"] == "bot_status"][-1] == "stuck"


async def test_a_challenge_that_clears_after_the_wait_opens_no_card_and_the_run_goes_on(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), say("The blue kettle is 30 EUR.")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CLEAR)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    assert len(rig.model.requests) == 2
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind, m.body) for m in messages][1:] == [("bot", "text", "The blue kettle is 30 EUR.")]
    assert await StuckStore(cfg).open_for_bot(user_id, bot.id) is None
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_ask_for_help_opens_an_asked_card(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    reason = "The council site wants a payment approval on your phone"
    rig = make_rig(cfg, team_model({"Helper": [
        [_call("h", "ask_for_help", reason=reason, suggest_main_browser=True), TurnDone("tool_use")],
        say("never asked"),
    ]}))
    thread = await _run_in_new_chat(rig, user_id, bot.id, "renew my parking permit")

    assert len(rig.model.requests) == 1
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    assert (card.reason, card.note, card.suggest_main_browser, card.url, card.request) == (
        "asked", reason, True, "", "renew my parking permit")
    [line] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert json.loads(line.body)["line"] == stuck_line(card)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_blocked_turn_that_said_nothing_leaves_no_empty_bubble(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP)]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind) for m in messages] == [("user", "text"), ("bot", "stuck")]
    frames = await frames_so_far(sub)
    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    assert any(f["type"] == "message_done" and f["message_id"] == placeholder_id for f in frames)
    assert placeholder_id not in {m.id for m in messages}


async def test_a_blocked_turn_keeps_what_it_said_before_the_block(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [[TextDelta("Let me look at the shop."), *_open_step(SHOP)]]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind, m.body) for m in messages][1:2] == [("bot", "text", "Let me look at the shop.")]
    assert [m.kind for m in messages] == ["text", "text", "stuck"]


async def test_a_handoff_run_that_hits_a_block_opens_no_card_and_reports_it_loudly(cfg, user_id):
    chief = await make_bot(cfg, user_id, "Chief", "leads the team")
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig = make_rig(cfg, team_model({
        "Chief": [[ask("c1", "Scout", f"price the kettle at {SHOP}"), TurnDone("tool_use")],
                  say("Scout couldn't get into the shop.")],
        "Scout": [_open_step(SHOP), say("The shop stopped me with a check that I'm human.")],
    }))
    rig.desks.for_bot(scout.id).serve(SHOP, CHALLENGE)
    await _run_in_new_chat(rig, user_id, chief.id, f"price the kettle at {SHOP}")

    scout_requests = [r for r in rig.model.requests if r.agent == "Scout"]
    assert len(scout_requests) == 2                         # R5: the run went on and its model answered
    assert _tool_texts(scout_requests[-1]) == [
        blocked_result_text(Block(reason="challenge", url=SHOP, host="shop.example"))]
    assert await StuckStore(cfg).list_open(user_id) == ()
    assert await _status(rig, user_id, scout.id) is BotStatus.RESTING


@pytest.mark.parametrize(("kinds", "room", "expected"), [
    ((), None, False),                                      # a run outside the queue
    ((WorkKind.MESSAGE,), None, True),
    ((WorkKind.CARD_ANSWER,), None, True),
    ((WorkKind.MESSAGE, WorkKind.CARD_ANSWER), None, True),
    ((WorkKind.HANDOFF,), None, False),
    ((WorkKind.MESSAGE, WorkKind.HANDOFF), None, False),
    ((WorkKind.ROOM_POST,), None, False),
    ((WorkKind.ROUTINE,), None, False),
    ((WorkKind.TRIGGER,), None, False),
    ((WorkKind.MESSAGE,), ROOM, False),                     # your own message, but in a room
])
def test_cards_open_only_in_runs_of_your_own_messages_and_continue_items(kinds, room, expected):
    inputs = RunInputs(items=tuple(_item(kind, n) for n, kind in enumerate(kinds)), room=room)
    assert _may_open_cards(inputs) is expected


async def test_a_continue_run_blocked_again_on_the_same_host_marks_the_card_blocked(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(SHOP, "p2")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    card = await stuck.open_for_bot(user_id, bot.id)
    sub = rig.events.subscribe(user_id)

    await _clear(rig, stuck, user_id, card)
    await wait_idle(rig.runner, timeout=8)

    assert (await stuck.get(user_id, card.id)).state is CardState.BLOCKED
    assert await stuck.open_for_bot(user_id, bot.id) is None            # rung 4: no new card on the same host
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.author_bot_id, m.body) for m in messages if m.role == "bot" and m.kind == "text"] == [
        (bot.id, blocked_line("shop.example", request))]
    assert len([m for m in messages if m.kind == "stuck"]) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING
    assert [f["card"]["state"] for f in await frames_so_far(sub) if f["type"] == "stuck_card"] == ["blocked"]


async def test_a_different_wall_on_the_same_site_after_clearing_opens_a_new_card(cfg, user_id):
    """R12: the check was cleared, and the same site now wants a code. That is progress, not
    the same block again: a new card opens and keeps the first request."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(SHOP, "p2")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CHALLENGE, SHOP_LOGIN)   # open + rung-1 repeat, then a code check
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    first = await stuck.open_for_bot(user_id, bot.id)
    assert first.reason == "challenge"

    _, continue_item = await _clear(rig, stuck, user_id, first)
    await wait_idle(rig.runner, timeout=8)

    second = await stuck.open_for_bot(user_id, bot.id)
    assert second.id != first.id
    assert (second.reason, second.host, second.request, second.work_item_id) == (
        "code", "shop.example", request, continue_item.id)
    assert (await stuck.get(user_id, first.id)).state is CardState.CLEARED
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert len([m for m in messages if m.kind == "stuck"]) == 2
    assert not [m for m in messages if m.kind == "text" and m.role == "bot"]   # no "Blocked: ..." line
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_asking_for_help_after_clearing_opens_a_new_card(cfg, user_id):
    """R12: a bot that asks for help on the page it just got into is not blocked by that page again."""
    bot = await make_bot(cfg, user_id, "Helper")
    reason = "The shop wants a payment approval on your phone"
    rig = make_rig(cfg, team_model({"Helper": [
        _open_step(SHOP),                                                     # run 1: the check stays
        _open_step(SHOP, "p2"),                                               # run 2: the page opens now
        [_call("h", "ask_for_help", reason=reason), TurnDone("tool_use")],    # ... and then it asks
    ]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CHALLENGE, CLEAR)
    stuck = StuckStore(cfg)
    request = f"buy the kettle at {SHOP}"
    await _run_in_new_chat(rig, user_id, bot.id, request)
    first = await stuck.open_for_bot(user_id, bot.id)

    await _clear(rig, stuck, user_id, first)
    await wait_idle(rig.runner, timeout=8)

    second = await stuck.open_for_bot(user_id, bot.id)
    assert second.id != first.id
    assert (second.reason, second.host, second.note, second.request) == ("asked", "shop.example", reason, request)
    assert (await stuck.get(user_id, first.id)).state is CardState.CLEARED
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_card_done_in_the_main_brave_never_ends_blocked(cfg, user_id):
    """R13: the user did the step in their own Brave. If the bot opens the same page again and it is
    still blocked, that is a new problem to show, never the end of the task."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(SHOP, "p2")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    first = await stuck.open_for_bot(user_id, bot.id)
    assert await stuck.mark_main_opened(user_id, first.id) is not None      # "Use my main Brave"

    cleared, continue_item = await _clear(rig, stuck, user_id, first)       # "Done, carry on"
    await wait_idle(rig.runner, timeout=8)

    assert cleared.main_opened is True
    assert ("user", continue_text(cleared)) in [(t.role, t.text) for t in rig.model.requests[1].turns]
    second = await stuck.open_for_bot(user_id, bot.id)
    assert second.id != first.id
    assert (second.reason, second.host, second.request, second.work_item_id, second.main_opened) == (
        "challenge", "shop.example", request, continue_item.id, False)
    assert (await stuck.get(user_id, first.id)).state is CardState.CLEARED
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert len([m for m in messages if m.kind == "stuck"]) == 2
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_continue_run_blocked_on_another_host_opens_a_new_card_with_the_first_request(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(BANK, "p2")]}))
    desk = rig.desks.for_bot(bot.id)
    desk.serve(SHOP, CHALLENGE)
    desk.serve(BANK, LOGIN_WALL)
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP} and pay for it at {BANK}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    first = await stuck.open_for_bot(user_id, bot.id)

    _, continue_item = await _clear(rig, stuck, user_id, first)
    await wait_idle(rig.runner, timeout=8)

    second = await stuck.open_for_bot(user_id, bot.id)
    assert second.id != first.id
    assert (second.reason, second.host, second.request, second.work_item_id) == (
        "code", "bank.example", request, continue_item.id)
    assert (await stuck.get(user_id, first.id)).state is CardState.CLEARED
    assert len([m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]) == 2
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_continue_line_reaches_the_model_as_your_turn_and_the_run_finishes(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        _open_step(SHOP), [_call("r", "read_page"), TurnDone("tool_use")], say("The blue kettle is 30 EUR."),
    ]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CHALLENGE, CLEAR)   # open + rung-1 repeat, then cleared
    stuck = StuckStore(cfg)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")
    card = await stuck.open_for_bot(user_id, bot.id)

    cleared, _ = await _clear(rig, stuck, user_id, card)
    await wait_idle(rig.runner, timeout=8)

    assert ("user", continue_text(cleared)) in [(t.role, t.text) for t in rig.model.requests[1].turns]
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind) for m in messages] == [
        ("user", "text"), ("bot", "stuck"), ("user", "card_answer"), ("bot", "text")]
    assert messages[-1].body == "The blue kettle is 30 EUR."
    assert (await stuck.get(user_id, card.id)).state is CardState.CLEARED
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_a_new_message_while_a_card_is_open_is_answered_and_the_bot_stays_stuck(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), say("Yes, I'm waiting for you on the shop.")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    await send(rig, user_id, bot.id, thread.id, "are you still on it?")
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [m.body for m in messages if m.role == "bot" and m.kind == "text"] == [
        "Yes, I'm waiting for you on the shop."]
    assert len(await StuckStore(cfg).list_open(user_id)) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_block_in_another_chat_while_a_card_is_open_shows_the_open_card_there(cfg, user_id):
    """One open card per bot: a second blocked run opens no second card, and its own chat is never left empty."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(BANK, "p2")]}))
    desk = rig.desks.for_bot(bot.id)
    desk.serve(SHOP, CHALLENGE)
    desk.serve(BANK, LOGIN_WALL)
    stuck = StuckStore(cfg)
    first_chat = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")
    card = await stuck.open_for_bot(user_id, bot.id)

    second_chat = await _run_in_new_chat(rig, user_id, bot.id, f"pay the bill at {BANK}")

    assert [c.id for c in await stuck.list_open(user_id)] == [card.id]
    [shown] = [m for m in await rig.talk.list_messages(user_id, second_chat.id) if m.kind == "stuck"]
    assert (shown.role, shown.author_bot_id, shown.body) == ("bot", bot.id, stuck_message_body(card))
    assert len([m for m in await rig.talk.list_messages(user_id, first_chat.id) if m.kind == "stuck"]) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_block_in_another_chat_while_a_card_is_open_says_what_it_did_not_finish(cfg, user_id):
    """The second run's own task is never dropped silently behind the older card: in its chat the
    bot says it is already waiting on you, for which site, and what it didn't finish. The run that
    opened the card says no such line."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        _open_step(SHOP),
        [_call("n", "open_page", url=NEWS), _call("p2", "open_page", url=BANK), TurnDone("tool_use")],
    ]}))
    desk = rig.desks.for_bot(bot.id)
    desk.serve(SHOP, CHALLENGE)
    desk.serve(BANK, LOGIN_WALL)
    first_chat = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    sub = rig.events.subscribe(user_id)

    second_chat = await _run_in_new_chat(rig, user_id, bot.id, f"check {NEWS}, then pay the bill at {BANK}")

    second = await rig.talk.list_messages(user_id, second_chat.id)
    assert [(m.role, m.kind) for m in second] == [("user", "text"), ("bot", "text"), ("bot", "stuck")]
    said, shown = second[1], second[2]
    assert (said.author_bot_id, said.body) == (
        bot.id, already_waiting_line("shop.example", f"check {NEWS}, then pay the bill at {BANK}"))
    assert said.tainted is True                     # this run read news.example
    assert (shown.body, shown.tainted) == (stuck_message_body(card), card.tainted)
    first = await rig.talk.list_messages(user_id, first_chat.id)
    assert [(m.role, m.kind) for m in first] == [("user", "text"), ("bot", "stuck")]
    said_live = [f["message"]["body"] for f in await frames_so_far(sub)
                 if f["type"] == "message" and f["thread_id"] == second_chat.id]
    assert said.body in said_live


async def test_settle_leaves_a_running_bot_on_it_and_settles_when_its_run_ends(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, GatedModel(["Done."]))
    stuck = StuckStore(cfg)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await until(lambda: len(rig.model.requests) == 1)            # the run is on, held inside the model
    card = await stuck.open(user_id, _draft(bot.id, thread.id))

    await rig.runner.settle(user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.ON_IT    # not now: it settles when the run ends

    rig.model.release.set()
    await wait_idle(rig.runner)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the run's own settle, then settle's, saw the card

    await stuck.close(user_id, card.id, CardState.GIVEN_UP)
    await rig.runner.settle(user_id, bot.id)                     # no drain task: at once
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_give_up_while_a_run_ends_settles_after_the_run(cfg, user_id):
    """R9: Give up pressed while a run is ending (the run already settled itself
    to Stuck, its drain task is still alive) must not leave the bot Stuck with no
    open card. The run is held at ``finish``, not in the model: a run held in the
    model would settle after the card closed, and show Resting even with the old
    no-op ``settle``."""
    bot = await make_bot(cfg, user_id, "Helper")
    stuck = StuckStore(cfg)
    card = await stuck.open(user_id, _draft(bot.id, (await TalkStore(cfg).create_thread(user_id, bot.id)).id))
    rig, runs = await _ending_run(cfg, user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the run's own settle saw the card

    await stuck.close(user_id, card.id, CardState.GIVEN_UP)          # what /give-up does to the card
    await rig.runner.settle(user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the drain task is alive: not yet

    runs.release.set()
    await wait_idle(rig.runner)
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING
    assert rig.runner._settling == frozenset()                       # the settle task ended and was let go


async def test_a_settle_that_fails_after_the_run_is_logged(cfg, user_id, caplog, monkeypatch):
    """Nobody awaits the settle that runs after a drain task ends, so its error is logged, never lost."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig, runs = await _ending_run(cfg, user_id, bot.id)

    async def _db_gone(user_id: str, bot_id: str) -> None:
        raise RuntimeError("database is gone")

    monkeypatch.setattr(rig.runner, "_settle_status", _db_gone)
    await rig.runner.settle(user_id, bot.id)
    runs.release.set()
    await wait_idle(rig.runner)

    assert f"Settling the status after a run failed for bot {bot.id}" in caplog.text
    assert "RuntimeError: database is gone" in caplog.text
    assert rig.runner._settling == frozenset()


async def test_boot_puts_a_bot_with_an_open_card_back_to_stuck(cfg, user_id):
    """Review Focus #5: the old process died between opening the card and settling (the bot was On it)."""
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    card = await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))
    await BotStore(cfg).set_status(user_id, bot.id, BotStatus.ON_IT)
    app = create_app()
    async with app.router.lifespan_context(app):
        assert (await app.state.bots.get(user_id, bot.id)).status is BotStatus.STUCK
        assert [c.id for c in await app.state.stuck.list_open(user_id)] == [card.id]


async def test_boot_leaves_an_off_duty_bot_with_an_open_card_off_duty(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.bots.set_off_duty(user_id, bot.id, True)
    await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))

    await rig.runner.restore_stuck_on_boot()

    assert await _status(rig, user_id, bot.id) is BotStatus.OFF_DUTY


async def test_back_on_duty_with_an_open_card_shows_stuck(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.runner.set_off_duty(user_id, bot.id, True)
    await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))

    back = await rig.runner.set_off_duty(user_id, bot.id, False)
    await wait_idle(rig.runner)

    assert back.status is BotStatus.STUCK
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_the_card_keeps_the_request_up_to_its_cap(cfg, user_id, monkeypatch):
    monkeypatch.setattr(runner_module, "STUCK_REQUEST_MAX_CHARS", 12)
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP)]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    assert (await StuckStore(cfg).open_for_bot(user_id, bot.id)).request == "price the ke"


def test_a_stuck_card_previews_as_stuck_on_its_host():
    assert chat_preview(_message(json.dumps({"card_id": "c1", "host": "shop.example"}), kind="stuck")) == (
        "Stuck on shop.example", "card")
    assert chat_preview(_message(json.dumps({"card_id": "c1", "host": ""}), kind="stuck")) == (
        "Needs your help", "card")
    assert chat_preview(_message("not json", kind="stuck")) == ("Needs your help", "card")
    assert chat_preview(_message("[1, 2]", kind="stuck")) == ("Needs your help", "card")


async def test_a_continue_line_previews_like_your_own_words(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot.id)
    text = "I cleared the block on shop.example. Read the page again and carry on with: price the kettle"
    await talk.add_message(user_id, thread.id, "user", text, kind="card_answer")
    [row] = await chat_rows(user_id=user_id, bots=BotStore(cfg), talk=talk, rooms=RoomStore(cfg))
    assert (row["preview"], row["preview_kind"], row["from_you"]) == (preview(text, CHAT_PREVIEW_CHARS), "text", True)


def test_the_card_message_kinds_and_the_continue_origin_exist():
    assert {"stuck", "card_answer"} <= set(get_args(MessageKind))
    assert ORIGIN_CARD == "you, after a Stuck card"
