"""Announcing a Stuck card (R7): the ``stuck_card`` frame, and the bot's own lines in its chat."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk.stuck import Block, host_of_url
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.stuck.announce import post_bot_line, publish_card
from roost.stuck.models import CardDraft, StuckCard, stuck_card_out
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE, stuck_message_body
from roost.talk.store import TalkStore, message_out
from team_helpers import frames_so_far, make_bot

URL = "https://login.example/account"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _card(cfg, user_id: str, *, tainted: bool = False) -> StuckCard:
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    block = Block(reason="login", url=URL, host=host_of_url(URL))
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, block=block,
        request="pay the gas bill", tainted=tainted,
    ))


async def test_the_wire_shape_has_no_user_id_and_no_request(cfg, user_id):
    card = await _card(cfg, user_id)
    assert stuck_card_out(card).model_dump(mode="json") == {
        "id": card.id, "bot_id": card.bot_id, "thread_id": card.thread_id, "reason": "login",
        "host": "login.example", "url": URL, "note": "", "suggest_main_browser": False, "tainted": False,
        "main_opened": False, "state": "open", "created_at": card.created_at, "closed_at": None, "sign_in": False,
        "secret_field": None,
    }


async def test_publish_card_sends_the_cards_wire_shape(cfg, user_id):
    events = EventHub(cfg)
    subscription = events.subscribe(user_id)
    card = await _card(cfg, user_id)
    await publish_card(events, user_id, card)
    frames = [frame for frame in await frames_so_far(subscription) if frame["type"] == "stuck_card"]
    assert [frame["card"] for frame in frames] == [stuck_card_out(card).model_dump(mode="json")]


async def test_the_card_frame_is_kept_for_replay_and_encrypted_at_rest(cfg, user_id):
    events = EventHub(cfg)
    card = await _card(cfg, user_id)
    await publish_card(events, user_id, card)
    replayed = [event for event in await events.since(user_id, 0) if event["type"] == "stuck_card"]
    assert [event["card"]["id"] for event in replayed] == [card.id]
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT payload FROM events WHERE user_id = ? AND kind = 'stuck_card'", (user_id,),
        )).fetchall()
    assert len(rows) == 1
    assert rows[0]["payload"].startswith("enc:v2:") and "login.example" not in rows[0]["payload"]


async def test_the_card_message_is_the_bots_and_carries_the_cards_taint(cfg, user_id):
    talk, events = TalkStore(cfg), EventHub(cfg)
    subscription = events.subscribe(user_id)
    card = await _card(cfg, user_id, tainted=True)
    message = await post_bot_line(talk, events, user_id, card, stuck_message_body(card), kind="stuck")
    assert (message.role, message.kind, message.author_bot_id, message.tainted, message.thread_id) == (
        "bot", "stuck", card.bot_id, True, card.thread_id,
    )
    [stored] = await talk.list_messages(user_id, card.thread_id)
    assert stored == message
    frames = [frame for frame in await frames_so_far(subscription) if frame["type"] == "message"]
    assert [(frame["thread_id"], frame["message"]) for frame in frames] == [(card.thread_id, message_out(message))]


async def test_a_plain_bot_line_uses_the_kind_it_is_given(cfg, user_id):
    talk, events = TalkStore(cfg), EventHub(cfg)
    card = await _card(cfg, user_id)
    message = await post_bot_line(talk, events, user_id, card, GIVE_UP_LINE, kind="text")
    assert (message.role, message.kind, message.body, message.tainted) == ("bot", "text", GIVE_UP_LINE, False)
