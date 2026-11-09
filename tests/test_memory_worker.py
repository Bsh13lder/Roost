"""Worker calls for memory: ask_worker, the scripted worker, and the factory."""

from __future__ import annotations

import asyncio
import json

import pytest

from roost.config import load_config
from roost.llm.registry import WORKER, make_worker_model
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.memory import worker as worker_module
from roost.memory.worker import CAPTURE_AGENT, SUMMARY_AGENT, WorkerError, ask_worker


class RecordingModel:
    def __init__(self, events):
        self.requests: list[ModelRequest] = []
        self._events = events

    async def stream(self, request):
        self.requests.append(request)
        for event in self._events:
            yield event


class SlowModel:
    async def stream(self, request):
        await asyncio.sleep(1)
        yield TextDelta("late")


async def test_ask_worker_joins_text_and_uses_the_worker_model():
    model = RecordingModel([TextDelta("a"), TextDelta("b"), TurnDone("end_turn")])
    out = await ask_worker(model, agent=CAPTURE_AGENT, system="sys", text="hello")
    assert out == "ab"
    request = model.requests[0]
    assert request.model == WORKER
    assert request.tools == ()
    assert request.agent == CAPTURE_AGENT
    assert request.system == "sys"
    assert request.turns[0].text == "hello"


async def test_a_tool_call_from_the_worker_is_an_error():
    model = RecordingModel([ToolCallRequested("1", "x", {}), TurnDone("tool_use")])
    with pytest.raises(WorkerError):
        await ask_worker(model, agent=CAPTURE_AGENT, system="s", text="t")


async def test_a_slow_worker_times_out(monkeypatch):
    monkeypatch.setattr(worker_module, "MEMORY_WORKER_TIMEOUT_S", 0.01)
    with pytest.raises(TimeoutError):
        await ask_worker(SlowModel(), agent=CAPTURE_AGENT, system="s", text="t")


def _capture_text(body: str) -> str:
    return f"<user_messages>\n{body}\n</user_messages>"


async def test_the_scripted_worker_captures_remember_and_prefer_sentences():
    text = _capture_text("Remember that Ana&#x27;s birthday is in May. Hello there. I prefer short answers!")
    out = await ask_worker(ScriptedWorker(), agent=CAPTURE_AGENT, system="s", text=text)
    items = json.loads(out)["items"]
    assert items == [
        {"kind": "about_you", "text": "Ana's birthday is in May", "importance": 5},
        {"kind": "preference", "text": "Prefers short answers", "importance": 3},
    ]


async def test_the_scripted_worker_keeps_at_most_the_max_items():
    text = _capture_text("\n".join(f"Remember item {n}" for n in range(6)))
    out = await ask_worker(ScriptedWorker(), agent=CAPTURE_AGENT, system="s", text=text)
    assert len(json.loads(out)["items"]) == 3


async def test_the_scripted_worker_summarises_by_line_count():
    text = "Previous summary:\n<summary>\n(none)\n</summary>\n<chat>\n[a] You: hi\n[b] Bot: yo\ncontinued\n</chat>"
    out = await ask_worker(ScriptedWorker(), agent=SUMMARY_AGENT, system="s", text=text)
    assert out == "A summary of the earlier chat (2 lines)."


async def test_the_scripted_worker_answers_nothing_for_other_agents():
    assert await ask_worker(ScriptedWorker(), agent="other", system="s", text="t") == ""


def test_scripted_mode_gives_the_scripted_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOST_MODEL_SCRIPT", str(tmp_path / "script.json"))
    assert isinstance(make_worker_model(load_config()), ScriptedWorker)
