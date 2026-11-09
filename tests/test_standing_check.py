"""The Fable check (Step 3): one Fable request with the routine's instructions and the act as escaped fields; only
an exact ``fits`` lets the act through. Anything else, a tool call, an error or a timeout is "ask". The reply is
never logged. No real model: fakes and the scripted worker."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import pytest

from roost.llm.registry import DEFAULT_BOT_MODEL
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.standing import check as check_module
from roost.standing.check import ActFacts, act_fits, check_input
from roost.standing.constants import STANDING_CHECK_AGENT, STANDING_CHECK_TYPED_CHARS

FACTS = ActFacts(host="x.com", action="post", words="Post", typed=None)


class Saying:
    def __init__(self, *parts: object) -> None:
        self.parts = parts
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        for part in self.parts:
            if isinstance(part, Exception):
                raise part
            yield TextDelta(part) if isinstance(part, str) else part  # type: ignore[misc]
        yield TurnDone("end_turn")


class Hanging:
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        await asyncio.sleep(10)
        yield TurnDone("end_turn")


def test_the_input_is_escaped_structured_fields():
    text = check_input("Post <b>weekly</b> & stop", ActFacts("x.com", "post", "<Post>", "a" * 500 + "<script>"))
    assert "<instructions>Post &lt;b&gt;weekly&lt;/b&gt; &amp; stop</instructions>" in text
    assert "<host>x.com</host>" in text and "<action>post</action>" in text
    assert "<button>&lt;Post&gt;</button>" in text
    typed = text.split("<typed>")[1].split("</typed>")[0]
    assert typed == "a" * STANDING_CHECK_TYPED_CHARS and "<script>" not in text


def test_no_typed_text_leaves_the_field_out():
    assert "<typed>" not in check_input("Post it", FACTS)


async def test_fits_is_the_only_yes_and_it_asks_the_bots_model():
    model = Saying(" Fits\n")
    assert await act_fits(model, "Post the weekly update", FACTS) is True
    request = model.requests[0]
    assert request.model == DEFAULT_BOT_MODEL and request.agent == STANDING_CHECK_AGENT and request.tools == ()


@pytest.mark.parametrize("parts", [
    ("ask",), ("fits, but check the link",), ("",), ("I think it fits",), ("fi", "ts?"),
    (ToolCallRequested("c1", "click", {}),), (RuntimeError("boom"),),
])
async def test_anything_but_fits_is_ask(parts):
    assert await act_fits(Saying(*parts), "Post the weekly update", FACTS) is False


async def test_a_timeout_is_ask(monkeypatch):
    monkeypatch.setattr(check_module, "STANDING_CHECK_TIMEOUT_S", 0.01)
    assert await act_fits(Hanging(), "Post the weekly update", FACTS) is False


async def test_the_reply_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    await act_fits(Saying("SECRET-REPLY-WORDS"), "Post", FACTS)
    await act_fits(Saying(RuntimeError("SECRET-ERROR-WORDS")), "Post", FACTS)
    assert "SECRET-REPLY-WORDS" not in caplog.text and "SECRET-ERROR-WORDS" not in caplog.text


async def test_the_scripted_worker_fits_only_a_host_the_instructions_name():
    worker = ScriptedWorker()
    assert await act_fits(worker, "Every Monday post the update on x.com", FACTS) is True
    assert await act_fits(worker, "Every Monday post the update on linkedin.com", FACTS) is False
