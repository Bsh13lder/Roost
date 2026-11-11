"""Old tool results fold to a stub (keeping the cache warm, docs/plans/2026-11-09-roost-tool-groups.md §4).

A run's transcript used to carry every tool result to its last step: a long browsing run re-sent every 12k-character
page on every step. Here a result with ``COMPACT_AFTER_STEPS`` results after it becomes ``COMPACTED_RESULT_TEXT``,
and the fold moves in batches of ``COMPACT_BATCH_STEPS`` so the prompt cache breaks once per batch, not once per
step. The newest ``COMPACT_KEEP_RESULTS`` always stay whole, as do short results (an error, an id, a "Done"), a
refusal or block the bot must keep in mind, the newest look (its picture rides after it) and every user turn (a card
answer, a steered message). A "step" here is one tool result: a step with parallel calls counts each.

Only the request the model sees is folded (``roost/talk/run_request.py``); the stored turns never change, and the
run's taint was recorded when the result arrived, so folding changes nothing there."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from roost.constants import COMPACT_AFTER_STEPS, COMPACT_BATCH_STEPS, COMPACT_KEEP_RESULTS, COMPACT_MIN_CHARS
from roost.llm.types import ChatTurn

COMPACTED_RESULT_TEXT: Final = "[no longer shown; read it again if you need it]"
_LOOK: Final = "look"
# A result that starts like this is an outcome the bot must keep in view, never a page to forget.
_KEPT_PREFIXES: Final = ("Refused", "Not performed", "Not shown", "Blocked:", "Stuck:", "Asked:", "Error")


def _fold_count(results: int) -> int:
    """How many of the oldest results fold: whole batches only, once ``COMPACT_AFTER_STEPS`` came after them."""
    batches = (results - COMPACT_AFTER_STEPS) // COMPACT_BATCH_STEPS
    return max(0, min(batches * COMPACT_BATCH_STEPS, results - COMPACT_KEEP_RESULTS))


def _foldable(turn: ChatTurn) -> bool:
    return (turn.role == "tool" and len(turn.text) >= COMPACT_MIN_CHARS
            and not turn.text.lstrip().startswith(_KEPT_PREFIXES))


def compact_results(turns: tuple[ChatTurn, ...]) -> tuple[ChatTurn, ...]:
    """The turns as the model sees them: the oldest foldable results, in whole batches, as the stub."""
    results = tuple(i for i, turn in enumerate(turns) if turn.role == "tool")
    count = _fold_count(len(results))
    if count <= 0:
        return turns
    looks = tuple(i for i in results if turns[i].tool_name == _LOOK)
    newest_look = looks[-1] if looks else None
    fold = frozenset(i for i in results[:count] if i != newest_look and _foldable(turns[i]))
    if not fold:
        return turns
    return tuple(replace(turn, text=COMPACTED_RESULT_TEXT) if i in fold else turn for i, turn in enumerate(turns))
