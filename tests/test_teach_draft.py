"""The skill draft from a teach recording: the worker's JSON, or a plain draft when the worker can't help."""

from __future__ import annotations

import json

import pytest

from roost.constants import SKILL_BODY_MAX, TEACH_STEPS_MAX, TEACH_WORKER_AGENT
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.teach.draft import TeachRefused, make_draft, worker_input
from roost.teach import texts
from roost.teach.models import TeachStep

STEPS = (
    TeachStep(kind="click", host="shop.example", path="/", title="Shop", role="link", label="Orders"),
    TeachStep(kind="password", host="shop.example", path="/login", title="Sign in", role="field",
              label="Password"),
    TeachStep(kind="type", host="shop.example", path="/orders", title="Orders <b>", role="field", label="Item"),
)


class FakeWorker:
    def __init__(self, reply: str = "", *, tool: bool = False, fail: bool = False) -> None:
        self.reply = reply
        self.tool = tool
        self.fail = fail
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("down")
        if self.tool:
            yield ToolCallRequested("x", "web_search", {})
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


async def test_the_worker_answer_becomes_the_draft():
    reply = "Here: " + json.dumps({"name": "Reorder an item", "use_when": "the user wants to reorder",
                                   "steps": ["Open shop.example and go to Orders", "Ask the user to sign in"]})
    worker = FakeWorker(reply)
    draft = await make_draft(worker, STEPS, "Reorder from the shop")
    assert draft.name == "Reorder an item" and draft.use_when == "the user wants to reorder"
    assert draft.body == "1. Open shop.example and go to Orders\n2. Ask the user to sign in"
    [request] = worker.requests
    assert request.agent == TEACH_WORKER_AGENT and request.tools == ()
    text = request.turns[-1].text
    assert "<description>Reorder from the shop</description>" in text
    assert "Orders &lt;b&gt;" in text and "<b>" not in text.replace("<description>", "")


@pytest.mark.parametrize("worker", [
    FakeWorker("not json"), FakeWorker(json.dumps({"name": "x"})), FakeWorker("", tool=True),
    FakeWorker("", fail=True), FakeWorker(json.dumps({"name": "two\nlines", "use_when": "w", "steps": ["a"]})),
    FakeWorker(json.dumps({"name": "n", "use_when": "w", "steps": []})),
])
async def test_a_worker_that_cannot_help_gives_the_plain_draft(worker):
    draft = await make_draft(worker, STEPS, None)
    assert draft.name == "Task on shop.example"
    assert draft.use_when == "doing the task the user showed on shop.example"
    assert draft.body.startswith("1. On shop.example/ (“Shop”): click the link “Orders”")
    assert "ask the user to sign in" in draft.body


async def test_the_plain_draft_uses_your_description():
    draft = await make_draft(FakeWorker(""), STEPS, "Reorder from the shop")
    assert draft.name == "Reorder from the shop" and draft.use_when == "Reorder from the shop"


async def test_a_recording_with_no_web_page_gets_a_plain_name():
    draft = await make_draft(FakeWorker(""), (TeachStep(kind="browser"),), None)
    assert draft.name == "Taught task" and draft.body == "1. Use the browser's address bar or tabs"


async def test_a_secret_in_a_label_is_left_out_and_one_in_your_description_refuses():
    leaky = (TeachStep(kind="click", host="a.example", role="button", label="sk-ant-api03-" + "a" * 40),)
    draft = await make_draft(FakeWorker(""), leaky, None)
    assert draft.body == texts.LEFT_OUT_NOTE
    with pytest.raises(TeachRefused) as caught:
        await make_draft(FakeWorker(""), STEPS, "token=" + "a" * 20)
    assert caught.value.text.startswith("Not saved:")


def test_worker_input_quotes_every_line():
    text = worker_input(STEPS, None)
    assert "<description>" not in text and text.count("\n") >= 4


def _long_step(n: int) -> TeachStep:
    return TeachStep(kind="click", host=f"h{n}." + "a" * 70 + ".example", path="/" + "p" * 119, title="T" * 120,
                     role="r" * 80, label=f"{n} " + "L" * 77)


async def test_a_long_plain_draft_is_shortened_to_fit():
    """Review FAIL 2: 60 long steps still make a plain draft within the skill body limit."""
    steps = tuple(_long_step(n) for n in range(TEACH_STEPS_MAX))
    draft = await make_draft(FakeWorker(""), steps, None)
    assert len(draft.body) <= SKILL_BODY_MAX
    assert draft.body.startswith("1. On h0.") and texts.SHORTENED_NOTE in draft.body


async def test_a_label_with_an_email_is_left_out_of_the_plain_draft():
    steps = (TeachStep(kind="click", host="accounts.example", role="button", label="Use alice@example.com"),
             TeachStep(kind="click", host="accounts.example", role="button", label="Next"))
    draft = await make_draft(FakeWorker(""), steps, None)
    assert "alice@example.com" not in draft.body and "Next" in draft.body
    assert texts.LEFT_OUT_NOTE in draft.body
