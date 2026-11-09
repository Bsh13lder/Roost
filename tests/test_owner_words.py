"""W2–W4 (docs/plans/2026-10-23-roost-owner-words.md): a hard-floor send, submit, accept or delete (or typing) runs
with no card when the act quotes your own message and the Fable check says it fits. Spend, account changes, never
and routine runs are untouched. No real model: fakes and the scripted worker."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import AsyncIterator

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box, ClickIn, PageTarget, PressKeyIn, TypeIn
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.llm.registry import DEFAULT_BOT_MODEL
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolSpec, TurnDone
from roost.owner_words.check import OwnerFacts, check_input, words_fit
from roost.owner_words.constants import OWNER_CHECK_AGENT
from roost.owner_words.guard import OwnerWordsGuard
from roost.owner_words.quote import quote_is_yours, your_quote
from roost.standing.models import StandingState
from roost.talk.gate import Gate, GateContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef
from team_helpers import make_bot

_EMPTY = {"type": "object", "properties": {}}
_CATALOG = {**CATALOG, **{n: ToolDef(ToolSpec(n, n, _EMPTY), "act") for n in ("click", "type", "press_key")}}
_FENCE = SiteFence(frozenset({"www.upwork.com"}))
_ASKED = "reply to James: thanks, I will check it tomorrow and send it"


class Saying:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


def _target(text: str, **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False)
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(text: str = "Send", words: str = _ASKED, **over: object) -> ActResolution:
    target = _target(text, **over)
    return ActResolution(tool="click", url="https://www.upwork.com/messages", host="www.upwork.com", target=target,
                         point=(140, 215), covered_by="", nav_host="", commit=commit_class(target), owner_words=words)


def _typing(words: str = _ASKED, **over: object) -> ActResolution:
    box = _target("Write a message", kind="field", tag="textarea", editable=True, **over)
    return ActResolution(tool="type", url="https://www.upwork.com/messages", host="www.upwork.com", target=box,
                         point=(140, 215), covered_by="", nav_host="", commit="browsing", text_ok=False,
                         owner_words=words)


def _ctx(*, cards: bool = True, tainted: bool = True, standing: StandingState | None = None) -> GateContext:
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=cards, standing=standing)
    return GateContext(allowed=frozenset(_CATALOG), tainted=tainted, approval=state, fence=_FENCE)


# -- the quote is yours ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("quote", "ok"), [
    (_ASKED, True),
    ("reply to   James: thanks", True),          # whitespace forgiven, whole words
    ("send it", False),                           # under three words and not a whole message or line
    ("ply to James", False),                      # not whole words
    ("buy the credits", False),                   # not in your messages
    ("", False),
])
def test_a_quote_must_be_your_own_words(quote, ok):
    assert quote_is_yours(quote, (_ASKED, "hello")) is ok


def test_a_short_quote_counts_when_it_is_a_whole_message_or_line():
    assert quote_is_yours("send it", ("send it",)) is True
    assert quote_is_yours("send it", ("check James\nsend it",)) is True


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_only_your_own_untainted_newest_messages_are_sources(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Chief")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user.id, bot.id)
    await talk.add_message(user.id, thread.id, "user", "please delete the old draft for me")
    await talk.add_message(user.id, thread.id, "bot", "send the proposal to Iurie now")
    await talk.add_message(user.id, thread.id, "user", "post the update on the board", tainted=True)
    for n in range(3):
        await talk.add_message(user.id, thread.id, "user", f"message number {n} here")
    await talk.add_message(user.id, thread.id, "user", _ASKED)
    assert await your_quote(cfg, user.id, thread.id, "reply to James: thanks") == "reply to James: thanks"
    assert await your_quote(cfg, user.id, thread.id, "send the proposal to Iurie") == ""     # the bot's words
    assert await your_quote(cfg, user.id, thread.id, "post the update on the board") == ""   # tainted
    assert await your_quote(cfg, user.id, thread.id, "delete the old draft") == ""           # older than the last 3
    assert await your_quote(cfg, user.id, thread.id, None) == _ASKED                         # W9: your newest


# -- the inputs take it ---------------------------------------------------------------------------------------

def test_the_act_inputs_take_owner_words():
    assert ClickIn.model_validate({"target": {"text": "Send"}, "expect": "sent", "owner_words": "send it"}).owner_words
    assert TypeIn.model_validate({"text": "hi", "source": {"from": "message"}, "expect": "typed",
                                  "owner_words": "say hi"}).owner_words == "say hi"
    assert PressKeyIn.model_validate({"key": "Enter", "expect": "sent"}).owner_words is None


# -- the pure judge -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["Send", "Submit", "Accept offer", "Delete"])
def test_your_words_cover_send_submit_accept_and_delete(label):
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "owner_words")


def test_typing_needs_no_words_of_yours_at_all():
    # Owner, 2026-11-03: typing never asks, so it never needs your quote either.
    verdict = judge_act("type", _typing(), _ctx(), SiteFence(frozenset()), typed_chars=20)   # off a trusted site
    assert (verdict.decision, verdict.reason) == ("do", "allowed")


@pytest.mark.parametrize("label", ["Sign up", "Log out"])
def test_your_words_cover_account_steps(label):
    # Owner, 2026-11-03: sign up, register, save changes and log out are covered too.
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "owner_words")


@pytest.mark.parametrize("label", ["Buy now", "Pay €20", "Change password", "Frobnicate"])
def test_payments_password_changes_and_unknown_still_ask(label):
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_no_verified_quote_asks():
    verdict = judge_act("click", _click("Send", words=""), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_a_run_without_cards_never_uses_your_words():
    verdict = judge_act("click", _click("Send"), _ctx(cards=False), _FENCE)
    assert (verdict.decision, verdict.reason) == ("never", "needs_your_ok")


def test_a_routine_run_never_uses_your_words():
    standing = StandingState(routine_id="r1", instructions="x", permissions=(), today="2026-10-23")
    verdict = judge_act("click", _click("Send"), _ctx(standing=standing), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_never_stays_never():
    secret = _typing(secret_field=True)
    assert judge_act("type", secret, _ctx(), _FENCE, typed_chars=5).decision == "never"
    covered = replace(_click("Send"), covered_by="Cookie banner")
    assert judge_act("click", covered, _ctx(), _FENCE).decision == "ask"
    off_site = replace(_click("Send"), nav_host="evil.example")
    assert (judge_act("click", off_site, _ctx(), _FENCE).reason) == "new_site"


def test_contact_details_and_secrets_in_typing_still_ask():
    r = replace(_typing(), text_flags=frozenset({"contact"}))
    assert judge_act("type", r, _ctx(), _FENCE, typed_chars=20).reason == "hard_floor"


# -- the Fable check ------------------------------------------------------------------------------------------

def test_the_check_input_is_escaped_data():
    text = check_input(OwnerFacts(words="send <it>", host="x.com", action="send", button="<Send>", typed="a & b"))
    assert "<owner_words>send &lt;it&gt;</owner_words>" in text and "<button>&lt;Send&gt;</button>" in text
    assert "<typed>a &amp; b</typed>" in text


async def test_only_fits_lets_it_through_and_the_bots_model_is_asked():
    model = Saying("fits")
    facts = OwnerFacts(words=_ASKED, host="x.com", action="send", button="Send", typed=None)
    assert await words_fit(model, facts) is True
    assert model.requests[0].model == DEFAULT_BOT_MODEL and model.requests[0].agent == OWNER_CHECK_AGENT
    assert await words_fit(Saying("ask"), facts) is False
    assert await words_fit(Saying("fits, because"), facts) is False


# -- the gate -------------------------------------------------------------------------------------------------

def _audit(cfg) -> list[tuple[str, str]]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT decision, reason FROM audit ORDER BY id").fetchall()
    finally:
        con.close()


async def _ids(cfg) -> tuple[str, str]:
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Chief")
    return user.id, bot.id


async def test_a_fitting_act_runs_and_the_audit_says_your_words(cfg):
    user_id, bot_id = await _ids(cfg)
    worker = Saying("fits")
    gate = Gate(cfg, catalog=_CATALOG, owner_words=OwnerWordsGuard(worker))
    verdict = await gate.decide(user_id, bot_id, "click", {"expect": "sent", "owner_words": _ASKED}, _ctx(),
                                act=_click())
    assert (verdict.decision, verdict.reason) == ("do", "owner_words") and len(worker.requests) == 1
    assert _audit(cfg) == [("do", "owner_words")]


async def test_fable_saying_anything_else_asks(cfg):
    user_id, bot_id = await _ids(cfg)
    gate = Gate(cfg, catalog=_CATALOG, owner_words=OwnerWordsGuard(Saying("ask")))
    verdict = await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click())
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")
    assert _audit(cfg) == [("ask", "hard_floor")]


async def test_a_spend_act_with_your_words_never_reaches_fable(cfg):
    user_id, bot_id = await _ids(cfg)
    worker = Saying("fits")
    gate = Gate(cfg, catalog=_CATALOG, owner_words=OwnerWordsGuard(worker))
    verdict = await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click("Buy now", words="buy the credits now"))
    assert verdict.decision == "ask" and worker.requests == []


async def test_a_broken_check_asks(cfg, monkeypatch):
    user_id, bot_id = await _ids(cfg)
    guard = OwnerWordsGuard(Saying("fits"))

    async def broken(*_args, **_kw):
        raise RuntimeError("gone")

    monkeypatch.setattr(guard, "confirm", broken)
    verdict = await Gate(cfg, catalog=_CATALOG, owner_words=guard).decide(user_id, bot_id, "click", {}, _ctx(),
                                                                         act=_click())
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


async def test_the_default_gate_uses_the_scripted_worker_in_tests(cfg):
    """The scripted check says fits when your words name the control (here "send")."""
    user_id, bot_id = await _ids(cfg)
    verdict = await Gate(cfg, catalog=_CATALOG).decide(user_id, bot_id, "click", {}, _ctx(), act=_click())
    assert (verdict.decision, verdict.reason) == ("do", "owner_words")
    unrelated = _click("Delete", words="reply to James: thanks a lot")
    assert (await Gate(cfg, catalog=_CATALOG).decide(user_id, bot_id, "click", {}, _ctx(), act=unrelated)).decision == "ask"


async def test_one_message_asking_for_the_whole_proposal_covers_its_final_send(cfg):
    """Owner, 2026-11-01 ("like Grok"): one message asked for the search, the proposal and the send; Upwork's last
    button, "Send for 14 Connects", is a send (Connects are the site's own credits), so it runs with no card."""
    user_id, bot_id = await _ids(cfg)
    asked = "Search Upwork now for the best fresh job for me, pick one, and send the proposal yourself, for real."
    worker = Saying("fits")
    gate = Gate(cfg, catalog=_CATALOG, owner_words=OwnerWordsGuard(worker))
    act = _click("Send for 14 Connects", words=asked)
    assert act.commit == "send"
    verdict = await gate.decide(user_id, bot_id, "click", {"expect": "the proposal is sent"}, _ctx(), act=act)
    assert (verdict.decision, verdict.reason) == ("do", "owner_words") and len(worker.requests) == 1


def test_your_words_never_skip_the_card_for_text_the_bot_wrote():
    # Owner, 2026-11-03: the Send card always shows the bot's own text, even after "send it".
    assert judge_act("click", _click(), _ctx(), _FENCE).reason == "owner_words"
    own = replace(_click(), own_text=True)
    assert (judge_act("click", own, _ctx(), _FENCE).decision, judge_act("click", own, _ctx(), _FENCE).reason) == (
        "ask", "hard_floor")
    submit_again = replace(_click("Submit proposal"), own_text=True, approved_again=True)
    assert judge_act("click", submit_again, _ctx(), _FENCE).reason == "approved"          # W10 is unchanged
    assert judge_act("type", replace(_typing(), own_text=True), _ctx(), _FENCE).decision != "ask"
