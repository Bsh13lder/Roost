"""ask_choice parks the run on an options card (chat feel Task 4)."""

from __future__ import annotations

import pytest

from roost.approvals.models import approval_card_out
from roost.choices.decisions import DecisionBook
from roost.choices.models import CHOICE_TOOL, choice_of
from roost.choices.texts import ALREADY_DECIDED_TEXT, BAD_CHOICE_ARGS_TEXT, CHOICE_NOT_HERE_TEXT
from roost.choices.tool import park_choice
from roost.constants import DECISION_REUSE_MAX_DAYS
from roost.config import load_config
from roost.constants import CHOICE_OPTION_MAX_CHARS
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot

ARGS = {"question": "Keep it as is?", "options": ["Keep it", "Change it", "Ask later"], "safe": 0,
        "why": "The file is shared."}


@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    book = DecisionBook(MemoryService(MemoryStore(cfg), EventHub(cfg)))
    return cfg, user, bot, book


async def _park(rig, arguments=ARGS, *, cards=True, tainted=False, qbook=False):
    cfg, user, bot, book = rig
    return await park_choice(arguments, cards=cards, tainted=tainted, decisions=book, user_id=user.id,
                             bot_id=bot.id, has_question_book=qbook)


async def test_ask_choice_parks_only_in_your_own_chat(rig):
    step = await _park(rig)
    assert step.tool == CHOICE_TOOL and step.arguments["options"] == ARGS["options"]
    elsewhere = await _park(rig, cards=False)
    assert elsewhere.startswith(CHOICE_NOT_HERE_TEXT.format(safe="Keep it"))
    assert "note_question" not in elsewhere
    assert "note_question" in await _park(rig, cards=False, qbook=True)


async def test_a_decided_question_is_not_asked_again(rig):
    cfg, user, bot, book = rig
    await book.record(user.id, bot.id, "Keep it as is?", "Keep it", tainted=False)
    again = await _park(rig, {**ARGS, "question": "keep it AS IS"})
    assert isinstance(again, str) and again.endswith("Keep it. Go on with that.")
    assert again.startswith("Already decided on ")
    assert ALREADY_DECIDED_TEXT.split("{")[0] in again


async def test_a_bot_saved_decision_does_not_count(rig):
    from roost.memory.models import MemoryDraft
    cfg, user, bot, book = rig
    memory = MemoryService(MemoryStore(cfg), EventHub(cfg))
    await memory.save(user.id, MemoryDraft(kind="decision", text="Keep it as is?\nDecision: Keep it",
                                           bot_id=bot.id, source="bot", created_by_bot=bot.id))
    assert (await _park(rig)).tool == CHOICE_TOOL


@pytest.mark.parametrize("bad", [
    {**ARGS, "options": ["Only one"]},
    {**ARGS, "options": ["a", "b", "c", "d", "e"]},
    {**ARGS, "safe": 3},
    {**ARGS, "safe": -1},
    {**ARGS, "options": ["a", "x" * (CHOICE_OPTION_MAX_CHARS + 1)]},
    {**ARGS, "options": ["same", "SAME"]},
    {**ARGS, "question": ""},
    {"question": "Q?"},
])
async def test_bad_choice_arguments_are_refused(rig, bad):
    assert await _park(rig, bad) == BAD_CHOICE_ARGS_TEXT


async def test_the_options_card_shows_every_stored_argument(rig):
    cfg, user, bot, book = rig
    step = await _park(rig, {**ARGS, "own": False})
    assert [r.label for r in step.rows] == ["Question", "Option 1", "Option 2", "Option 3", "Safe choice",
                                            "Own answer", "Why"]
    assert next(r for r in step.rows if r.key == "safe").value == "Keep it"
    from roost.approvals.models import ApprovalCard, CardState
    card = ApprovalCard("c1", user.id, bot.id, "t1", None, "ask", CardState.OPEN, (step,), "", False, False,
                        None, "2026-10-22T00:00:00+00:00", None)
    out = approval_card_out(card)
    assert out.choice.question == "Keep it as is?" and out.choice.safe == 0 and out.choice.own is False
    assert out.choice.options == ARGS["options"] and out.choice.why == "The file is shared."
    assert "request" not in out.model_dump() and "user_id" not in out.model_dump()
    assert choice_of(card) is not None


def test_every_bot_has_ask_choice():
    assert CATALOG["ask_choice"].kind == "read"
    from roost.talk.tools import EVERY_BOT_TOOLS, helper_tool_names
    assert "ask_choice" in EVERY_BOT_TOOLS
    assert "ask_choice" not in helper_tool_names(EVERY_BOT_TOOLS)


async def _chat(cfg, user, bot, steps):
    from approval_helpers import make_card_rig
    from team_helpers import send, team_model, wait_idle
    r = make_card_rig(cfg, team_model({bot.name: steps}))
    thread = await r.talk.create_thread(user.id, bot.id)
    await send(r, user.id, bot.id, thread.id, "Do the thing")
    await wait_idle(r.runner)
    return r, thread


def _asks(arguments):
    return [ToolCallRequested(id="c1", name="ask_choice", arguments=arguments), TurnDone("tool_use")]


async def test_a_chat_run_opens_an_options_card_and_the_bot_asks_you(rig):
    from team_helpers import say
    cfg, user, bot, book = rig
    r, thread = await _chat(cfg, user, bot, [_asks(ARGS), say("I asked you.")])
    cards = await r.store.list_open(user.id)
    assert len(cards) == 1 and cards[0].kind == "ask" and not cards[0].tainted
    assert choice_of(cards[0]).options == tuple(ARGS["options"])
    assert len(r.model.requests) == 1


async def test_a_tainted_run_opens_a_marked_card(rig):
    from team_helpers import say
    cfg, user, bot, book = rig
    page = [ToolCallRequested(id="p", name="open_page", arguments={"url": "https://example.com"}),
            TurnDone("tool_use")]
    r, thread = await _chat(cfg, user, bot, [page, _asks(ARGS), say("I asked you.")])
    cards = await r.store.list_open(user.id)
    assert len(cards) == 1 and cards[0].tainted is True


async def _decided(rig, question="Keep it as is?", *, days_old=0):
    cfg, user, bot, book = rig
    saved = await book.record(user.id, bot.id, question, "Keep it", tainted=False)
    if days_old:
        from datetime import datetime, timedelta, timezone
        from roost.db.connection import db_session
        old = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        async with db_session(cfg) as db:
            await db.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (old, saved.memory_id))
            await db.commit()


def _hint(step):
    return [r.value for r in step.rows if r.key == "earlier"]


async def test_a_clean_run_reuses_a_young_decision(rig):
    await _decided(rig, days_old=DECISION_REUSE_MAX_DAYS - 1)
    assert isinstance(await _park(rig), str)


async def test_a_tainted_run_opens_a_card_with_the_earlier_answer(rig):
    await _decided(rig)
    step = await _park(rig, tainted=True)
    assert step.tool == CHOICE_TOOL and _hint(step) == ["Keep it"]


async def test_an_old_decision_opens_a_card_with_a_hint(rig):
    await _decided(rig, days_old=DECISION_REUSE_MAX_DAYS + 1)
    step = await _park(rig)
    assert step.tool == CHOICE_TOOL and _hint(step) == ["Keep it"]


@pytest.mark.parametrize("word", ["delete", "send", "pay", "buy", "submit", "accept", "remove", "publish"])
async def test_dangerous_questions_never_auto_answer(rig, word):
    question = f"Should I {word.upper()} it now?"
    await _decided(rig, question)
    step = await _park(rig, {**ARGS, "question": question})
    assert step.tool == CHOICE_TOOL and _hint(step) == ["Keep it"]


async def test_a_question_without_those_words_is_reused(rig):
    await _decided(rig, "Is the colour fine?")
    assert isinstance(await _park(rig, {**ARGS, "question": "Is the colour fine?"}), str)
