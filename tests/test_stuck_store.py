"""Stuck cards (stuck flow §2, R6–R9): encrypted on disk, one open card per bot,
guarded state changes, and every query scoped to its user."""

from __future__ import annotations

import asyncio

import pytest

import roost.stuck.store as store_module
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import STUCK_REQUEST_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.desk.stuck import Block, host_of_url
from roost.gateway.auth import register_user
from roost.stuck.models import CardDraft, CardState
from roost.stuck.store import StuckStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

LOGIN_URL = "https://login.example/account"
REQUEST = "book a table for two at 8"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _chat(cfg, user_id: str, name: str = "Helper") -> tuple[str, str]:
    bot = await make_bot(cfg, user_id, name)
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    return bot.id, thread.id


@pytest.fixture
async def chat(cfg, user_id):
    return await _chat(cfg, user_id)


def _draft(bot_id: str, thread_id: str, *, reason: str = "login", url: str = LOGIN_URL, note: str = "",
           suggest: bool = False, request: str = REQUEST, tainted: bool = False,
           work_item_id: str | None = "item-0") -> CardDraft:
    block = Block(reason=reason, url=url, host=host_of_url(url), note=note, suggest_main_browser=suggest)
    return CardDraft(bot_id=bot_id, thread_id=thread_id, work_item_id=work_item_id, block=block,
                     request=request, tainted=tainted)


async def _raw(cfg, card_id: str):
    async with db_session(cfg) as db:
        return await (await db.execute(
            "SELECT url, note, request FROM stuck_cards WHERE id = ?", (card_id,),
        )).fetchone()


async def _count(cfg) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM stuck_cards")).fetchone())[0]


async def _three_open_cards(cfg, user_id: str, store: StuckStore) -> tuple:
    cards: tuple = ()
    for name in ("Ann", "Ben", "Cat"):
        bot_id, thread_id = await _chat(cfg, user_id, name)
        cards = (*cards, await store.open(user_id, _draft(bot_id, thread_id)))
    return cards


async def test_url_note_and_request_are_ciphertext_on_disk(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, reason="asked", note="approve the payment"))
    row = await _raw(cfg, card.id)
    assert all(row[column].startswith("enc:v2:") for column in ("url", "note", "request"))
    assert "login.example" not in row["url"] and "payment" not in row["note"] and "table" not in row["request"]
    again = await store.get(user_id, card.id)
    assert (again.url, again.note, again.request) == (LOGIN_URL, "approve the payment", REQUEST)


async def test_a_card_without_a_note_stores_no_note(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert (await _raw(cfg, card.id))["note"] is None
    assert (await store.get(user_id, card.id)).note == ""


async def test_a_new_card_is_open_and_keeps_what_stopped_the_bot(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, suggest=True, tainted=True))
    assert (card.user_id, card.bot_id, card.thread_id, card.work_item_id) == (user_id, bot_id, thread_id, "item-0")
    assert (card.reason, card.url, card.host) == ("login", LOGIN_URL, "login.example")
    assert (card.suggest_main_browser, card.tainted, card.main_opened) == (True, True, False)
    assert (card.state, card.answer_item_id, card.closed_at) == (CardState.OPEN, None, None)
    assert await store.get(user_id, card.id) == card
    assert await store.open_for_bot(user_id, bot_id) == card


async def test_a_bot_has_at_most_one_open_card(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    first = await store.open(user_id, _draft(bot_id, thread_id))
    second = await store.open(user_id, _draft(bot_id, thread_id, reason="challenge", url="https://other.example/"))
    assert second == first
    assert await _count(cfg) == 1


async def test_two_cards_opened_at_once_for_one_bot_become_one(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    a, b = await asyncio.gather(
        store.open(user_id, _draft(bot_id, thread_id)),
        store.open(user_id, _draft(bot_id, thread_id, reason="code")),
    )
    assert a.id == b.id
    assert await _count(cfg) == 1


async def test_after_a_card_closes_the_bot_can_get_a_new_one(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    first = await store.open(user_id, _draft(bot_id, thread_id))
    await store.close(user_id, first.id, CardState.GIVEN_UP)
    second = await store.open(user_id, _draft(bot_id, thread_id))
    assert second.id != first.id and second.state is CardState.OPEN


async def test_close_works_only_on_an_open_card_and_keeps_the_answer_item(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    cleared = await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert (cleared.state, cleared.answer_item_id) == (CardState.CLEARED, "item-1")
    assert cleared.closed_at is not None
    assert await store.close(user_id, card.id, CardState.GIVEN_UP) is None
    assert await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-2") is None
    assert await store.get(user_id, card.id) == cleared
    assert await store.open_for_bot(user_id, bot_id) is None


async def test_giving_up_closes_the_card_without_an_answer_item(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    given_up = await store.close(user_id, card.id, CardState.GIVEN_UP)
    assert (given_up.state, given_up.answer_item_id) == (CardState.GIVEN_UP, None)


async def test_a_card_is_never_closed_as_open(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    with pytest.raises(ValueError, match="can't be closed"):
        await store.close(user_id, card.id, CardState.OPEN)
    assert (await store.get(user_id, card.id)).state is CardState.OPEN


async def test_mark_blocked_only_from_cleared(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await store.mark_blocked(user_id, card.id) is None          # still open: rung 4 only follows a clear
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    blocked = await store.mark_blocked(user_id, card.id)
    assert (blocked.state, blocked.answer_item_id) == (CardState.BLOCKED, "item-1")
    assert await store.mark_blocked(user_id, card.id) is None


async def test_mark_main_opened_only_while_open(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    marked = await store.mark_main_opened(user_id, card.id)
    assert (marked.main_opened, marked.state) == (True, CardState.OPEN)
    cleared = await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert cleared.main_opened is True
    assert await store.mark_main_opened(user_id, card.id) is None


async def test_card_for_answer_finds_the_card_its_continue_item_answers(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert (await store.card_for_answer(user_id, "item-1")).id == card.id
    assert await store.card_for_answer(user_id, "item-2") is None


async def test_list_open_is_newest_first_and_leaves_out_closed_cards(cfg, user_id):
    store = StuckStore(cfg)
    ann, ben, cat = await _three_open_cards(cfg, user_id, store)
    await store.close(user_id, ben.id, CardState.GIVEN_UP)
    assert [card.id for card in await store.list_open(user_id)] == [cat.id, ann.id]


async def test_list_open_stops_at_the_list_limit(cfg, user_id, monkeypatch):
    monkeypatch.setattr(store_module, "STUCK_LIST_LIMIT", 2)
    store = StuckStore(cfg)
    ann, ben, cat = await _three_open_cards(cfg, user_id, store)
    assert [card.id for card in await store.list_open(user_id)] == [cat.id, ben.id]


async def test_another_users_card_is_not_found_and_not_changed(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await store.get(bob, card.id) is None
    assert await store.open_for_bot(bob, bot_id) is None
    assert await store.list_open(bob) == ()
    assert await store.mark_main_opened(bob, card.id) is None
    assert await store.close(bob, card.id, CardState.CLEARED, answer_item_id="item-1") is None
    assert await store.get(user_id, card.id) == card
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert await store.mark_blocked(bob, card.id) is None
    assert await store.card_for_answer(bob, "item-1") is None
    assert (await store.get(user_id, card.id)).state is CardState.CLEARED


async def test_open_bots_lists_every_users_bots_with_an_open_card(cfg, user_id, chat):
    store = StuckStore(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bot_id, thread_id = chat
    quiet_bot, quiet_thread = await _chat(cfg, user_id, "Quiet")
    bob_bot, bob_thread = await _chat(cfg, bob, "Scout")
    await store.open(user_id, _draft(bot_id, thread_id))
    done = await store.open(user_id, _draft(quiet_bot, quiet_thread))
    await store.close(user_id, done.id, CardState.CLEARED, answer_item_id="item-9")
    await store.open(bob, _draft(bob_bot, bob_thread))
    assert await store.open_bots() == ((user_id, bot_id), (bob, bob_bot))


async def test_retiring_a_bot_removes_its_cards(cfg, user_id, chat):
    """Review Focus 4: ON DELETE CASCADE; the open list (GET /api/stuck) no longer has it."""
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await BotStore(cfg).delete(user_id, bot_id) is True
    assert await store.get(user_id, card.id) is None
    assert await store.list_open(user_id) == ()
    assert await store.open_for_bot(user_id, bot_id) is None
    assert await store.open_bots() == ()
    assert await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1") is None
    assert await _count(cfg) == 0


async def test_a_card_for_a_chat_that_does_not_exist_is_refused(cfg, user_id, chat):
    bot_id, _ = chat
    with pytest.raises(ValueError, match="no longer exists"):
        await StuckStore(cfg).open(user_id, _draft(bot_id, "no-such-thread"))
    assert await _count(cfg) == 0


async def test_a_card_with_an_unknown_reason_is_refused(cfg, user_id, chat):
    bot_id, thread_id = chat
    with pytest.raises(ValueError, match="Unknown Stuck reason"):
        await StuckStore(cfg).open(user_id, _draft(bot_id, thread_id, reason="bored"))
    assert await _count(cfg) == 0


async def test_a_long_request_is_kept_up_to_the_limit(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, request="x" * (STUCK_REQUEST_MAX_CHARS + 50)))
    assert len(card.request) == STUCK_REQUEST_MAX_CHARS
    assert (await store.get(user_id, card.id)).request == card.request


async def test_an_address_that_fails_its_column_check_reads_as_no_address(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    async with db_session(cfg) as db:
        await db.execute("UPDATE stuck_cards SET url = request WHERE id = ?", (card.id,))
        await db.commit()
    again = await store.get(user_id, card.id)
    assert (again.url, again.host, again.request) == ("", "", REQUEST)
