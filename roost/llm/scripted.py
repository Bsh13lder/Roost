"""The deterministic test/dev model — never calls out, never costs a token.

Used by every test (``tests/conftest.py`` forces ``ROOST_MODEL=scripted``
session-wide) and by ``ROOST_MODEL=scripted`` in a real run. It never
imports ``claude_agent_sdk`` and never starts a process.
"""

from __future__ import annotations

from collections import deque
from typing import AsyncIterator, Sequence

from roost.constants import (
    SCRIPTED_USAGE_CACHE_READ,
    SCRIPTED_USAGE_CACHE_WRITE,
    SCRIPTED_USAGE_INPUT,
    SCRIPTED_USAGE_OUTPUT,
)
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, TurnDone, Usage

# Every scripted call's fake token usage, so tests (and the scripted E2E) see numbers (token usage plan).
SCRIPTED_USAGE = Usage(input=SCRIPTED_USAGE_INPUT, output=SCRIPTED_USAGE_OUTPUT, cache_read=SCRIPTED_USAGE_CACHE_READ,
                       cache_write=SCRIPTED_USAGE_CACHE_WRITE)


class ScriptedModel:
    """Replays a fixed script of events, one scripted turn per call.

    With no script left, ``echo=True`` (the default) makes it answer with
    a fixed, recognizable reply derived from the last user turn — enough
    for an end-to-end smoke test to prove a message really round-tripped
    through the turn loop without needing a real LLM.
    """

    def __init__(
        self,
        script: Sequence[Sequence[ModelEvent]] | None = None,
        echo: bool = True,
    ) -> None:
        self._script: deque[Sequence[ModelEvent]] = deque(script or ())
        self._echo = echo

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        if self._script:
            for event in self._script.popleft():
                yield event
            return

        if self._echo:
            last_user_text = next(
                (turn.text for turn in reversed(request.turns) if turn.role == "user"),
                "",
            )
            yield TextDelta(f"I heard: {last_user_text}")
            yield TurnDone("end_turn", SCRIPTED_USAGE)
