"""One first line per run; the final answer is its own paragraph (chat-feel fix)."""

from __future__ import annotations

from types import SimpleNamespace

from roost.llm.types import ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.talk.steps import step_loop

_REQUEST = ModelRequest(system="", turns=(), tools=(), model="m")


class _Scripted:
    def __init__(self, steps):
        self._steps = list(steps)

    async def stream(self, request):
        for event in self._steps.pop(0):
            yield event


class _Runner:
    block = None
    parked = None

    async def run(self, call):
        return "ok"


def _call(n):
    return ToolCallRequested(id=f"c{n}", name="read_page", arguments={})


async def _run(steps):
    seen: list[str] = []

    async def on_delta(text):
        seen.append(text)

    model = _Scripted(steps)
    text, capped = await step_loop(
        model=model, request_for=lambda added: _REQUEST, tool_runner=_Runner(), max_steps=8,
        deadline_s=60, on_delta=on_delta,
    )
    return text, "".join(seen), capped


async def test_multi_step_run_keeps_one_on_it_line_and_a_separate_answer():
    text, streamed, capped = await _run([
        [TextDelta("On it: opening upwork.com in my browser."), _call(1), TurnDone("tool_use")],
        [TextDelta("On it: opening upwork.com in my browser."), _call(2), TurnDone("tool_use")],
        [TextDelta("On it: trying again."), _call(3), TurnDone("tool_use")],
        [TextDelta("Blocked: a sign-in page."), TurnDone("end_turn")],
    ])
    assert not capped
    for body in (text, streamed):
        assert body.count("On it:") == 1
        assert body == "On it: opening upwork.com in my browser.\n\nBlocked: a sign-in page."


async def test_a_one_step_answer_is_untouched():
    text, streamed, _ = await _run([[TextDelta("Hello."), TurnDone("end_turn")]])
    assert text == streamed == "Hello."
