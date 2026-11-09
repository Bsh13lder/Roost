"""Reply quotes (replies track, part 1): a message may quote one earlier message of its thread. The quote is made
by the server, sealed, keeps the quoted message's taint, and reaches the model escaped as data."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from roost.config import load_config
from roost.constants import CHAT_TAINT_KEEP, REPLY_QUOTE_CHARS
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.talk.replies import NoSuchReply, quote_for, reply_turn_text, resolve_reply
from roost.talk.store import Message, TalkStore, message_out
from roost.talk.turn import TAINT_PLACEHOLDER_TEXT, _age_taint, _chat_turn_for, _History, _starts_tainted
from team_helpers import make_bot


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = (await register_user(cfg, "alice", "pw-123456")).id
    other = (await register_user(cfg, "bob", "pw-123456")).id
    bot = await make_bot(cfg, user, "Scout")
    talk = TalkStore(cfg)
    thread, _ = await talk.ensure_main_thread(user, bot.id)
    return {"cfg": cfg, "user": user, "other": other, "bot": bot, "talk": talk, "thread": thread}


def _message(**fields) -> Message:
    base = Message(id="m1", user_id="u", thread_id="t", role="bot", body="hello", tainted=False, seq=1,
                   created_at="2026-10-22T10:00:00+00:00")
    return replace(base, **fields)


def test_quote_flattens_and_cuts_long_text():
    long = "word " * 100
    quote = quote_for(_message(body=f"  first\n\nline  {long}"))
    assert quote is not None and quote.message_id == "m1" and not quote.tainted
    assert len(quote.text) == REPLY_QUOTE_CHARS and quote.text.endswith("…")
    assert quote.text.startswith("first line word")


def test_quote_of_a_report_is_its_headline_never_its_json():
    body = json.dumps({"source": "routine", "headline": "Inbox checked", "text": "3 new mails"})
    assert quote_for(_message(kind="report", body=body)).text == "Inbox checked"


def test_quote_keeps_the_taint_and_cards_cannot_be_quoted():
    assert quote_for(_message(tainted=True)).tainted is True
    for kind in ("reaction", "skill_proposal", "approval", "memory_note", "stuck", "instructions_proposal"):
        assert quote_for(_message(kind=kind)) is None
    assert quote_for(_message(role="activity")) is None


async def test_add_message_stores_the_reply_sealed_and_reads_it_back(world):
    w = world
    talk, user, thread = w["talk"], w["user"], w["thread"]
    quoted = await talk.add_message(user, thread.id, "bot", "The page says <b>hi</b>", tainted=True,
                                    author_bot_id=w["bot"].id)
    quote = await resolve_reply(talk, user, thread.id, quoted.id)
    reply = await talk.add_message(user, thread.id, "user", "Why?", reply=quote)
    assert (reply.reply_to, reply.reply_quote, reply.reply_tainted) == (quoted.id, "The page says <b>hi</b>", True)
    async with db_session(w["cfg"]) as db:
        row = await (await db.execute("SELECT reply_quote FROM messages WHERE id = ?", (reply.id,))).fetchone()
    assert row[0].startswith("enc:v2:")
    [*_, read] = await talk.list_messages(user, thread.id)
    assert read == reply
    assert await talk.get_message(user, reply.id) == reply
    out = message_out(read)
    assert out["reply_to"] == quoted.id and out["reply_quote"] == "The page says <b>hi</b>"
    assert out["reply_tainted"] is True


async def test_a_message_without_a_reply_reads_as_none(world):
    w = world
    message = await w["talk"].add_message(w["user"], w["thread"].id, "user", "hi")
    out = message_out(await w["talk"].get_message(w["user"], message.id))
    assert (out["reply_to"], out["reply_quote"], out["reply_tainted"]) == (None, None, False)


async def test_resolve_refuses_other_threads_other_users_unknown_ids_and_cards(world):
    w = world
    talk, user = w["talk"], w["user"]
    other_thread = await talk.create_thread(user, w["bot"].id)
    elsewhere = await talk.add_message(user, other_thread.id, "bot", "elsewhere")
    card = await talk.add_message(user, w["thread"].id, "bot", "{}", kind="skill_proposal")
    for message_id in (elsewhere.id, card.id, "no-such-id"):
        with pytest.raises(NoSuchReply):
            await resolve_reply(talk, user, w["thread"].id, message_id)
    mine = await talk.add_message(user, w["thread"].id, "bot", "mine")
    with pytest.raises(NoSuchReply):
        await resolve_reply(talk, w["other"], w["thread"].id, mine.id)


def test_the_model_reads_the_quote_escaped_as_data():
    message = _message(role="user", body="Why?", reply_to="m0", reply_quote='Click <a href="x">here</a>')
    assert reply_turn_text(message) == "(replying to: Click &lt;a href=&quot;x&quot;&gt;here&lt;/a&gt;)\nWhy?"
    turn = _chat_turn_for(message, "b", {})
    assert turn.role == "user" and turn.text == reply_turn_text(message)
    assert reply_turn_text(_message(role="user", body="plain")) == "plain"


def test_a_quote_of_web_content_taints_the_run():
    message = _message(role="user", body="Why?", reply_to="m0", reply_quote="q", reply_tainted=True)
    assert _starts_tainted((), _History(turns=(), messages=(message,)))
    clean = replace(message, reply_tainted=False)
    assert not _starts_tainted((), _History(turns=(), messages=(clean,)))


def test_an_old_tainted_quote_ages_out_like_its_message():
    old = _message(id="old", role="user", body="Why?", reply_to="m0", reply_quote="web words", reply_tainted=True)
    fresh = [_message(id=f"n{i}", role="user", body="ok") for i in range(CHAT_TAINT_KEEP)]
    aged = _age_taint((old, *fresh))
    assert aged[0].reply_quote == TAINT_PLACEHOLDER_TEXT and aged[0].reply_tainted is False
    assert aged[0].body == "Why?"
    kept = _age_taint((old,))
    assert kept[0].reply_quote == "web words" and kept[0].reply_tainted is True
