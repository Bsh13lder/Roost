"""``ScriptedTeamModel`` — the deterministic model, scripted per bot.

Scripts are keyed by bot name (case-insensitive, ``ModelRequest.agent``);
each ``stream()`` call replays that bot's next step. A bot with no script
left falls back to ``ScriptedModel``'s echo. ``from_json`` validates the
external JSON with pydantic — it is what ``ROOST_MODEL_SCRIPT`` loads for
the Playwright E2E (Task 9). Never calls out, never costs a token."""

from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from pathlib import Path
from typing import Any, AsyncIterator, Literal, Mapping, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from roost.llm.scripted import SCRIPTED_USAGE, ScriptedModel
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolCallRequested, TurnDone


MAX_WAIT_SECONDS = 30   # a wait step is for the E2E's slow bot, never a real delay
ECHO_MAX_CHARS = 200    # an echo step says this much of the last tool result's first line
ECHO_PREFIX = "Last result: "
_TAG = re.compile(r"<[^>]*>")


class _TextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class _ToolStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)


class _WaitStep(BaseModel):
    """E2E only: hold the step for this many seconds before its next part (a bot that is slow to answer)."""
    model_config = ConfigDict(extra="forbid")
    wait: float = Field(gt=0, le=MAX_WAIT_SECONDS)


class _EchoStep(BaseModel):
    """E2E only: say the first line of this run's last tool result, as inline code (C3: the E2E reads what the
    screen loop answered, such as "Look first: …", or where a look found the page)."""
    model_config = ConfigDict(extra="forbid")
    echo: Literal["tool"]


class _Echo:
    pass


def _echo_text(request: ModelRequest) -> str:
    last = next((turn.text for turn in reversed(request.turns) if turn.role == "tool"), "")
    line = _TAG.sub("", last).strip().split("\n", 1)[0][:ECHO_MAX_CHARS].replace("`", "'")
    return f"{ECHO_PREFIX}`{line}`"           # as code, so the chat shows it verbatim (no link, no markdown)


class _Pause:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds


_Part = Union[_TextStep, _ToolStep, _WaitStep, _EchoStep]
_SCRIPT = TypeAdapter(dict[str, list[list[_Part]]])


def _event(agent: str, index: int, n: int, part: _Part) -> Any:
    if isinstance(part, _TextStep):
        return TextDelta(part.text)
    if isinstance(part, _EchoStep):
        return _Echo()
    if isinstance(part, _WaitStep):
        return _Pause(part.wait)
    return ToolCallRequested(id=f"{agent.casefold()}-{index}-{n}", name=part.tool, arguments=part.args)


def _step_events(agent: str, index: int, step: Sequence[_Part]) -> tuple[ModelEvent, ...]:
    events = tuple(_event(agent, index, n, part) for n, part in enumerate(step))
    calls_tools = any(isinstance(event, ToolCallRequested) for event in events)
    return (*events, TurnDone("tool_use" if calls_tools else "end_turn", SCRIPTED_USAGE))


class ScriptedTeamModel:
    def __init__(self, scripts: Mapping[str, Sequence[Sequence[ModelEvent]]], echo: bool = True) -> None:
        self._scripts = {name.casefold(): deque(steps) for name, steps in scripts.items()}
        self._fallback = ScriptedModel(echo=echo)

    @classmethod
    def from_json(cls, data: Any) -> "ScriptedTeamModel":
        parsed = _SCRIPT.validate_python(data)
        return cls({name: [_step_events(name, i, step) for i, step in enumerate(steps)] for name, steps in parsed.items()})

    @classmethod
    def from_file(cls, path: Path) -> "ScriptedTeamModel":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        steps = self._scripts.get(request.agent.casefold())
        if steps:
            for event in steps.popleft():
                if isinstance(event, _Pause):
                    await asyncio.sleep(event.seconds)
                    continue
                yield TextDelta(_echo_text(request)) if isinstance(event, _Echo) else event
            return
        async for event in self._fallback.stream(request):
            yield event
