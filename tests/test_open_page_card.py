"""An address the run may not open by itself asks you once with an Open card (owner, 2026-10-23: Gela refused
WhatsApp Web twice and told the owner to type the link). Yes opens exactly the stored address and lets this chat
use that site from then on: the link scope of the run that carries on and the computer's site fence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from approval_helpers import make_card_rig
from roost.approvals.models import ApprovalState
from roost.computer_use.run_fence import approved_site_hosts
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.gate import LINK_REFUSAL_TEXT, GateContext, judge
from roost.talk.link_scope import LinkScope
from roost.talk.new_site import askable_url, page_step
from roost.talk.tool_catalog import CATALOG
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

WHATSAPP = "https://web.whatsapp.com/"
CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)


def _ctx(approval: ApprovalState | None = CARDS) -> GateContext:
    return GateContext(allowed=frozenset({"open_page"}), tainted=True,
                       link_guard=LinkScope.of(["https://example.com/"]), approval=approval)


def _judge(url: str, approval: ApprovalState | None = CARDS):
    return judge(CATALOG["open_page"], "open_page", {"url": url}, _ctx(approval))


def test_an_address_off_the_scope_asks_with_an_open_card_in_your_chat():
    verdict = _judge(WHATSAPP)
    assert (verdict.decision, verdict.reason, verdict.url) == ("ask", "new_site", WHATSAPP)


def test_an_address_in_the_scope_still_just_opens():
    verdict = _judge("https://example.com/")
    assert (verdict.decision, verdict.url) == ("do", "https://example.com/")


@pytest.mark.parametrize("approval", [None, replace(CARDS, cards=False)])
def test_with_nobody_watching_it_is_refused_and_never_asks_you_to_type_the_link(approval):
    verdict = _judge(WHATSAPP, approval)
    assert (verdict.decision, verdict.reason, verdict.text) == ("never", "link_not_trusted", LINK_REFUSAL_TEXT)
    assert "send me" not in LINK_REFUSAL_TEXT.lower() and "type" not in LINK_REFUSAL_TEXT.lower()


@pytest.mark.parametrize("url", [
    "https://user:pw@web.whatsapp.com/", "https://web.whatsapp.com:8443/", "ftp://web.whatsapp.com/",
    "file:///etc/passwd", "javascript:alert(1)", "https://web.whatsapp.com\\@evil.io/", "http://localhost/",
    "http://192.168.1.1/", "", "web.whatsapp.com",
])
def test_an_address_no_card_could_make_safe_is_never(url):
    assert askable_url(url) is None
    assert _judge(url).decision == "never"


def test_the_open_card_step_shows_the_site_and_the_whole_address():
    step = page_step(WHATSAPP)
    assert (step.tool, step.floor, dict(step.arguments)) == ("open_page", "new_site", {"url": WHATSAPP})
    assert step.title == "Open web.whatsapp.com"
    assert {(r.label, r.value) for r in step.rows} >= {("Site", "web.whatsapp.com"), ("Address", WHATSAPP)}


# -- the whole path: park, Yes, the page opens, the chat may use the site ----------------------------------

@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _open(call_id: str, url: str):
    return [ToolCallRequested(id=call_id, name="open_page", arguments={"url": url}), TurnDone("tool_use")]


def _add_task(call_id: str):
    return [ToolCallRequested(id=call_id, name="add_task", arguments={"title": "Read the news"}),
            TurnDone("tool_use")]


async def _parked(cfg, user_id: str):
    """A message in a routine's run log parks an Ask card (Gela is in Ask every time); after your Yes, the run that
    carries on there is no run of your own chat, so when it reads a page you linked and then wants WhatsApp Web it
    asks with an Open card. (In your own 1:1 chat, the run after your Yes just opens it, owner 2026-11-05.)"""
    bot = await make_bot(cfg, user_id, "Gela")
    script = [_add_task("c0"), _open("c1", "https://example.com/"), _open("c2", WHATSAPP), say("Opened it."),
              say("Done.")]
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Gela": script})))
    thread = await rig.talk.create_thread(user_id, bot.id, "Read the news", kind="routine")
    await send(rig, user_id, bot.id, thread.id, "Add a task, read https://example.com/ then open the messenger")
    await wait_idle(rig.runner)
    await rig.service.answer(user_id, (await rig.store.list_open(user_id))[0].id, "yes")
    await wait_idle(rig.runner)
    return rig, bot, thread


async def test_in_your_own_chat_the_bot_just_opens_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Gela")
    script = [_open("c1", "https://example.com/"), _open("c2", WHATSAPP), say("Opened it.")]
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Gela": script})))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Read https://example.com/ then open the messenger")
    await wait_idle(rig.runner)
    assert tuple(await rig.store.list_open(user_id)) == ()
    assert WHATSAPP in rig.desks.for_bot(bot.id).open_page_calls


async def _queued_scope(cfg, user_id: str, item_id: str) -> tuple[str, ...]:
    from roost.work.queue import WorkQueue
    item = await WorkQueue(cfg).get(user_id, item_id)
    return tuple(item.link_scope) if item is not None else ()


async def test_the_bot_parks_on_one_open_card_instead_of_refusing(cfg, user_id):
    rig, bot, _ = await _parked(cfg, user_id)
    cards = await rig.store.list_open(user_id)
    assert len(cards) == 1 and cards[0].tainted
    step = cards[0].steps[0]
    assert (step.tool, step.floor, step.arguments["url"]) == ("open_page", "new_site", WHATSAPP)
    desk = rig.desks.for_bot(bot.id)
    assert WHATSAPP not in desk.open_page_calls          # nothing opened before your Yes


async def test_yes_opens_the_stored_address_and_the_chat_may_use_the_site(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    card = (await rig.store.list_open(user_id))[0]
    closed = await rig.service.answer(user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert WHATSAPP in rig.desks.for_bot(bot.id).open_page_calls
    assert "web.whatsapp.com" in await approved_site_hosts(cfg, user_id, thread.id)
    assert closed.answer_item_id is not None
    assert WHATSAPP in await _queued_scope(cfg, user_id, closed.answer_item_id)


async def test_no_opens_nothing_and_widens_nothing(cfg, user_id):
    rig, bot, thread = await _parked(cfg, user_id)
    card = (await rig.store.list_open(user_id))[0]
    await rig.service.answer(user_id, card.id, "no")
    await wait_idle(rig.runner)
    assert WHATSAPP not in rig.desks.for_bot(bot.id).open_page_calls
    assert await approved_site_hosts(cfg, user_id, thread.id) == ()
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT state FROM approval_cards WHERE id = ?", (card.id,))).fetchone()
    assert row["state"] == "declined"


def test_the_bot_is_told_new_addresses_ask_once_and_never_to_make_you_type_them():
    from roost.talk.instructions import _OUTSIDE_CONTENT_TEXT
    from roost.talk.tool_catalog import OPEN_PAGE_SPEC
    for text in (_OUTSIDE_CONTENT_TEXT, OPEN_PAGE_SPEC.description):
        assert "Open card" in text and "never ask the user to type" in text
