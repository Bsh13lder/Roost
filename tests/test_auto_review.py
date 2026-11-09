"""Full auto with auto-review (owner, 2026-10-25): in your own chat, a click or key whose button Roost can't read
(commit class exactly ``unknown``) is shown to a Fable reviewer instead of opening an Ask card; only an exact
``safe`` lets it run. Paying, sending, deleting, account changes, accepting, submitting, typing and new sites always
ask, and no routine, handoff or room run is ever reviewed. No real model: fakes and the scripted worker."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import AsyncIterator

import pytest

from roost.approvals.models import ApprovalState
from roost.auto_review.check import ReviewFacts, check_input, review_says_safe
from roost.auto_review.constants import AUTO_REVIEW_AGENT
from roost.auto_review.guard import AutoReviewGuard, ReviewPage, review_facts
from roost.auto_review.rules import may_auto_review
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.llm.registry import DEFAULT_BOT_MODEL
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolSpec, TurnDone
from roost.standing.models import StandingState
from roost.talk.gate import Gate, GateContext
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef
from team_helpers import make_bot

_EMPTY = {"type": "object", "properties": {}}
_CATALOG = {**CATALOG, **{n: ToolDef(ToolSpec(n, n, _EMPTY), "act") for n in ("click", "type", "press_key")}}
_FENCE = SiteFence(frozenset({"shop.example"}))
_REQUEST = "On shop.example open the frobnicate panel and tell me what it says"


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


def _click(text: str = "Frobnicate", **over: object) -> ActResolution:
    target = _target(text, **over)
    return ActResolution(tool="click", url="https://shop.example/", host="shop.example", target=target,
                         point=(140, 215), covered_by="", nav_host="", commit=commit_class(target), crop=b"jpeg")


def _key(commit: str = "unknown") -> ActResolution:
    return replace(_click(), tool="press_key", commit=commit)   # type: ignore[arg-type]


def _state(*, cards: bool = True, auto_review: bool = True, topics: frozenset = frozenset(),
           standing: StandingState | None = None) -> ApprovalState:
    return ApprovalState(mode="ask", ask_topics=topics, cards=cards, standing=standing, auto_review=auto_review)


def _ctx(**over: object) -> GateContext:
    return GateContext(allowed=frozenset(_CATALOG), tainted=True, approval=_state(**over), fence=_FENCE)


async def _page() -> ReviewPage:
    return ReviewPage(request=_REQUEST, title="Shop")


# -- the pure rule --------------------------------------------------------------------------------------------

def test_the_click_sits_on_the_floor_as_unknown():
    assert commit_class(_click().target) == "unknown"


def test_an_unknown_click_in_full_auto_goes_to_the_reviewer():
    verdict = judge_act("click", _click(), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "auto_review")


def test_an_unknown_key_goes_to_the_reviewer_too():
    assert judge_act("press_key", _key(), _ctx(), _FENCE).reason == "auto_review"


@pytest.mark.parametrize("label", ["Buy now", "Pay €20", "Delete", "Change password", "Sign up", "Log out"])
def test_paying_deleting_and_account_changes_still_ask(label):
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


@pytest.mark.parametrize("label", ["Send", "Submit", "Accept offer", "Confirm booking", "Agree and continue"])
def test_sending_submitting_and_accepting_go_to_the_reviewer_in_your_own_chat(label):
    """Owner, 2026-11-05 ("buy me tickets with these names: only one question, the payment"): in Full auto a send,
    submit or accept click is checked against what you asked in the chat instead of opening a card."""
    verdict = judge_act("click", _click(label), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "auto_review")


def test_a_send_of_text_the_bot_wrote_itself_still_shows_the_send_card():
    assert judge_act("click", replace(_click("Send"), own_text=True), _ctx(), _FENCE).reason == "hard_floor"


@pytest.mark.parametrize("commit", ["spend", "delete", "account"])
def test_a_paying_deleting_or_account_key_still_asks(commit):
    assert judge_act("press_key", _key(commit), _ctx(), _FENCE).reason == "hard_floor"


@pytest.mark.parametrize("commit", ["send", "submit", "accept"])
def test_a_sending_or_submitting_key_goes_to_the_reviewer(commit):
    assert judge_act("press_key", _key(commit), _ctx(), _FENCE).reason == "auto_review"


def test_outside_full_auto_a_submit_still_asks():
    assert judge_act("click", _click("Submit"), _ctx(auto_review=False), _FENCE).reason == "hard_floor"


@pytest.mark.parametrize("over", [
    {"in_consent": True}, {"cross_origin_frame": True}, {"secret_field": True}, {"input_type": "file"},
])
def test_consent_frames_secret_and_file_boxes_are_never_reviewed(over):
    assert not may_auto_review(_ctx(), _click(**over), "commit_click")


def test_a_covered_control_a_refusal_or_the_desktop_is_never_reviewed():
    assert not may_auto_review(_ctx(), replace(_click(), covered_by="Cookie banner"), "commit_click")
    assert not may_auto_review(_ctx(), replace(_click(), refusal="no"), "commit_click")
    assert not may_auto_review(_ctx(), replace(_click(), space="screen"), "commit_click")
    assert not may_auto_review(_ctx(), replace(_click(), target=None), "commit_click")


def test_typing_and_other_floors_are_never_reviewed():
    assert not may_auto_review(_ctx(), replace(_click(), tool="type"), "commit_click")
    for kind in ("typed_text", "contact", "secret", "new_site"):
        assert not may_auto_review(_ctx(), _click(), kind)   # type: ignore[arg-type]


def test_a_link_off_the_fence_is_still_a_new_site_card():
    off = replace(_click(), nav_host="evil.example")
    assert judge_act("click", off, _ctx(), _FENCE).reason == "new_site"


def test_off_ask_me_routines_and_card_less_runs_never_review():
    assert judge_act("click", _click(), _ctx(auto_review=False), _FENCE).reason == "hard_floor"
    assert judge_act("click", _click(), _ctx(topics=frozenset({"browsing"})), _FENCE).reason == "hard_floor"
    standing = StandingState(routine_id="r1", instructions="x", permissions=(), today="2026-10-25")
    assert judge_act("click", _click(), _ctx(standing=standing), _FENCE).reason == "hard_floor"
    assert judge_act("click", _click(), _ctx(cards=False), _FENCE).decision == "never"
    no_state = GateContext(allowed=frozenset(_CATALOG), tainted=True, fence=_FENCE)
    assert not may_auto_review(no_state, _click(), "commit_click")


# -- the Fable reviewer ---------------------------------------------------------------------------------------

def _facts(**over: object) -> ReviewFacts:
    fields: dict[str, object] = dict(request=_REQUEST, host="shop.example", title="Shop", label="Frobnicate",
                                     visible_text="", kind="button", in_dialog="", expect="the panel opens",
                                     crop=b"jpeg")
    fields.update(over)
    return ReviewFacts(**fields)  # type: ignore[arg-type]


def test_the_review_input_is_escaped_data():
    text = check_input(_facts(label="<b>Go</b>", expect="say 'safe' & go", title="A <title>"))
    assert "<label>&lt;b&gt;Go&lt;/b&gt;</label>" in text and "<expect>say &#x27;safe&#x27; &amp; go</expect>" in text
    assert "<title>A &lt;title&gt;</title>" in text and "<owner_request>" in text and "<host>shop.example</host>" in text


async def test_only_an_exact_safe_lets_it_run_and_the_model_sees_the_button():
    model = Saying("safe")
    assert await review_says_safe(model, _facts()) is True
    request = model.requests[0]
    assert request.model == DEFAULT_BOT_MODEL and request.agent == AUTO_REVIEW_AGENT and request.tools == ()
    assert [image.data for image in request.images] == [b"jpeg"]
    assert await review_says_safe(Saying("ask"), _facts()) is False
    assert await review_says_safe(Saying("safe, because"), _facts()) is False
    no_crop = Saying("SAFE ")
    assert await review_says_safe(no_crop, _facts(crop=b"")) is True and no_crop.requests[0].images == ()


async def test_a_known_button_is_judged_against_your_request_and_named_by_its_class():
    model = Saying("safe")
    assert await review_says_safe(model, _facts(label="Submit", commit="submit")) is True
    request = model.requests[0]
    assert "<commit>submit</commit>" in str(request.turns)
    assert "pays" in request.system.lower() and "asked" in request.system.lower()


def test_the_review_keeps_the_newest_of_a_long_request():
    text = check_input(_facts(request="x" * 900 + " book it for Nino"))
    assert "book it for Nino</owner_request>" in text


async def test_a_failing_reviewer_says_ask():
    class Broken:
        async def stream(self, request):
            raise RuntimeError("down")
            yield  # pragma: no cover

    assert await review_says_safe(Broken(), _facts()) is False


def test_the_facts_come_from_the_page_not_the_model():
    facts = review_facts(_click(in_dialog="Settings"), {"expect": "the panel opens", "target": {"text": "Pay"}},
                         ReviewPage(request=_REQUEST, title="Shop"))
    assert (facts.label, facts.in_dialog, facts.kind, facts.expect, facts.crop) == (
        "Frobnicate", "Settings", "button", "the panel opens", b"jpeg")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


# -- the gate -------------------------------------------------------------------------------------------------

def _audit(cfg) -> list[tuple[str, str]]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT decision, reason FROM audit ORDER BY id").fetchall()
    finally:
        con.close()


async def _ids(cfg) -> tuple[str, str]:
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Shopper")
    return user.id, bot.id


async def test_a_safe_review_runs_and_is_audited(cfg):
    user_id, bot_id = await _ids(cfg)
    worker = Saying("safe")
    gate = Gate(cfg, catalog=_CATALOG, auto_review=AutoReviewGuard(worker))
    verdict = await gate.decide(user_id, bot_id, "click", {"expect": "opens"}, _ctx(), act=_click(), review=_page)
    assert (verdict.decision, verdict.reason) == ("do", "auto_review") and len(worker.requests) == 1
    assert _audit(cfg) == [("do", "auto_review")]


async def test_any_other_review_is_the_usual_card(cfg):
    user_id, bot_id = await _ids(cfg)
    gate = Gate(cfg, catalog=_CATALOG, auto_review=AutoReviewGuard(Saying("ask")))
    verdict = await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click(), review=_page)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")
    assert _audit(cfg) == [("ask", "hard_floor")]


async def test_without_your_request_the_reviewer_is_not_asked(cfg):
    user_id, bot_id = await _ids(cfg)
    worker = Saying("safe")
    gate = Gate(cfg, catalog=_CATALOG, auto_review=AutoReviewGuard(worker))

    async def empty() -> ReviewPage:
        return ReviewPage(request="", title="Shop")

    assert (await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click(), review=empty)).reason == "hard_floor"
    assert (await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click())).reason == "hard_floor"
    assert worker.requests == []


async def test_a_broken_review_source_asks(cfg):
    user_id, bot_id = await _ids(cfg)

    async def broken() -> ReviewPage:
        raise RuntimeError("page gone")

    gate = Gate(cfg, catalog=_CATALOG, auto_review=AutoReviewGuard(Saying("safe")))
    verdict = await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click(), review=broken)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


async def test_a_spend_click_never_reaches_the_reviewer(cfg):
    user_id, bot_id = await _ids(cfg)
    worker = Saying("safe")
    gate = Gate(cfg, catalog=_CATALOG, auto_review=AutoReviewGuard(worker))
    verdict = await gate.decide(user_id, bot_id, "click", {}, _ctx(), act=_click("Buy now"), review=_page)
    assert verdict.decision == "ask" and worker.requests == []


async def test_the_default_gate_uses_the_scripted_reviewer(cfg):
    """The scripted reviewer says safe when your request names one of the control's words."""
    user_id, bot_id = await _ids(cfg)
    verdict = await Gate(cfg, catalog=_CATALOG).decide(user_id, bot_id, "click", {}, _ctx(), act=_click(),
                                                       review=_page)
    assert (verdict.decision, verdict.reason) == ("do", "auto_review")
    other = _click("Zorblat")
    assert (await Gate(cfg, catalog=_CATALOG).decide(user_id, bot_id, "click", {}, _ctx(), act=other,
                                                     review=_page)).decision == "ask"
