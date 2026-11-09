"""The Send card's buttons (owner, 2026-11-03): Send · Don't send · Change it…. Change it closes the card as edited and
posts your words as your own message, so the bot's next run retypes them and asks again; Don't send tells the bot to
stop and wait. Other Ask cards keep Yes · No. The red "from web content" badge shows only when the text came from a
page."""

from __future__ import annotations

import pytest

from approval_helpers import make_card_rig
from roost.approvals.models import (
    ApprovalDraft, BadAnswer, CardState, DraftBox, PendingCall, approval_card_out,
)
from roost.approvals.send_card import is_send_card, shows_web_badge
from roost.approvals.texts import NO_LINE, SEND_NO_LINE
from roost.computer_use.models import ActResolution, Box, PageTarget, resolution_to_json
from roost.config import load_config
from roost.constants import APPROVAL_EDIT_TEXT_MAX
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from team_helpers import RecordingModel, make_bot, say, wait_idle

_LETTER = "Hi! I have built REST APIs in Node.js for six years."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _button(text: str) -> PageTarget:
    return PageTarget(node_id=9, kind="button", text=text, tag="button", input_type="", box=Box(300, 560, 220, 36),
                      form_method="", form_submit_text="", is_form_submit=False, link_host="", in_dialog="",
                      in_consent=False, cross_origin_frame=False, editable=False, secret_field=False, searchish=False,
                      expands=False)


def _step(text: str = "Send for 14 Connects", commit: str = "send", *, basis: bool = False) -> PendingCall:
    act = ActResolution(tool="click", url="https://www.upwork.com/apply", host="www.upwork.com",
                        target=_button(text), point=(410, 578), covered_by="", nav_host="", commit=commit)  # type: ignore[arg-type]
    return PendingCall(tool="click", arguments={"target": {"text": text}, "expect": "sent"}, topic="browsing",
                       title="Send message", floor="commit_click", act=resolution_to_json(act), tainted_basis=basis,
                       drafts=(DraftBox("Cover letter", _LETTER, 5),))


async def _open(cfg, step: PendingCall, *, tainted: bool = True):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Gigs")
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Gigs": [say("I'll change it."), say("ok")]})))
    thread = await rig.talk.create_thread(user.id, bot.id)
    card = await rig.store.open(user.id, ApprovalDraft(bot_id=bot.id, thread_id=thread.id, work_item_id=None,
                                                       kind="ask", steps=(step,), request="send it", tainted=tainted))
    return rig, user.id, thread, card


def test_only_a_send_submit_or_accept_click_is_a_send_card():
    assert is_send_card_of(_step()) and is_send_card_of(_step("Submit proposal", "submit"))
    assert is_send_card_of(_step("Accept offer", "accept"))
    assert not is_send_card_of(_step("Pay now", "spend")) and not is_send_card_of(_step("Delete", "delete"))


def is_send_card_of(step: PendingCall) -> bool:
    from roost.approvals.models import ApprovalCard
    card = ApprovalCard(id="c", user_id="u", bot_id="b", thread_id="t", work_item_id=None, kind="ask",
                        state=CardState.OPEN, steps=(step,), request="", tainted=True, session_offer=False,
                        answer_item_id=None, created_at="", closed_at=None)
    return is_send_card(card)


async def test_change_it_posts_your_words_as_your_message_and_the_bot_reads_them(cfg):
    rig, user_id, thread, card = await _open(cfg, _step())
    assert approval_card_out(card).send is True
    answered = await rig.service.answer(user_id, card.id, "edit", "Say I can start Monday instead")
    await wait_idle(rig.runner)
    assert answered.state is CardState.EDITED
    mine = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "user" and m.kind == "text"]
    assert [m.body for m in mine] == ["Say I can start Monday instead"] and not mine[0].tainted
    assert any(turn.text == "Say I can start Monday instead" for turn in rig.model.requests[-1].turns)


async def test_change_it_needs_words_and_only_a_send_card_offers_it(cfg):
    rig, user_id, _, card = await _open(cfg, _step())
    with pytest.raises(BadAnswer):
        await rig.service.answer(user_id, card.id, "edit", "   ")
    with pytest.raises(BadAnswer):
        await rig.service.answer(user_id, card.id, "edit", "x" * (APPROVAL_EDIT_TEXT_MAX + 1))
    other = await rig.store.open(user_id, ApprovalDraft(
        bot_id=card.bot_id, thread_id=card.thread_id, work_item_id=None, kind="ask",
        steps=(_step("Pay now", "spend"),), request="", tainted=False))
    assert approval_card_out(other).send is False
    with pytest.raises(BadAnswer):
        await rig.service.answer(user_id, other.id, "edit", "something else")


async def test_dont_send_tells_the_bot_to_stop_and_wait(cfg):
    rig, user_id, thread, card = await _open(cfg, _step())
    await rig.service.answer(user_id, card.id, "no")
    await wait_idle(rig.runner)
    lines = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "card_answer"]
    assert lines == [SEND_NO_LINE.format(title="Send message")]
    assert "carry on" not in lines[0] and NO_LINE.format(title="Send message") != lines[0]


def test_the_web_badge_follows_the_text_on_a_send_card():
    from roost.approvals.models import ApprovalCard

    def card(step: PendingCall, tainted: bool) -> ApprovalCard:
        return ApprovalCard(id="c", user_id="u", bot_id="b", thread_id="t", work_item_id=None, kind="ask",
                            state=CardState.OPEN, steps=(step,), request="", tainted=tainted, session_offer=False,
                            answer_item_id=None, created_at="", closed_at=None)

    assert not shows_web_badge(card(_step(), True))                    # it only looked at the page
    assert shows_web_badge(card(_step(basis=True), True))              # its text came from the page
    assert not shows_web_badge(card(_step(basis=True), False))
    assert shows_web_badge(card(_step("Pay now", "spend"), True))      # any other card keeps the run's taint
    assert approval_card_out(card(_step(), True)).from_web is False
    assert approval_card_out(card(_step(), True)).tainted is True      # the card's own taint is unchanged
