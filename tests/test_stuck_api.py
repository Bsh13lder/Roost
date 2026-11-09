"""The Stuck card's buttons over HTTP (stuck flow, Task 7; design §2, R6, R8–R10).

``GET /api/stuck`` lists your open cards. ``/clear`` (Give it back, Try again,
Done, carry on) posts your continue line and queues a ``card_answer`` item.
``/give-up`` ends the task. Both settle the bot's status. ``/open-in-main-browser`` opens the card's address
in your own Brave through ``app.state.main_browser``. Here that is always
``FakeMainBrowser``: no test opens a real browser.

These tests use ``httpx.AsyncClient`` on the test's own event loop, not
``TestClient``. ``/clear`` starts the bot's drain task, and ``wait_idle`` must
see it finish before the test ends.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

import roost.talk.runner as runner_module
import roost.talk.tool_runner as tool_runner_module
from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk import DeskUnavailable, PageText
from roost.desk.main_browser import FakeMainBrowser
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.stuck.models import CardClosed, CardDraft, CardState, StuckCard
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, TalkStore
from roost.work.models import ORIGIN_CARD, WorkKind, WorkState
from roost.work.queue import WorkQueue
from team_helpers import make_bot, say, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
PASSWORD = "pw-123456"
SHOP_URL = "https://shop.example/kettle"
REQUEST = "Find the price of the blue kettle"
CLOSED = {"detail": "This card is already closed."}
NOT_FOUND = {"detail": "Card not found"}
BUTTONS = ("clear", "give-up", "open-in-main-browser")
CARD_FIELDS = {"id", "bot_id", "thread_id", "reason", "host", "url", "note", "suggest_main_browser", "tainted",
               "main_opened", "state", "created_at", "closed_at", "sign_in", "secret_field"}

CHALLENGE = PageText(url=SHOP_URL, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)
CLEARED = PageText(url=SHOP_URL, title="Blue kettle", text="Blue kettle, 1.7 litres: 25 EUR. In stock.",
                   truncated=False, status=200)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@asynccontextmanager
async def _signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    """``username`` logged in over HTTP. On the way out, every drain task the requests started has finished."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        login = await client.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=O)
        assert login.status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _card(cfg, user_id: str, bot_id: str, *, url: str = SHOP_URL, reason: str = "challenge",
                note: str = "", tainted: bool = True) -> StuckCard:
    """An open Stuck card in a new chat with ``bot_id``, the way Task 5's run leaves one."""
    thread = await TalkStore(cfg).create_thread(user_id, bot_id)
    block = Block(reason=reason, url=url, host=host_of_url(url), note=note)
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot_id, thread_id=thread.id, work_item_id=None, block=block, request=REQUEST, tainted=tainted,
    ))


async def _frames(app, user_id: str, frame_type: str) -> list[dict]:
    return [frame for frame in await app.state.events.since(user_id, 0) if frame["type"] == frame_type]


async def _continue_items(cfg, user_id: str) -> int:
    async with db_session(cfg) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM work_items WHERE user_id = ? AND kind = 'card_answer'", (user_id,),
        )).fetchone()
    return row[0]


async def _lines(app, user_id: str, card: StuckCard, kind: str) -> list[Message]:
    return [m for m in await app.state.talk.list_messages(user_id, card.thread_id) if m.kind == kind]


def _service_with(app, store: StuckStore, main_browser) -> StuckService:
    return StuckService(store, app.state.talk, app.state.events, app.state.turns, app.state.control, main_browser)


def _use_model(app, model) -> TurnRunner:
    """Drain with a scripted model. The service is rebuilt on the new runner, so
    ``/clear`` queues its continue item on the runner that runs it."""
    turns = TurnRunner(
        app.state.config, app.state.bots, app.state.talk, app.state.events, app.state.desks, model,
        app.state.activity_board, rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck,
    )
    app.state.turns = turns
    app.state.stuck_service = _service_with(app, app.state.stuck, app.state.main_browser)
    return turns


def _open_shop():
    return [ToolCallRequested(id="open-shop", name="open_page", arguments={"url": SHOP_URL}), TurnDone("tool_use")]


def _read_again():
    return [ToolCallRequested(id="read-again", name="read_page", arguments={}), TurnDone("tool_use")]


class _ReadBeforeTheOtherPress(StuckStore):
    """``get`` answers the card as this press read it, just before another press closed it."""

    def __init__(self, config, snapshot: StuckCard) -> None:
        super().__init__(config)
        self._snapshot = snapshot

    async def get(self, user_id: str, card_id: str) -> StuckCard | None:
        return self._snapshot


class _GivenUpWhileOpening:
    """A main Brave that is slow enough for the card to be given up in another tab while it opens."""

    def __init__(self, store: StuckStore, user_id: str, card_id: str) -> None:
        self._store = store
        self._user_id = user_id
        self._card_id = card_id
        self.opened: tuple[tuple[str, str], ...] = ()

    async def open(self, bot_id: str, url: str) -> None:
        self.opened = (*self.opened, (bot_id, url))
        await self._store.close(self._user_id, self._card_id, CardState.GIVEN_UP)


def test_the_gateway_wires_the_stuck_routes_and_a_fake_main_browser():
    app = create_app()
    assert isinstance(app.state.main_browser, FakeMainBrowser)          # ROOST_DESK=fake: no keeper, no real Brave
    assert isinstance(app.state.stuck_service, StuckService)
    assert {"/api/stuck", "/api/stuck/{card_id}/clear", "/api/stuck/{card_id}/give-up",
            "/api/stuck/{card_id}/open-in-main-browser"} <= set(app.openapi()["paths"])


async def test_the_list_holds_only_your_open_cards_newest_first(cfg, alice):
    app = create_app()
    bob = await register_user(cfg, "bob", PASSWORD)
    helper, scout, quill = [await make_bot(cfg, alice.id, name) for name in ("Helper", "Scout", "Quill")]
    older = await _card(cfg, alice.id, helper.id)
    newer = await _card(cfg, alice.id, scout.id, reason="login")
    stopped = await _card(cfg, alice.id, quill.id)
    await StuckStore(cfg).close(alice.id, stopped.id, CardState.GIVEN_UP)
    await _card(cfg, bob.id, (await make_bot(cfg, bob.id, "Helper")).id)
    async with _signed_in(app, "alice") as client:
        listed = (await client.get("/api/stuck")).json()
    assert [card["id"] for card in listed] == [newer.id, older.id]
    assert set(listed[0]) == CARD_FIELDS                                  # no user_id, no request
    assert (listed[0]["reason"], listed[0]["host"], listed[0]["url"], listed[0]["state"]) == (
        "login", "shop.example", SHOP_URL, "open")


async def test_clear_queues_the_continue_item_and_gives_the_computer_back(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app.state.control.take(bot.id)                                        # the user took control from the card
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert r.status_code == 200
    assert (r.json()["id"], r.json()["state"]) == (card.id, "cleared") and r.json()["closed_at"]
    assert app.state.control.held(bot.id) is None
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert (line.role, line.tainted, line.author_bot_id) == ("user", True, None)
    assert line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {REQUEST}"
    stored = await StuckStore(cfg).get(alice.id, card.id)
    item = await WorkQueue(cfg).get(alice.id, stored.answer_item_id)
    assert (item.kind, item.origin, item.body, item.tainted) == (WorkKind.CARD_ANSWER, ORIGIN_CARD, line.body, True)
    assert (item.bot_id, item.thread_id, item.message_id, item.link_scope) == (
        bot.id, card.thread_id, line.id, (SHOP_URL, "host:shop.example"))   # the card's site too (2026-11-04)
    assert (item.depth, item.parent_item_id) == (0, None)                 # not a handoff
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["cleared"]
    assert "card_answer" in [f["message"]["kind"] for f in await _frames(app, alice.id, "message")]


async def test_try_again_posts_its_own_line(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json={"how": "try_again"}, headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == f"Try again on shop.example. Read the page again and carry on with: {REQUEST}"
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.body == line.body


@pytest.mark.parametrize("payload", [{"how": "gave_back"}, {}, None])
async def test_give_it_back_is_the_default_way_to_clear(cfg, alice, payload):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O, **({} if payload is None else {"json": payload}))
    assert r.status_code == 200
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {REQUEST}"


@pytest.mark.parametrize("payload", [{"how": "give_up"}, {"how": 3}, {"how": "try_again", "extra": 1}, {"other": "x"}])
async def test_clear_refuses_an_unknown_how_or_field(cfg, alice, payload):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json=payload, headers=O)
        still_open = await client.get("/api/stuck")
    assert r.status_code == 422
    assert [c["id"] for c in still_open.json()] == [card.id]                # a refused press closes nothing
    assert await _continue_items(cfg, alice.id) == 0


async def test_clearing_twice_queues_one_continue_item(cfg, alice):
    """Review Focus 3: Give it back pressed twice, by a double click or from two tabs."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        presses = await asyncio.gather(*(client.post(f"/api/stuck/{card.id}/clear", headers=O) for _ in range(2)))
        late = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert sorted(r.status_code for r in presses) == [200, 409]
    assert [r.json() for r in presses if r.status_code == 409] == [CLOSED]
    assert (late.status_code, late.json()) == (409, CLOSED)
    assert await _continue_items(cfg, alice.id) == 1
    assert len(await _lines(app, alice.id, card, "card_answer")) == 1
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["cleared"]


async def test_clear_works_with_no_control_hold(cfg, alice):
    """Review Focus 5: a restart forgets every hold, because ControlLock lives in
    memory, but the card is in the database. The restarted gateway holds nothing,
    and Give it back on the card still works."""
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app()                                                    # the gateway after the restart
    assert app.state.control.held(bot.id) is None
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    assert await _continue_items(cfg, alice.id) == 1
    assert app.state.control.held(bot.id) is None


async def test_clear_when_the_bot_cannot_run_does_not_leave_it_stuck(cfg, alice, monkeypatch):
    """R9: ``/clear`` settles the status. Here the continue run can't start (the
    daily run cap is reached), so no run settles it: without that settle the bot
    would keep showing Stuck with no open card. The continue item waits."""
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 0)
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await app.state.bots.set_status(alice.id, bot.id, BotStatus.STUCK)       # the run that left the card did this
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
    assert [f["status"] for f in await _frames(app, alice.id, "bot_status")] == ["resting"]
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.state is WorkState.QUEUED                                    # it runs after midnight
    assert "daily_limit" in [m.kind for m in await app.state.talk.list_messages(alice.id, card.thread_id)]


async def test_a_clear_that_fails_after_closing_the_card_still_publishes_it_and_settles_the_status(
    cfg, alice, monkeypatch, caplog,
):
    """I5: the card is already ``cleared`` when queuing the continue item fails. The face must hear
    of the closed card and the bot must not keep showing Stuck with no open card. The failure is
    logged with the ids (never the address or the request) and still raised."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await app.state.bots.set_status(alice.id, bot.id, BotStatus.STUCK)       # the run that left the card did this

    async def _queue_is_gone(*args, **kwargs):
        raise RuntimeError("the queue is gone")

    monkeypatch.setattr(app.state.turns, "submit", _queue_is_gone)
    service = _service_with(app, app.state.stuck, app.state.main_browser)
    with caplog.at_level(logging.ERROR, logger="roost.stuck.service"):
        with pytest.raises(RuntimeError, match="the queue is gone"):
            await service.clear(alice.id, card.id)

    assert (await StuckStore(cfg).get(alice.id, card.id)).state is CardState.CLEARED
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["cleared"]
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
    [record] = [r for r in caplog.records if r.name == "roost.stuck.service" and r.levelno == logging.ERROR]
    assert card.id in record.getMessage() and bot.id in record.getMessage()
    assert record.exc_info is not None and record.exc_info[0] is RuntimeError
    assert SHOP_URL not in record.getMessage() and REQUEST not in record.getMessage()


async def test_a_press_that_loses_the_race_posts_and_queues_nothing(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await StuckStore(cfg).close(alice.id, card.id, CardState.CLEARED)    # the other tab's press landed first
    service = _service_with(app, _ReadBeforeTheOtherPress(cfg, card), app.state.main_browser)
    with pytest.raises(CardClosed):
        await service.clear(alice.id, card.id)
    with pytest.raises(CardClosed):
        await service.give_up(alice.id, card.id)
    assert await _continue_items(cfg, alice.id) == 0
    assert await app.state.talk.list_messages(alice.id, card.thread_id) == []
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_give_up_stops_the_task_and_the_bot_rests(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await app.state.bots.set_status(alice.id, bot.id, BotStatus.STUCK)
    app.state.control.take(bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/give-up", headers=O)
        after = [await client.post(f"/api/stuck/{card.id}/{button}", headers=O) for button in BUTTONS]
    assert (r.status_code, r.json()["state"]) == (200, "given_up") and r.json()["closed_at"]
    assert [(a.status_code, a.json()) for a in after] == [(409, CLOSED)] * 3
    [line] = [m for m in await app.state.talk.list_messages(alice.id, card.thread_id) if m.role == "bot"]
    assert (line.body, line.kind, line.author_bot_id, line.tainted) == (GIVE_UP_LINE, "text", bot.id, True)
    assert GIVE_UP_LINE == "OK, I stopped that task."
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
    assert [f["status"] for f in await _frames(app, alice.id, "bot_status")] == ["resting"]
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["given_up"]
    assert app.state.control.held(bot.id) is None
    assert await _continue_items(cfg, alice.id) == 0
    assert app.state.main_browser.opened == ()


async def test_open_in_main_browser_opens_the_cards_address_and_marks_the_card(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, reason="login")
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert r.status_code == 200
    assert (r.json()["main_opened"], r.json()["state"]) == (True, "open")
    assert app.state.main_browser.opened == ((bot.id, SHOP_URL),)
    assert listed["main_opened"] is True
    assert [f["card"]["main_opened"] for f in await _frames(app, alice.id, "stuck_card")] == [True]
    assert await _continue_items(cfg, alice.id) == 0                      # opening the page is not carrying on


async def test_done_after_the_main_brave_says_you_did_the_step(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, reason="login")
    async with _signed_in(app, "alice") as client:
        await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"], r.json()["main_opened"]) == (200, "cleared", True)
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == (
        "I did this step in my own browser on shop.example. Don't read that page again; "
        f"carry on with the rest of: {REQUEST}. If you can't, tell me exactly what's left."
    )
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["open", "cleared"]


async def test_a_card_without_an_address_is_400_and_carries_on_without_a_link(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url="", reason="asked", note="Approve the payment in your bank app")
    async with _signed_in(app, "alice") as client:
        refused = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        cleared = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (refused.status_code, refused.json()) == (400, {"detail": "This card has no web address."})
    assert app.state.main_browser.opened == ()
    assert cleared.status_code == 200
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.link_scope == ()
    assert item.body == f"I did what you asked. Carry on with: {REQUEST}"


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "file:///etc/passwd", "javascript:alert(1)"])
async def test_an_address_the_url_check_refuses_is_never_opened(cfg, alice, url):
    """Design §5: the gateway's own check refuses a home-network address, ``file:`` and ``javascript:``."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url=url)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert (r.status_code, r.json()) == (400, {"detail": "That address can't be opened."})
    assert app.state.main_browser.opened == ()
    assert (listed["main_opened"], listed["state"]) == (False, "open")
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_an_unreachable_main_brave_is_503_and_leaves_the_card_unmarked(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app.state.main_browser.fail = True                                    # the keeper is down
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert (r.status_code, r.json()) == (503, {"detail": "desk unavailable"})
    assert (listed["main_opened"], listed["state"]) == (False, "open")


async def test_an_unreachable_main_brave_is_logged_with_its_cause_and_never_the_address(cfg, alice, caplog):
    """M10: the warning carries the traceback, and says which card and bot but never the card's address."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app.state.main_browser.fail = True
    async with _signed_in(app, "alice") as client:
        with caplog.at_level(logging.WARNING, logger="roost.stuck.service"):
            r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
    assert r.status_code == 503
    [record] = [r for r in caplog.records if r.name == "roost.stuck.service"]
    assert record.levelno == logging.WARNING
    assert card.id in record.getMessage() and bot.id in record.getMessage()
    assert record.exc_info is not None and record.exc_info[0] is DeskUnavailable
    assert "shop.example" not in caplog.text


async def test_a_card_given_up_while_the_main_brave_opens_is_card_closed(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    store = StuckStore(cfg)
    racing = _GivenUpWhileOpening(store, alice.id, card.id)
    with pytest.raises(CardClosed):
        await _service_with(app, store, racing).open_in_main_browser(alice.id, card.id)
    assert racing.opened == ((bot.id, SHOP_URL),)
    assert (await store.get(alice.id, card.id)).main_opened is False
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_another_users_card_is_404_on_every_route(cfg, alice):
    app = create_app()
    await register_user(cfg, "bob", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "bob") as as_bob:
        listed = (await as_bob.get("/api/stuck")).json()
        answers = [await as_bob.post(f"/api/stuck/{card.id}/{button}", headers=O) for button in BUTTONS]
        unknown = await as_bob.post("/api/stuck/not-a-card/clear", headers=O)
    assert listed == []
    assert [(a.status_code, a.json()) for a in answers] == [(404, NOT_FOUND)] * 3
    assert (unknown.status_code, unknown.json()) == (404, NOT_FOUND)
    assert (await StuckStore(cfg).get(alice.id, card.id)).state is CardState.OPEN
    assert app.state.main_browser.opened == ()
    assert await _continue_items(cfg, alice.id) == 0


async def test_the_buttons_need_an_origin_and_the_list_needs_a_login(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        bare = [await client.post(f"/api/stuck/{card.id}/{button}") for button in BUTTONS]
        foreign = [await client.post(f"/api/stuck/{card.id}/{button}", headers=BAD_O) for button in BUTTONS]
    assert [r.status_code for r in bare + foreign] == [403] * 6
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as nobody:
        assert (await nobody.get("/api/stuck")).status_code == 401
    assert (await StuckStore(cfg).get(alice.id, card.id)).state is CardState.OPEN
    assert app.state.main_browser.opened == ()


async def test_a_bot_stuck_on_a_check_carries_on_after_you_clear_it(cfg, alice, monkeypatch):
    """End to end: a challenge that stays leaves a card, Give it back clears it,
    and the continue run reads the cleared page and answers."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    model = team_model({"Helper": [_open_shop(), _read_again(), say("The blue kettle costs 25 EUR.")]})
    turns = _use_model(app, model)
    # open_page, then rung 1's one repeat of it, then the continue run's read_page
    app.state.desks.for_bot(bot.id).serve(SHOP_URL, CHALLENGE, CHALLENGE, CLEARED)
    ask = f"{REQUEST} on {SHOP_URL}"
    async with _signed_in(app, "alice") as client:
        thread = (await client.post(f"/api/bots/{bot.id}/threads", json={}, headers=O)).json()
        await client.post(f"/api/threads/{thread['id']}/messages", json={"text": ask}, headers=O)
        await wait_idle(turns, timeout=8)
        [card] = (await client.get("/api/stuck")).json()
        stuck_status = (await app.state.bots.get(alice.id, bot.id)).status
        cleared = await client.post(f"/api/stuck/{card['id']}/clear", headers=O)
        await wait_idle(turns, timeout=8)
        left_open = (await client.get("/api/stuck")).json()
    assert (card["reason"], card["host"], card["url"], card["state"]) == ("challenge", "shop.example", SHOP_URL, "open")
    assert stuck_status is BotStatus.STUCK
    assert (cleared.status_code, cleared.json()["state"], left_open) == (200, "cleared", [])
    messages = await app.state.talk.list_messages(alice.id, thread["id"])
    assert [(m.role, m.kind) for m in messages] == [
        ("user", "text"), ("bot", "stuck"), ("user", "card_answer"), ("bot", "text"),
    ]
    continue_line, reply = messages[2], messages[3]
    assert continue_line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {ask}"
    assert reply.body == "The blue kettle costs 25 EUR."
    assert len(model.requests) == 3                                       # 1 step until the block, 2 after Give it back
    assert continue_line.body in [t.text for t in model.requests[1].turns if t.role == "user"]
    assert any("25 EUR" in t.text for t in model.requests[2].turns if t.role == "tool")
    assert app.state.desks.for_bot(bot.id).open_page_calls == [SHOP_URL, SHOP_URL]
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["open", "cleared"]
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
