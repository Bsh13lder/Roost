"""Unit tests for ``roost.llm.scripted.ScriptedModel`` and the
``roost.llm.registry.make_model`` factory that picks it (or the real
Claude SDK provider) by ``RoostConfig.model_mode``.

Every test here runs under ``tests/conftest.py``'s session-wide
``ROOST_MODEL=scripted`` override — this file is the proof that override
actually produces a model that never calls out.
"""

from __future__ import annotations

from roost.config import load_config
from roost.llm.registry import DEFAULT_BOT_MODEL, WORKER, make_model
from roost.llm.scripted import ScriptedModel
from roost.llm.types import ChatTurn, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.llm.scripted import SCRIPTED_USAGE

_REQUEST = ModelRequest("sys", (ChatTurn("user", "ping"),), (), "claude-sonnet-5")


async def test_echo_with_no_script_uses_last_user_text():
    model = ScriptedModel()
    events = [event async for event in model.stream(_REQUEST)]
    assert events == [TextDelta("I heard: ping"), TurnDone("end_turn", SCRIPTED_USAGE)]


async def test_echo_uses_the_most_recent_user_turn():
    request = ModelRequest(
        "sys",
        (
            ChatTurn("user", "first"),
            ChatTurn("assistant", "reply"),
            ChatTurn("user", "second"),
        ),
        (),
        "claude-sonnet-5",
    )
    events = [event async for event in ScriptedModel().stream(request)]
    assert events == [TextDelta("I heard: second"), TurnDone("end_turn", SCRIPTED_USAGE)]


async def test_echo_false_with_no_script_yields_nothing():
    model = ScriptedModel(echo=False)
    events = [event async for event in model.stream(_REQUEST)]
    assert events == []


async def test_scripted_turns_are_popped_in_order():
    script = [
        [TextDelta("first turn"), TurnDone("end_turn")],
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "x"}), TurnDone("tool_use")],
    ]
    model = ScriptedModel(script=script)

    first = [event async for event in model.stream(_REQUEST)]
    second = [event async for event in model.stream(_REQUEST)]

    assert first == [TextDelta("first turn"), TurnDone("end_turn")]
    assert second == [
        ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "x"}),
        TurnDone("tool_use"),
    ]


async def test_falls_back_to_echo_once_the_script_is_exhausted():
    model = ScriptedModel(script=[[TextDelta("scripted"), TurnDone("end_turn")]])
    await _drain(model)  # consumes the one scripted turn

    events = [event async for event in model.stream(_REQUEST)]
    assert events == [TextDelta("I heard: ping"), TurnDone("end_turn", SCRIPTED_USAGE)]


async def _drain(model: ScriptedModel) -> None:
    async for _ in model.stream(_REQUEST):
        pass


def test_registry_model_ids_match_the_contract():
    assert DEFAULT_BOT_MODEL == "claude-sonnet-5-5"
    assert WORKER == "claude-haiku-5-5"


def test_make_model_returns_scripted_model_in_scripted_mode(monkeypatch):
    monkeypatch.setenv("ROOST_MODEL", "scripted")
    assert isinstance(make_model(load_config()), ScriptedModel)


def test_make_model_returns_claude_sdk_model_in_claude_mode(monkeypatch):
    # Only constructs the provider — never calls .stream(), so this never
    # starts the real claude CLI.
    from roost.llm.claude_sdk import ClaudeSdkModel

    monkeypatch.setenv("ROOST_MODEL", "claude")
    model = make_model(load_config())
    assert isinstance(model, ClaudeSdkModel)
    assert model.model_id == DEFAULT_BOT_MODEL
