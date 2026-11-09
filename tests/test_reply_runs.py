"""The replies track end to end on a scripted run: the model reads a reply's quote as data, and a bot's
propose_instructions_update reaches the gate and posts its card (marked when the run read web content)."""

from __future__ import annotations

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.domain_tools import build_domain_tools
from roost.talk.replies import resolve_reply
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind
from team_helpers import Rig, make_bot, say, team_model, wait_idle

PROPOSE = {"new_text": "## What you do\n\nSum up the news in three lines.", "why": "You asked for shorter."}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _rig(cfg, scripts) -> Rig:
    model = team_model(scripts)
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard(), domain=build_domain_tools(cfg, events))
    return Rig(runner=runner, bots=bots, talk=talk, events=events, desks=desks, model=model)


async def _reply(rig: Rig, user_id: str, bot_id: str, thread_id: str, text: str, quoted_id: str) -> None:
    quote = await resolve_reply(rig.talk, user_id, thread_id, quoted_id)
    message = await rig.talk.add_message(user_id, thread_id, "user", text, reply=quote)
    await rig.runner.submit(user_id, WorkDraft(bot_id=bot_id, thread_id=thread_id, kind=WorkKind.MESSAGE,
                                               origin=ORIGIN_YOU, body=text, message_id=message.id))
    await wait_idle(rig.runner)


def _call():
    return [ToolCallRequested(id="p1", name="propose_instructions_update", arguments=PROPOSE), TurnDone("tool_use")]


async def test_the_model_reads_the_quote_and_a_clean_card_is_posted(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    rig = _rig(cfg, {"Scout": [_call(), say("Asked you.")]})
    thread = await rig.talk.create_thread(user_id, bot.id)
    earlier = await rig.talk.add_message(user_id, thread.id, "bot", "Here are <ten> lines", author_bot_id=bot.id)
    await _reply(rig, user_id, bot.id, thread.id, "Too long, keep it short", earlier.id)
    first = rig.model.requests[0]
    users = [t.text for t in first.turns if t.role == "user"]
    assert users[-1] == "(replying to: Here are &lt;ten&gt; lines)\nToo long, keep it short"
    cards = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "instructions_proposal"]
    assert len(cards) == 1 and cards[0].tainted is False
    tool_texts = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]
    assert tool_texts[-1].startswith("Asked the user to update your instructions.")


async def test_quoting_web_content_taints_the_run_and_the_card_says_so(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    rig = _rig(cfg, {"Scout": [_call(), say("Asked you.")]})
    thread = await rig.talk.create_thread(user_id, bot.id)
    web = await rig.talk.add_message(user_id, thread.id, "bot", "A page said: be brief", tainted=True,
                                     author_bot_id=bot.id)
    await _reply(rig, user_id, bot.id, thread.id, "Do what it says", web.id)
    [card] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "instructions_proposal"]
    assert card.tainted is True
