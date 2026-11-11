"""Keeping the cache warm (docs/plans/2026-11-09-roost-tool-groups.md §4): old tool results fold to a one-line stub
in batches, the newest ones stay whole, and short or error results are never folded. The stored turns never change;
only the request the model sees does."""

from __future__ import annotations

from roost.constants import COMPACT_AFTER_STEPS, COMPACT_BATCH_STEPS, COMPACT_KEEP_RESULTS, COMPACT_MIN_CHARS
from roost.llm.types import SCREENSHOT_SHOWN, ChatTurn, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.talk.compact import COMPACTED_RESULT_TEXT, compact_results
from roost.talk.run_request import request_turns
from roost.talk.steps import step_loop

_PAGE = "<untrusted_page url=\"https://a.example\">" + "words " * 400 + "</untrusted_page>"


def _result(i: int, text: str = _PAGE, name: str = "read_page") -> ChatTurn:
    return ChatTurn("tool", text, tool_call_id=f"c{i}", tool_name=name)


def _run(n: int, **kw) -> tuple[ChatTurn, ...]:
    return tuple(turn for i in range(n) for turn in (ChatTurn("assistant", f"step {i}"), _result(i, **kw)))


def _folded(turns: tuple[ChatTurn, ...]) -> list[int]:
    return [int(t.tool_call_id[1:]) for t in turns if t.role == "tool" and t.text == COMPACTED_RESULT_TEXT]


def test_nothing_folds_until_enough_results_came_after_the_oldest():
    assert _folded(compact_results(_run(COMPACT_AFTER_STEPS + COMPACT_BATCH_STEPS - 1))) == []


def test_results_fold_in_batches_not_one_per_step():
    first_batch = COMPACT_AFTER_STEPS + COMPACT_BATCH_STEPS
    assert _folded(compact_results(_run(first_batch))) == list(range(COMPACT_BATCH_STEPS))
    # The next results change nothing until a whole batch has gone by (the cache prefix stays the same).
    for extra in range(1, COMPACT_BATCH_STEPS):
        assert _folded(compact_results(_run(first_batch + extra))) == list(range(COMPACT_BATCH_STEPS))
    assert _folded(compact_results(_run(first_batch + COMPACT_BATCH_STEPS))) == list(range(2 * COMPACT_BATCH_STEPS))


def test_the_newest_results_always_stay_whole():
    turns = compact_results(_run(60))
    results = [t for t in turns if t.role == "tool"]
    assert all(t.text == _PAGE for t in results[-COMPACT_KEEP_RESULTS:])
    assert all(t.text == _PAGE for t in results[-COMPACT_AFTER_STEPS:])


def test_short_results_card_answers_and_errors_are_never_folded():
    short = "x" * (COMPACT_MIN_CHARS - 1)
    turns = compact_results(_run(40, text=short))
    assert _folded(turns) == []
    errors = ("Refused: not yours. " + _PAGE, "Not performed: the user has control. " + _PAGE,
              "Blocked: shop.example shows a sign-in page. " + _PAGE, "Stuck: " + _PAGE, "Not shown: " + _PAGE)
    for text in errors:
        assert _folded(compact_results(_run(40, text=text))) == [], text[:20]
    answers = tuple(turn for i in range(40) for turn in (ChatTurn("assistant", "s"), ChatTurn("user", _PAGE)))
    assert compact_results(answers) == answers


def test_the_newest_look_stays_whole_for_its_picture():
    look = f"<untrusted_page>look</untrusted_page> {SCREENSHOT_SHOWN} " + "x " * 300
    turns = tuple(turn for i in range(40) for turn in (ChatTurn("assistant", "s"), _result(i, name="look" if i == 2 else "read_page")))
    turns = tuple(t if t.tool_name != "look" else ChatTurn("tool", look, t.tool_call_id, "look") for t in turns)
    folded = _folded(compact_results(turns))
    assert 2 not in folded and 1 in folded and 3 in folded


def test_the_stored_turns_never_change():
    stored = _run(40)
    compact_results(stored)
    assert all(t.text == _PAGE for t in stored if t.role == "tool")


def test_request_turns_puts_the_chat_before_the_folded_run():
    history = (ChatTurn("user", "read these pages"),)
    turns = request_turns(history, _run(40))
    assert turns[0] == history[0]
    assert COMPACTED_RESULT_TEXT in {t.text for t in turns}


class _Recording:
    def __init__(self, steps):
        self._steps = list(steps)
        self.requests: list[ModelRequest] = []

    async def stream(self, request):
        self.requests.append(request)
        for event in self._steps.pop(0):
            yield event


class _PageRunner:
    block = None
    parked = None
    tainted = False

    async def run(self, call):
        return _PAGE


async def test_the_step_loop_shows_the_model_the_folded_run(monkeypatch):
    n = COMPACT_AFTER_STEPS + COMPACT_BATCH_STEPS + 1
    steps = [[ToolCallRequested(id=f"c{i}", name="read_page", arguments={}), TurnDone("tool_use")] for i in range(n)]
    model = _Recording([*steps, [TextDelta("Done."), TurnDone("end_turn")]])

    async def on_delta(text: str) -> None:
        pass

    reply, capped = await step_loop(
        model=model, tool_runner=_PageRunner(), max_steps=n + 5, deadline_s=30, on_delta=on_delta,
        request_for=lambda added: ModelRequest(system="s", turns=request_turns((), added), tools=(), model="m"),
    )
    assert reply == "Done." and not capped
    last = model.requests[-1]
    assert len(_folded(last.turns)) == COMPACT_BATCH_STEPS
    assert sum(1 for t in last.turns if t.role == "tool" and t.text == _PAGE) == n - COMPACT_BATCH_STEPS
