"""``ScriptedTeamModel`` — per-bot scripts for tests and the Playwright E2E."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from roost.config import load_config
from roost.llm.registry import make_model
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ChatTurn, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.llm.scripted import SCRIPTED_USAGE


def _request(agent: str, text: str = "hi") -> ModelRequest:
    return ModelRequest(system="s", turns=(ChatTurn("user", text),), tools=(), model="m", agent=agent)


async def _events(model, agent: str, text: str = "hi"):
    return [event async for event in model.stream(_request(agent, text))]


async def test_each_bot_replays_its_own_script_one_step_per_call():
    model = ScriptedTeamModel.from_json({
        "Chief": [[{"tool": "ask_bot", "args": {"bot": "Scout", "task": "hours"}}], [{"text": "done"}]],
        "Scout": [[{"text": "9:00"}]],
    })
    assert await _events(model, "Chief") == [
        ToolCallRequested(id="chief-0-0", name="ask_bot", arguments={"bot": "Scout", "task": "hours"}),
        TurnDone("tool_use", SCRIPTED_USAGE),
    ]
    assert await _events(model, "scout") == [TextDelta("9:00"), TurnDone("end_turn", SCRIPTED_USAGE)]
    assert await _events(model, "Chief") == [TextDelta("done"), TurnDone("end_turn", SCRIPTED_USAGE)]


async def test_an_unscripted_or_finished_bot_echoes():
    model = ScriptedTeamModel.from_json({"Scout": [[{"text": "once"}]]})
    await _events(model, "Scout")
    assert await _events(model, "Scout", "again") == [TextDelta("I heard: again"), TurnDone("end_turn", SCRIPTED_USAGE)]
    assert await _events(model, "Wren", "hello") == [TextDelta("I heard: hello"), TurnDone("end_turn", SCRIPTED_USAGE)]


def test_a_malformed_script_is_rejected():
    with pytest.raises(ValidationError):
        ScriptedTeamModel.from_json({"Scout": [[{"say": "wrong key"}]]})


def test_from_file_reads_json(tmp_path):
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"Scout": [[{"text": "hi"}]]}), encoding="utf-8")
    assert isinstance(ScriptedTeamModel.from_file(path), ScriptedTeamModel)


def test_make_model_uses_the_script_file_in_scripted_mode(tmp_path):
    script = tmp_path / "script.json"
    script.write_text('{"Chief": [[{"text": "hi"}]]}', encoding="utf-8")
    env = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k"),
           "ROOST_MODEL": "scripted", "ROOST_MODEL_SCRIPT": str(script)}
    assert isinstance(make_model(load_config(env)), ScriptedTeamModel)


def test_a_missing_script_file_fails_at_startup(tmp_path):
    env = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k"),
           "ROOST_MODEL": "scripted", "ROOST_MODEL_SCRIPT": str(tmp_path / "missing.json")}
    with pytest.raises(FileNotFoundError):
        make_model(load_config(env))


async def test_a_wait_step_pauses_before_the_next_events(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("roost.llm.scripted_team.asyncio.sleep", fake_sleep)
    model = ScriptedTeamModel.from_json({"Slowpoke": [[{"wait": 1.5}, {"text": "late"}]]})
    assert await _events(model, "Slowpoke") == [TextDelta("late"), TurnDone("end_turn", SCRIPTED_USAGE)]
    assert slept == [1.5]


def test_a_wait_step_is_bounded():
    with pytest.raises(ValidationError):
        ScriptedTeamModel.from_json({"Slowpoke": [[{"wait": 600}]]})
