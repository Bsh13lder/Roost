"""B3 (owner decision 2026-10-23): the Sign-in card's field variant and its migration (schema v35)."""

from __future__ import annotations

import json
import sqlite3

import aiosqlite

from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS, _apply_one, latest_version
from roost.desk.stuck import Block
from roost.gateway.auth import register_user
from roost.stuck.models import CardDraft, stuck_card_out
from roost.stuck.store import StuckStore
from roost.stuck.texts import stuck_message_body
from roost.talk.store import TalkStore

_NAME = "secret field"


def _migration():
    return next(m for m in MIGRATIONS if m.name == _NAME)


async def test_v35_adds_the_secret_field_column_and_is_idempotent():
    assert _migration().version == 35 and _migration().version <= latest_version()
    config = load_config()
    await init_db(config)
    db_path = get_db_path(config)
    async with aiosqlite.connect(db_path) as db:
        await _apply_one(db, _migration())
    con = sqlite3.connect(db_path)
    try:
        columns = {row[1]: row for row in con.execute("PRAGMA table_info(stuck_cards)")}
    finally:
        con.close()
    assert columns["secret_field"][2] == "TEXT" and columns["secret_field"][4] is None


async def _card(block: Block):
    config = load_config()
    await init_db(config)
    user = await register_user(config, "alice", "pw-123456")
    bot = await BotStore(config).create(user.id, BotDraft(name="Gela", job="j", instructions="",
                                                          avatar=Avatar("round", "#22c55e", "none")))
    thread = await TalkStore(config).create_thread(user.id, bot.id)
    store = StuckStore(config)
    card = await store.open(user.id, CardDraft(bot_id=bot.id, thread_id=thread.id, work_item_id=None, block=block,
                                               request="sign in", tainted=True, sign_in=True))
    return store, user.id, card


async def test_a_field_card_keeps_its_kind_and_shows_it_on_the_wire():
    block = Block(reason="login", url="https://www.upwork.com/ab/account-security/login", host="www.upwork.com",
                  note="to read your messages", sign_in=True, field="password")
    store, user_id, card = await _card(block)
    again = await store.get(user_id, card.id)
    assert card.secret_field == "password" and again is not None and again.secret_field == "password"
    assert stuck_card_out(again).secret_field == "password"
    assert json.loads(stuck_message_body(again))["secret_field"] == "password"


async def test_a_plain_sign_in_card_has_no_field():
    block = Block(reason="login", url="https://shop.example/login", host="shop.example", sign_in=True)
    store, user_id, card = await _card(block)
    assert (await store.get(user_id, card.id)).secret_field is None


def test_a_field_card_is_never_met_again_by_the_next_field():
    from roost.stuck.models import CardState, StuckCard

    card = StuckCard(id="c", user_id="u", bot_id="b", thread_id="t", work_item_id=None, reason="login",
                     url="https://www.upwork.com/login", note="", request="", suggest_main_browser=False,
                     tainted=True, main_opened=False, state=CardState.CLEARED, answer_item_id="i",
                     created_at="", closed_at=None, sign_in=True, secret_field="password")
    code = Block(reason="login", url="https://www.upwork.com/login", host="www.upwork.com", sign_in=True,
                 field="code")
    assert not card.is_met_again_by(code)
