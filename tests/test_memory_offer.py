"""A refused ``remember`` is never a blank: the chat shows a ``memory_offer`` line, "Not remembered: …" with a
Remember it button, and the bot's tool result is one short sentence."""

from __future__ import annotations

import json
import sqlite3

import pytest

from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.db.connection import db_session, get_db_path, init_db
from roost.desk.fake import FakeDesk
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.memory.offers import (
    MEMORY_OFFER_KIND, OFFERED_TOOL_TEXT, offer_body, offer_line, parse_offer, remembered_line,
)
from roost.memory.prompt import MEMORY_USE_TEXT
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore
from roost.memory.tool_specs import REMEMBER_SPEC, TAINTED_REMEMBER_TEXT
from roost.memory.tools import MemoryTools
from roost.talk.chats import chat_preview
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import Gate
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner
from team_helpers import make_bot

WANT = "send me task alerts only, no budget alerts"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tools(cfg) -> MemoryTools:
    events = EventHub(cfg)
    return MemoryTools(MemoryService(MemoryStore(cfg), events), TalkStore(cfg), events)


def _count(cfg, sql: str) -> int:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def _runner(cfg, user_id, bot_id, thread_id) -> ToolRunner:
    return ToolRunner(
        user_id=user_id, bot_id=bot_id, desk=FakeDesk(bot_id), gate=Gate(cfg), activity=ActivityBoard(),
        events=EventHub(cfg), allowed=frozenset(CATALOG), tainted=True, domain=DomainTools((_tools(cfg),)),
        thread_id=thread_id,
    )


def _remember(text: str = WANT, kind: str = "preference") -> ToolCallRequested:
    return ToolCallRequested(id="r1", name="remember", arguments={"text": text, "kind": kind})


async def _offers(cfg, user_id, thread_id):
    messages = await TalkStore(cfg).list_latest_messages(user_id, thread_id, 20)
    return [m for m in messages if m.kind == MEMORY_OFFER_KIND]


def test_the_line_says_what_was_not_remembered_and_why():
    assert offer_line(WANT) == (f"Not remembered: {WANT}. I read a web page in this run, "
                                "so I can't save memories myself.")
    assert offer_line("Likes tea.") == ("Not remembered: Likes tea. I read a web page in this run, "
                                        "so I can't save memories myself.")
    assert remembered_line("Likes tea.") == "Remembered: Likes tea."
    assert OFFERED_TOOL_TEXT == (
        "Not saved yet. Tell the user plainly that it is not saved and that they can tap Remember it in the chat to save it. Never say you saved it."
    )


def test_the_body_round_trips_and_junk_is_no_offer():
    body = offer_body(WANT, "preference", 5)
    assert json.loads(body) == {"text": WANT, "kind": "preference", "importance": 5, "memory_id": None}
    offer = parse_offer(body)
    assert offer is not None and offer.text == WANT and offer.memory_id is None
    assert parse_offer("not json") is None and parse_offer('{"text": ""}') is None
    assert parse_offer(json.dumps({"text": "x", "kind": "nope", "importance": 3})) is None


async def test_a_tainted_remember_posts_a_sealed_offer_marked_from_the_web(cfg, user_id):
    bot = await make_bot(cfg, user_id, "One")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    result = await _runner(cfg, user_id, bot.id, thread.id).run(_remember())
    assert result == OFFERED_TOOL_TEXT
    [offer] = await _offers(cfg, user_id, thread.id)
    assert offer.tainted and offer.role == "activity" and offer.author_bot_id == bot.id
    assert json.loads(offer.body)["text"] == WANT
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT body FROM messages WHERE id = ?", (offer.id,))).fetchone()
    assert row["body"].startswith("enc:v2") and "budget" not in row["body"]
    assert _count(cfg, "SELECT COUNT(*) FROM memories") == 0


async def test_no_offer_when_a_click_could_not_save_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "One")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    secret = await _runner(cfg, user_id, bot.id, thread.id).run(_remember("my password is hunter2", "fact"))
    no_chat = await _runner(cfg, user_id, bot.id, None).run(_remember())
    bad = await _runner(cfg, user_id, bot.id, thread.id).run(_remember(kind="nonsense"))
    assert secret == no_chat == bad == TAINTED_REMEMBER_TEXT
    assert await _offers(cfg, user_id, thread.id) == []


async def test_the_tools_own_taint_check_offers_too(cfg, user_id):
    bot = await make_bot(cfg, user_id, "One")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=True, thread_id=thread.id)
    outcome = await _tools(cfg).run("remember", {"text": "Likes tea.", "kind": "fact"}, ctx)
    assert outcome.text == OFFERED_TOOL_TEXT and not outcome.created
    assert len(await _offers(cfg, user_id, thread.id)) == 1


async def test_the_chat_list_shows_words_never_json(cfg, user_id):
    bot = await make_bot(cfg, user_id, "One")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    await _runner(cfg, user_id, bot.id, thread.id).run(_remember())
    [offer] = await _offers(cfg, user_id, thread.id)
    text, kind = chat_preview(offer)
    assert text.startswith("Not remembered: send me task alerts") and kind == "notice" and "{" not in text
    taken = chat_preview(offer.__class__(**{**offer.__dict__, "body": offer_body("Likes tea.", "fact", 3, "m1")}))
    assert taken == ("Remembered: Likes tea.", "notice")
    junk = chat_preview(offer.__class__(**{**offer.__dict__, "body": "{oops"}))
    assert junk == ("Not remembered", "notice")


def test_the_prompt_says_remind_is_a_task_and_lasting_is_a_memory():
    assert "remind me" in MEMORY_USE_TEXT and "tell me at" in MEMORY_USE_TEXT
    assert "task with a reminder" in MEMORY_USE_TEXT and "add_task" in MEMORY_USE_TEXT
    assert "lasting preference or fact" in MEMORY_USE_TEXT
    assert "one short line which one you did" in MEMORY_USE_TEXT
    assert "add_task" in REMEMBER_SPEC.description
