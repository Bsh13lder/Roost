"""Owner, 2026-11-03: "Why Fable's check? Use whatever brain is set for the bot." The checks that still need a model's
judgement (your words for a send, the create check, auto-review of a button Roost can't read, a routine's standing
permission) run on the bot's own model, which the run carries in ``GateContext.check_model``. Your words now also
cover account steps (sign up, register, save changes, log out), never a password or email change; and Enter in a box
whose own label says search is browsing. No real model: recording fakes only."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from roost.approvals.models import ApprovalState
from roost.auto_review.guard import AutoReviewGuard, ReviewPage
from roost.computer_use.commit_words import commit_class
from roost.computer_use.models import ActResolution, Box
from roost.create_check.guard import CreateCheckGuard
from roost.desk.page_targets import target_from_ax
from roost.llm.registry import DEFAULT_BOT_MODEL, OPUS, check_model
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, TurnDone
from roost.owner_words.constants import OWNER_WORDS_CLASSES
from roost.owner_words.guard import OwnerWordsGuard
from roost.owner_words.quote import words_may_cover
from roost.talk.verdict import GateContext, Verdict


class Saying:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True, auto_review=True)


def _ctx(model: str | None = OPUS.id) -> GateContext:
    return GateContext(allowed=frozenset({"click"}), approval=CARDS, owner_chat=True, check_model=model)


def _button(label: str, *, role: str = "button") -> ActResolution:
    ax = {"role": {"value": role}, "name": {"value": label}, "backendDOMNodeId": 5}
    target = target_from_ax(ax, Box(10, 10, 80, 20), {"tag": "button"})
    return ActResolution("click", "https://site.example/", "site.example", target, (50, 20), "", "",
                         commit_class(target), owner_words="please sign me up and save it")


def test_the_check_model_is_the_bots_own_or_the_default():
    assert check_model(OPUS.id) == OPUS.id
    assert check_model(None) == DEFAULT_BOT_MODEL


async def test_the_owner_words_check_runs_on_the_bots_model():
    worker = Saying("fits")
    verdict = Verdict("do", "owner_words")
    assert await OwnerWordsGuard(worker).confirm(verdict, {}, _ctx(), _button("Send")) == verdict
    assert worker.requests[0].model == OPUS.id


async def test_the_auto_review_runs_on_the_bots_model():
    worker = Saying("safe")
    verdict = Verdict("do", "auto_review")

    async def page() -> ReviewPage:
        return ReviewPage(request="open the menu", title="Shop")

    assert await AutoReviewGuard(worker).confirm(verdict, {}, _ctx(), _button("Menu"), page) == verdict
    assert worker.requests[0].model == OPUS.id


async def test_the_create_check_runs_on_the_bots_model():
    worker = Saying("fits")
    verdict = Verdict("do", "checked_create")

    async def words() -> tuple[str, ...]:
        return ("make me a bot called Scout for the news",)

    arguments = {"name": "Scout", "job": "news", "instructions": "Read the news."}
    assert await CreateCheckGuard(worker).confirm(verdict, arguments, words, model_id=OPUS.id) == verdict
    assert worker.requests[0].model == OPUS.id


async def test_with_no_model_on_the_run_the_default_bot_model_checks():
    worker = Saying("fits")
    await OwnerWordsGuard(worker).confirm(Verdict("do", "owner_words"), {}, _ctx(None), _button("Send"))
    assert worker.requests[0].model == DEFAULT_BOT_MODEL


# --- item 6: account steps -----------------------------------------------------------------------------------------

def test_account_is_a_class_your_words_cover():
    assert "account" in OWNER_WORDS_CLASSES


@pytest.mark.parametrize("label", ["Sign up", "Register", "Save changes", "Log out"])
def test_your_words_may_cover_an_account_step(label):
    r = _button(label)
    assert commit_class(r.target) == "account"
    assert words_may_cover(r, "commit_click")


@pytest.mark.parametrize("label", ["Change password", "Update email", "Cambiar contraseña", "Change email"])
def test_a_password_or_email_change_is_never_covered(label):
    assert not words_may_cover(_button(label), "commit_click")


# --- item 9: Enter in a box whose own label says search ----------------------------------------------------------

def test_enter_in_a_box_named_search_is_browsing():
    editable = {"name": "editable", "value": {"value": "richtext"}}
    ax = {"role": {"value": "textbox"}, "name": {"value": "Search or start a new chat"}, "backendDOMNodeId": 7,
          "properties": [editable]}
    box = target_from_ax(ax, Box(20, 70, 380, 36), {"tag": "div"})
    assert box.search_named and commit_class(box, key="Enter") == "browsing"
    composer = target_from_ax({**ax, "name": {"value": "Type a message"}}, Box(20, 70, 380, 36), {"tag": "div"})
    assert commit_class(composer, key="Enter") == "unknown"
