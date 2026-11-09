"""C3 Task 9: the newest look's screenshot reaches the real model as one streamed user message.

``query`` is always faked; the real CLI never starts."""

from __future__ import annotations

import base64

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

import roost.llm.claude_sdk as sdk
from roost.llm.claude_sdk import ClaudeSdkModel
from roost.llm.registry import DEFAULT_BOT_MODEL
from roost.llm.scripted import ScriptedModel
from roost.llm.types import ChatTurn, ImagePart, ModelRequest, TextDelta, ToolSpec, TurnDone
from roost.llm.scripted import SCRIPTED_USAGE

_JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s1",
        stop_reason="end_turn",
    )


def _install(monkeypatch) -> dict:
    seen: dict = {}

    async def fake_query(*, prompt, options):
        seen["options"] = options
        if isinstance(prompt, str):
            seen["prompt"] = prompt
        else:
            seen["messages"] = [message async for message in prompt]
        yield AssistantMessage(content=[TextBlock("ok")], model=DEFAULT_BOT_MODEL)
        yield _result()

    monkeypatch.setattr(sdk, "query", fake_query)
    return seen


def _request(images=()) -> ModelRequest:
    return ModelRequest(
        "sys", (ChatTurn("user", "find the price"),), (ToolSpec("look", "Look", {"type": "object"}),),
        DEFAULT_BOT_MODEL, images=images,
    )


async def _drain(request: ModelRequest) -> list:
    return [event async for event in ClaudeSdkModel(DEFAULT_BOT_MODEL).stream(request)]


def _texts(message) -> list[str]:
    return [block.get("text", "<image>") for block in message["message"]["content"]]


async def test_every_step_goes_as_one_streamed_user_message_with_a_block_per_turn(monkeypatch):
    # Tokens (owner, 2026-11-07): the transcript went as ONE text block, so every step wrote the whole of it to the
    # prompt cache again. One block per turn keeps everything before the newest turns a cache read.
    seen = _install(monkeypatch)
    turns = (ChatTurn("user", "find the price"), ChatTurn("assistant", "On it"),
             ChatTurn("tool", "<untrusted_page>9 EUR</untrusted_page>", tool_call_id="t1", tool_name="read_text"))
    request = ModelRequest("sys", turns, (), DEFAULT_BOT_MODEL)
    events = await _drain(request)
    assert events == [TextDelta("ok"), TurnDone("end_turn")]
    assert "prompt" not in seen
    (message,) = seen["messages"]
    assert message["type"] == "user" and message["parent_tool_use_id"] is None
    assert _texts(message) == [
        '<turn role="user">find the price</turn>', '<turn role="assistant">On it</turn>',
        '<tool_result name="read_text" id="t1"><untrusted_page>9 EUR</untrusted_page></tool_result>']
    assert "\n".join(_texts(message)) == sdk._render_prompt(turns)


async def test_one_image_goes_as_a_single_streamed_user_message(monkeypatch):
    seen = _install(monkeypatch)
    events = await _drain(_request((ImagePart("image/jpeg", _JPEG),)))
    assert events == [TextDelta("ok"), TurnDone("end_turn")]
    assert "prompt" not in seen
    (message,) = seen["messages"]
    assert message["type"] == "user" and message["parent_tool_use_id"] is None
    assert message["message"]["role"] == "user"
    text_block, image_block = message["message"]["content"]
    assert text_block == {"type": "text", "text": sdk._render_prompt(_request().turns)}
    assert image_block == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(_JPEG).decode("ascii")},
    }


def test_an_image_sits_right_after_its_own_turn_so_later_steps_keep_the_same_prefix():
    turns = (ChatTurn("user", "a"), ChatTurn("tool", "look 1", tool_call_id="t1", tool_name="look"),
             ChatTurn("tool", "clicked", tool_call_id="t2", tool_name="click"))
    images = (ImagePart("image/jpeg", b"p", label="Picture 1:", after_turn=0),
              ImagePart("image/jpeg", b"s", after_turn=1))
    message = sdk._user_message(turns, images)
    assert _texts(message) == ['<turn role="user">a</turn>', "Picture 1:", "<image>",
                               '<tool_result name="look" id="t1">look 1</tool_result>', "<image>",
                               '<tool_result name="click" id="t2">clicked</tool_result>']


def test_an_image_without_a_place_goes_after_every_turn():
    message = sdk._user_message((ChatTurn("user", "hello"),),
                                (ImagePart("image/jpeg", b"a"), ImagePart("image/jpeg", b"b", after_turn=7)))
    kinds = [block["type"] for block in message["message"]["content"]]
    assert kinds == ["text", "image", "image"]


async def test_options_are_unchanged_with_images(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-the-sdk")
    seen = _install(monkeypatch)
    await _drain(_request((ImagePart("image/jpeg", _JPEG),)))
    options = seen["options"]
    assert options.tools == [] and options.max_turns == 1 and options.strict_mcp_config is True
    assert options.setting_sources == [] and options.can_use_tool is not None
    assert options.hooks and "PreToolUse" in options.hooks
    assert "ANTHROPIC_API_KEY" not in options.env
    assert options.extra_args == {"no-session-persistence": None}


async def test_scripted_model_ignores_images():
    model = ScriptedModel()
    events = [event async for event in model.stream(_request((ImagePart("image/jpeg", _JPEG),)))]
    assert events == [TextDelta("I heard: find the price"), TurnDone("end_turn", SCRIPTED_USAGE)]


def test_model_request_has_no_images_by_default():
    assert _request().images == ()
