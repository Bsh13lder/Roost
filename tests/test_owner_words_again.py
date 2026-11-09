"""Owner, 2026-10-31 (docs/plans/2026-10-23-roost-owner-words.md, W8–W11): what you said in the chat counts.

W8: "Apply now" outside a POST form only opens a form. W9: when the bot forgets to quote you, your newest own message
is the quote. W10: a button you said Yes to on a card clicks again with no card while the page has not moved.
W11: the check's one-word answer is logged. No real model."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import AsyncIterator

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box, PageTarget, resolution_to_json
from roost.config import load_config
from roost.crypto.encryption import encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, TurnDone
from roost.owner_words.again import approved_before, repeats_approved
from roost.owner_words.check import CHECK_SYSTEM, OwnerFacts, words_fit
from roost.owner_words.quote import your_quote
from roost.talk.store import TalkStore
from roost.talk.verdict import GateContext
from team_helpers import make_bot

_FENCE = SiteFence(frozenset({"www.upwork.com"}))
_JOB = "https://www.upwork.com/nx/search/jobs/details/~0221"


def _target(text: str, **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False)
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(text: str, url: str = _JOB, **over: object) -> ActResolution:
    target = _target(text, **over)
    return ActResolution(tool="click", url=url, host="www.upwork.com", target=target, point=(140, 215),
                         covered_by="", nav_host="", commit=commit_class(target))


def _ctx(*, cards: bool = True) -> GateContext:
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=cards)
    return GateContext(allowed=frozenset({"click"}), tainted=True, approval=state, fence=_FENCE)


# -- W8: "Apply now" opens a form ------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["Apply now", "Apply", "Aplicar", "Postularse", "Apply filters"])
def test_apply_outside_a_post_form_is_browsing(label):
    assert commit_class(_target(label)) == "browsing"


def test_apply_that_submits_a_post_form_still_asks():
    assert commit_class(_target("Apply now", is_form_submit=True, form_method="post")) == "submit"


@pytest.mark.parametrize(("label", "cls"), [
    ("Submit proposal", "submit"), ("Confirm", "submit"), ("Send for 16 Connects", "send"), ("Buy Connects", "spend"),
])
def test_other_commit_words_are_unchanged(label, cls):
    assert commit_class(_target(label)) == cls


def test_apply_now_on_a_job_page_needs_no_card():
    assert judge_act("click", _click("Apply now"), _ctx(), _FENCE).decision == "do"


# -- W9: your newest message is the quote --------------------------------------------------------------------

@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _chat(cfg) -> tuple[str, str, str]:
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Chief")
    thread = await TalkStore(cfg).create_thread(user.id, bot.id)
    return user.id, bot.id, thread.id


async def test_with_no_quote_your_newest_own_message_is_the_quote(cfg):
    user_id, _bot, thread_id = await _chat(cfg)
    talk = TalkStore(cfg)
    await talk.add_message(user_id, thread_id, "user", "look at the vet clinic job")
    await talk.add_message(user_id, thread_id, "user", "check that job good and send proposel")
    await talk.add_message(user_id, thread_id, "bot", "send it to everyone")
    await talk.add_message(user_id, thread_id, "user", "pasted from a page", tainted=True)
    assert await your_quote(cfg, user_id, thread_id, None) == "check that job good and send proposel"
    assert await your_quote(cfg, user_id, thread_id, "") == "check that job good and send proposel"


async def test_with_no_messages_there_is_no_quote(cfg):
    user_id, _bot, thread_id = await _chat(cfg)
    assert await your_quote(cfg, user_id, thread_id, None) == ""


def test_the_check_counts_a_step_on_the_way_and_site_credits():
    assert "step on the way" in CHECK_SYSTEM and "Connects" in CHECK_SYSTEM
    assert "paying money" in CHECK_SYSTEM


class Saying:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


# -- W11: the check's answer is logged, one word only ----------------------------------------------------------

@pytest.mark.parametrize(("reply", "logged"), [("ask", "ask"), ("Sure, it fits because…", "other")])
async def test_a_no_from_the_check_logs_its_one_word(caplog, reply, logged):
    facts = OwnerFacts(words="send the proposal", host="www.upwork.com", action="send", button="Send", typed=None)
    with caplog.at_level(logging.WARNING, logger="roost.owner_words.check"):
        assert await words_fit(Saying(reply), facts) is False
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [f"owner words check answered: {logged} (action send on www.upwork.com)"]
    assert "proposal" not in messages[0]


async def test_a_fits_logs_nothing_at_warning(caplog):
    facts = OwnerFacts(words="send it", host="x.com", action="send", button="Send", typed=None)
    with caplog.at_level(logging.WARNING, logger="roost.owner_words.check"):
        assert await words_fit(Saying("fits"), facts) is True
    assert caplog.records == []


# -- W10: the button you said Yes to ------------------------------------------------------------------------

def test_the_same_submit_button_on_the_same_page_repeats_a_yes():
    yes = _click("Submit proposal")
    assert repeats_approved((yes,), _click("Submit proposal")) is True


@pytest.mark.parametrize("live", [
    _click("Submit proposal", url="https://www.upwork.com/ab/proposals/new"),   # the page moved on
    _click("Submit offer"),                                                       # another button
])
def test_another_page_or_button_does_not(live):
    assert repeats_approved((_click("Submit proposal"),), live) is False


@pytest.mark.parametrize("label", ["Send", "Buy now", "Delete", "Sign up"])
def test_send_spend_delete_and_account_never_repeat(label):
    """Clicking Send or Pay twice would send or pay twice."""
    assert repeats_approved((_click(label),), _click(label)) is False


def test_the_gate_lets_a_repeated_yes_through_only_in_your_chat():
    live = replace(_click("Submit proposal"), approved_again=True)
    verdict = judge_act("click", live, _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "approved")
    assert judge_act("click", live, _ctx(cards=False), _FENCE).decision == "never"
    send = replace(_click("Send"), approved_again=True)
    assert judge_act("click", send, _ctx(), _FENCE).decision == "ask"


async def _card(cfg, user_id: str, bot_id: str, thread_id: str, act: ActResolution, *, state: str,
                closed_at: str) -> None:
    dek = await get_user_dek(cfg, user_id)
    steps = json.dumps([{"tool": "click", "arguments": {"index": 3}, "topic": "browsing", "title": "Click",
                         "floor": "commit_click", "act": resolution_to_json(act)}])
    async with db_session(cfg) as db:
        await db.execute(
            "INSERT INTO approval_cards (id, user_id, bot_id, thread_id, kind, state, steps, request, created_at, "
            "closed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"c-{state}-{closed_at}", user_id, bot_id, thread_id, "ask", state,
             encrypt(steps, dek, user_aad(user_id, "approval_cards:steps")), "{}", closed_at, closed_at))
        await db.commit()


async def test_a_recent_yes_in_this_chat_is_found(cfg):
    user_id, bot_id, thread_id = await _chat(cfg)
    now = "2026-10-31T11:21:00+00:00"
    await _card(cfg, user_id, bot_id, thread_id, _click("Submit proposal"), state="approved",
                closed_at="2026-10-31T11:20:15+00:00")
    assert await approved_before(cfg, user_id, thread_id, _click("Submit proposal"), now=now) is True
    assert await approved_before(cfg, user_id, thread_id, _click("Submit offer"), now=now) is False
    assert await approved_before(cfg, user_id, "another-thread", _click("Submit proposal"), now=now) is False


async def test_an_old_or_declined_card_is_not_a_yes(cfg):
    user_id, bot_id, thread_id = await _chat(cfg)
    now = "2026-10-31T11:21:00+00:00"
    await _card(cfg, user_id, bot_id, thread_id, _click("Submit proposal"), state="approved",
                closed_at="2026-10-31T10:30:00+00:00")
    await _card(cfg, user_id, bot_id, thread_id, _click("Submit proposal"), state="declined",
                closed_at="2026-10-31T11:20:50+00:00")
    assert await approved_before(cfg, user_id, thread_id, _click("Submit proposal"), now=now) is False
