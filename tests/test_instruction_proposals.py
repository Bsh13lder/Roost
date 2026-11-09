"""'Update my instructions?' (replies track, part 3): a bot offers new instructions for itself on a card; only the
user's Accept writes them."""

from __future__ import annotations

import json
import sqlite3

import pytest

from roost.bots.models import BotPatch
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import MAX_BOT_INSTRUCTIONS_LENGTH
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.instruction_proposals.diff import line_diff
from roost.instruction_proposals.service import (
    InstructionProposalClosed, InstructionProposalRefused, InstructionProposalService, NoSuchInstructionProposal,
)
from roost.instruction_proposals.store import InstructionProposalStore
from roost.instruction_proposals.tools import InstructionTools
from roost.talk.chats import chat_preview
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, HELPER_DENIED
from roost.talk.turn import _MODEL_KINDS
from team_helpers import make_bot

NEW = "## What you do\n\nRead the news and sum it up.\n\n## Tone\n\nShort."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def world(cfg):
    user = (await register_user(cfg, "alice", "pw-123456")).id
    bots = BotStore(cfg)
    bot = await make_bot(cfg, user, "Scout", "reads the news")
    bot = await bots.update(user, bot.id, BotPatch(instructions="Old words."))
    talk = TalkStore(cfg)
    thread, _ = await talk.ensure_main_thread(user, bot.id)
    service = InstructionProposalService(InstructionProposalStore(cfg), bots, talk, EventHub(cfg))
    return {"user": user, "bot": bot, "bots": bots, "talk": talk, "thread": thread, "service": service,
            "tools": InstructionTools(service)}


def _ctx(w, *, tainted=False, from_routine=False, thread_id=None, bot_id=None):
    return RecordContext(user_id=w["user"], bot_id=bot_id or w["bot"].id, tainted=tainted,
                         from_routine=from_routine, thread_id=thread_id or w["thread"].id, run_id="run-1")


async def _propose(w, text=NEW, why="You asked for shorter summaries.", **kw):
    return await w["tools"].run("propose_instructions_update", {"new_text": text, "why": why}, _ctx(w, **kw))


async def _cards(w, thread_id=None):
    return [m for m in await w["talk"].list_messages(w["user"], thread_id or w["thread"].id)
            if m.kind == "instructions_proposal"]


def test_the_tool_is_every_bots_and_never_a_helpers():
    tool = CATALOG["propose_instructions_update"]
    assert tool.kind == "write_change" and tool.no_ask and tool.allowed_when_tainted
    assert "propose_instructions_update" in EVERY_BOT_TOOLS and "propose_instructions_update" in HELPER_DENIED
    assert "instructions_proposal" not in _MODEL_KINDS
    import inspect
    from roost.instruction_proposals import tools as tools_module
    assert "update(" not in inspect.getsource(tools_module)


def test_line_diff():
    assert line_diff("a\nb\nc", "a\nB\nc\nd") == (
        {"op": "same", "text": "a"}, {"op": "del", "text": "b"}, {"op": "add", "text": "B"},
        {"op": "same", "text": "c"}, {"op": "add", "text": "d"})
    assert line_diff("", "x") == ({"op": "add", "text": "x"},)


async def test_propose_posts_a_card_and_accept_writes_the_instructions(world):
    w = world
    out = await _propose(w)
    assert out.text.startswith("Asked the user to update your instructions.")
    assert (await w["bots"].get(w["user"], w["bot"].id)).instructions == "Old words."
    [card] = await _cards(w)
    [view] = await w["service"].list_open(w["user"])
    assert json.loads(card.body) == {"proposal_id": view.proposal.id}
    assert card.author_bot_id == w["bot"].id and card.tainted is False
    payload = view.proposal.payload
    assert payload.before == "Old words." and payload.why == "You asked for shorter summaries."
    assert payload.after.startswith("## Who you are and context\n\nYou are Scout.")
    assert "## What you do\n\nRead the news and sum it up." in payload.after
    assert {"op": "del", "text": "Old words."} in view.diff and view.stale is False
    accepted, bot = await w["service"].accept(w["user"], view.proposal.id)
    assert accepted.proposal.state == "accepted" and bot.instructions == payload.after
    assert (await w["bots"].get(w["user"], w["bot"].id)).instructions == payload.after
    assert await w["service"].list_open(w["user"]) == ()


async def test_accept_with_the_users_edit_stores_their_words(world):
    w = world
    await _propose(w)
    [view] = await w["service"].list_open(w["user"])
    _, bot = await w["service"].accept(w["user"], view.proposal.id, text="My own version.")
    assert bot.instructions == "My own version."


async def test_accept_after_the_user_changed_the_instructions_is_stale(world):
    w = world
    await _propose(w)
    [view] = await w["service"].list_open(w["user"])
    await w["bots"].update(w["user"], w["bot"].id, BotPatch(instructions="Mine now."))
    assert (await w["service"].get(w["user"], view.proposal.id)).stale is True
    with pytest.raises(InstructionProposalRefused) as caught:
        await w["service"].accept(w["user"], view.proposal.id)
    assert caught.value.text == "Your bot's instructions changed since this card was made, so it no longer fits."
    assert (await w["service"].get(w["user"], view.proposal.id)).proposal.state == "open"
    assert (await w["bots"].get(w["user"], w["bot"].id)).instructions == "Mine now."


async def test_a_tainted_run_may_propose_but_the_card_is_marked(world):
    w = world
    out = await _propose(w, tainted=True)
    assert out.text.startswith("Asked the user")
    [card] = await _cards(w)
    [view] = await w["service"].list_open(w["user"])
    assert card.tainted is True and view.proposal.tainted is True


async def test_a_routine_run_proposal_is_marked_and_shown_in_the_bots_chat(world):
    w = world
    log = await w["talk"].create_thread(w["user"], w["bot"].id, "Morning", kind="routine")
    await _propose(w, from_routine=True, thread_id=log.id)
    [view] = await w["service"].list_open(w["user"])
    assert view.proposal.from_routine is True
    assert len(await _cards(w, log.id)) == 1 and len(await _cards(w)) == 1


async def test_refusals(world):
    w = world
    same = await _propose(w, text=(await w["bots"].get(w["user"], w["bot"].id)).instructions)
    assert same.text.startswith("Refused:")
    bad = await w["tools"].run("propose_instructions_update", {"why": "x"}, _ctx(w))
    assert bad.text.startswith("Refused: propose_instructions_update needs")
    too_long = await _propose(w, text="x" * (MAX_BOT_INSTRUCTIONS_LENGTH + 1))
    assert too_long.text.startswith("Refused:")
    secret = await _propose(w, text="Use sk-ant-abcdefghijklmnopqrstuv0123 for the API.")
    assert secret.text == "Refused: New instructions can't hold an API key or token."
    no_chat = await w["tools"].run("propose_instructions_update", {"new_text": NEW, "why": "x"},
                                   RecordContext(user_id=w["user"], bot_id=w["bot"].id, tainted=False))
    assert no_chat.text == "Refused: There is no chat to show the card in."
    assert await w["service"].list_open(w["user"]) == ()


async def test_one_open_card_per_bot(world):
    w = world
    assert (await _propose(w)).text.startswith("Asked")
    again = await _propose(w, text="Something else entirely.")
    assert again.text == "Refused: Your last instructions card is still waiting for the user."


async def test_accept_twice_is_closed_and_decline_writes_nothing(world):
    w = world
    await _propose(w)
    [view] = await w["service"].list_open(w["user"])
    declined = await w["service"].decline(w["user"], view.proposal.id)
    assert declined.proposal.state == "declined"
    assert (await w["bots"].get(w["user"], w["bot"].id)).instructions == "Old words."
    with pytest.raises(InstructionProposalClosed):
        await w["service"].accept(w["user"], view.proposal.id)
    with pytest.raises(NoSuchInstructionProposal):
        await w["service"].get(w["user"], "nope")


async def test_another_users_proposal_is_no_such_proposal(world, cfg):
    w = world
    await _propose(w)
    [view] = await w["service"].list_open(w["user"])
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    for call in (w["service"].get, w["service"].accept, w["service"].decline):
        with pytest.raises(NoSuchInstructionProposal):
            await call(bob, view.proposal.id)
    assert await w["service"].list_open(bob) == ()


async def test_the_payload_is_sealed_and_the_chat_list_says_words(world, cfg):
    w = world
    await _propose(w)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        [(payload,)] = con.execute("SELECT payload FROM instruction_proposals").fetchall()
    finally:
        con.close()
    assert payload.startswith("enc:v2:") and "Read the news" not in payload
    [card] = await _cards(w)
    assert chat_preview(card) == ("Asking you: update my instructions", "card")
