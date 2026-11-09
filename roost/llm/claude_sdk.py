"""The real Claude Agent SDK provider — always-on, default-deny.

``build_options`` is the one place Night-1 configures the SDK: no built-in
tools, an in-process ``roost`` MCP server whose handlers are inert stubs
(they never run anything — the model layer never imports the talk or
desk packages, so it has no way to), a ``can_use_tool`` callback that
denies anything outside that server, a ``PreToolUse`` hook as a second,
independent layer, one turn per call, no on-disk session persistence, and
a copy of the process environment with ``ANTHROPIC_API_KEY`` stripped (a
subscription login breaks if that var is present).

Tool calls the model actually wants to run are never executed here —
they're collected from the response and handed back to the caller as
``ToolCallRequested`` events; the turn runner in a later task decides
what happens next via the refusal gate.
"""

from __future__ import annotations

import base64
import html
import os
from dataclasses import dataclass
from typing import Any, AsyncIterable, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

from roost.usage.counts import usage_from_sdk
from roost.llm.types import (
    ChatTurn,
    ImagePart,
    ModelEvent,
    ModelRequest,
    ModelUnreachable,
    TextDelta,
    ToolCallRequested,
    ToolSpec,
    TurnDone,
)

# The SDK prefixes every tool of an in-process ("sdk") MCP server named
# "roost" with this exact string when it hands tool names to the model
# and back. Stripped off again when turning a ToolUseBlock into a
# ToolCallRequested, so the rest of the codebase only ever sees plain
# names ("open_page", not "mcp__roost__open_page").
ROOST_TOOL_PREFIX = "mcp__roost__"
_ROOST_SERVER_NAME = "roost"

# No on-disk session persistence: the CLI should never write a resumable
# session file for a Roost turn.
# No SDK subagent of any kind: the tools are disallowed, the built-in agents
# are switched off and the spawn depth is capped.
_NO_SUBAGENT_TOOLS = ("Agent", "Task")
_NO_SUBAGENT_ENV = {
    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
    # No CLI telemetry or other non-essential traffic.
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}

_EXTRA_ARGS: dict[str, str | None] = {"no-session-persistence": None}


async def _stub_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    """Every roost tool's handler — inert. Runs nothing, touches nothing.

    The model layer collects the resulting ``ToolUseBlock`` as a
    ``ToolCallRequested`` event instead of ever letting the SDK itself
    execute a tool; this handler exists only so the SDK's MCP server has
    something to call while the turn is still in flight, and its result
    is discarded by ``ClaudeSdkModel.stream`` once the ``ToolCallRequested``
    has been collected.
    """
    return {"content": [{"type": "text", "text": "tool call recorded"}]}


def _build_roost_server(tools: tuple[ToolSpec, ...]):
    sdk_tools = [
        tool(spec.name, spec.description, spec.input_schema)(_stub_handler)
        for spec in tools
    ]
    return create_sdk_mcp_server(_ROOST_SERVER_NAME, tools=sdk_tools)


async def _deny_builtins_and_unknown_tools(
    tool_name: str, tool_input: dict[str, Any], context: Any
) -> PermissionResultAllow | PermissionResultDeny:
    """``can_use_tool``: allow only this turn's ``roost`` MCP tools.

    Every built-in tool (``Bash``, ``Read``, ``WebFetch``, ...) and any
    tool name this check doesn't recognize — including one a future SDK
    version introduces — is denied. This is the primary gate; the
    ``PreToolUse`` hook below is a second, independent layer.
    """
    if tool_name.startswith(ROOST_TOOL_PREFIX):
        return PermissionResultAllow()
    return PermissionResultDeny(
        message=f"Refused: {tool_name} is not an available tool."
    )


async def _deny_pre_tool_use_hook(
    input_data: Any, tool_use_id: str | None, context: Any
) -> dict[str, Any]:
    """``PreToolUse`` hook — defense in depth alongside ``can_use_tool``.

    The permission decision itself is made by ``can_use_tool``; this hook
    exists so a tool call is never one misconfigured callback away from
    running — a bug in one still leaves the other in place. It makes no
    independent decision (an empty result leaves ``can_use_tool``'s
    decision untouched).
    """
    return {}


def build_options(
    system: str, tools: tuple[ToolSpec, ...], model: str, effort: str | None = None
) -> ClaudeAgentOptions:
    """Build the one ``ClaudeAgentOptions`` Night-1 ever uses.

    No built-in tools (``tools=[]``), no settings files
    (``setting_sources=[]``), a strict MCP config (only the servers
    listed here, nothing from a user/project config), exactly one turn,
    and an environment with ``ANTHROPIC_API_KEY`` removed.
    """
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(_NO_SUBAGENT_ENV)

    return ClaudeAgentOptions(
        system_prompt=system,
        tools=[],
        disallowed_tools=list(_NO_SUBAGENT_TOOLS),
        agents=None,
        effort=effort,
        mcp_servers={_ROOST_SERVER_NAME: _build_roost_server(tools)},
        strict_mcp_config=True,
        permission_mode="default",
        setting_sources=[],
        max_turns=1,
        model=model,
        env=env,
        extra_args=dict(_EXTRA_ARGS),
        can_use_tool=_deny_builtins_and_unknown_tools,
        hooks={"PreToolUse": [HookMatcher(hooks=[_deny_pre_tool_use_hook])]},
    )


def _escape_tags(text: str) -> str:
    """Neutralize ``&``/``<``/``>``/quotes as HTML entities, ``&`` first
    (``html.escape``'s own order) — applied ONLY to a plain user/assistant
    turn's text (Fix round 1, finding 1/3, superseding the original
    Ruling 16 reading).

    A tool result's text is never re-escaped here any more: ``roost/
    talk/turn.py`` already built it, including the ONE real
    ``<untrusted_page url="…">…</untrusted_page>`` wrapper around any page
    content, with that content's own ``&``/``<``/``>`` already neutralized
    before wrapping. Re-escaping the whole tool turn on top of that (the
    original Ruling 16 reading) would convert turn.py's real wrapper tags
    into entity text indistinguishable from content — defeating the
    wrapper's entire purpose, since the model is told to distrust a
    literal ``<untrusted_page>`` tag, not an escaped one. See
    ``_render_prompt`` below.
    """
    return html.escape(text, quote=True)


def _render_turn(turn: ChatTurn) -> str:
    if turn.role == "tool":
        name = _escape_tags(turn.tool_name or "")
        call_id = _escape_tags(turn.tool_call_id or "")
        return f'<tool_result name="{name}" id="{call_id}">{turn.text}</tool_result>'
    if turn.role == "teammate":
        author = _escape_tags(turn.tool_name or "")
        return f'<bot_reply from="{author}">{_escape_tags(turn.text)}</bot_reply>'
    return f'<turn role="{turn.role}">{_escape_tags(turn.text)}</turn>'


def _render_prompt(turns: tuple[ChatTurn, ...]) -> str:
    """Render the transcript as tagged text — the SDK's ``prompt`` string.

    ``<turn role="user">…</turn>`` / ``<turn role="assistant">…</turn>``
    for ordinary turns, with their text escaped by ``_escape_tags``. A
    tool's result renders as ``<tool_result name="…" id="…">…</tool_result>``
    instead, so the model can tell a tool result apart from a turn someone
    actually said — but its TEXT is rendered as-is (not re-escaped: see
    ``_escape_tags``'s docstring), since ``roost/talk/turn.py`` already
    made it safe, real wrapper tags and all. Only the ``name``/``id``
    attributes, which come straight from the model's own preceding tool
    call, are escaped here. A teammate's room post renders as
    ``<bot_reply from="…">…</bot_reply>``, with both the author name and
    the text escaped HERE — unlike a tool result, nobody upstream built a
    wrapper into it, so this is the one place that makes the real
    ``<bot_reply>`` tag safe.
    """
    return "\n".join(_render_turn(turn) for turn in turns)


def _image_blocks(image: ImagePart) -> list[dict[str, Any]]:
    """An image as a base64 block, after its own label line when it has one (your attached pictures)."""
    block = {"type": "image", "source": {"type": "base64", "media_type": image.media_type,
                                         "data": base64.b64encode(image.data).decode("ascii")}}
    return [{"type": "text", "text": image.label}, block] if image.label else [block]


def _content(turns: tuple[ChatTurn, ...], images: tuple[ImagePart, ...]) -> list[dict[str, Any]]:
    """One text block per turn (owner, 2026-11-07, tokens): the prompt cache matches whole blocks, so a step that
    only adds turns reads everything before them instead of writing the whole transcript again. Each image rides
    right after its own turn (``after_turn``); one without a place in this transcript goes after every turn."""
    placed = {i: [img for img in images if img.after_turn == i] for i in range(len(turns))}
    loose = [img for img in images if img.after_turn is None or not 0 <= img.after_turn < len(turns)]
    blocks: list[dict[str, Any]] = []
    for i, turn in enumerate(turns):
        blocks.append({"type": "text", "text": _render_turn(turn)})
        blocks += [b for img in placed[i] for b in _image_blocks(img)]
    return blocks + [b for img in loose for b in _image_blocks(img)]


def _user_message(turns: tuple[ChatTurn, ...], images: tuple[ImagePart, ...]) -> dict[str, Any]:
    """One SDK streaming-input user message: a text block per turn with the images in place (C3, chat
    pictures). Same envelope the SDK itself writes for a string prompt."""
    return {
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": _content(turns, images)},
        "parent_tool_use_id": None,
    }


async def _one_message(turns: tuple[ChatTurn, ...], images: tuple[ImagePart, ...]) -> AsyncIterator[dict[str, Any]]:
    """Streaming input of exactly one user message: only streaming mode takes content blocks."""
    yield _user_message(turns, images)


def _prompt_for(request: ModelRequest) -> str | AsyncIterable[dict[str, Any]]:
    """Always the streamed message of blocks; a request with no turns at all keeps the empty string prompt."""
    if not request.turns:
        return _render_prompt(request.turns)
    return _one_message(request.turns, request.images)


# The CLI's own words when the API can't be reached (claude_agent_sdk 0.2.170, gateway log 2026-11-07/08).
_UNREACHABLE_MARKERS = ("ECONNRESET", "ENOTFOUND", "EAI_AGAIN", "ECONNREFUSED", "ETIMEDOUT", "Can't reach the API")


@dataclass(frozen=True)
class ClaudeSdkModel:
    """Drives one turn through the real Claude Agent SDK."""

    model_id: str

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        options = build_options(request.system, request.tools, request.model or self.model_id, request.effort)
        prompt = _prompt_for(request)

        saw_tool_use = False
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield TextDelta(block.text)
                        elif isinstance(block, ToolUseBlock):
                            name = block.name
                            if name.startswith(ROOST_TOOL_PREFIX):
                                name = name[len(ROOST_TOOL_PREFIX) :]
                            saw_tool_use = True
                            yield ToolCallRequested(
                                id=block.id, name=name, arguments=block.input
                            )
                elif isinstance(message, ResultMessage):
                    yield TurnDone(message.stop_reason or message.subtype, usage_from_sdk(message.usage))
        except ResultError as exc:
            # Final review, finding 1: `max_turns=1` (`build_options`
            # above) means a turn that calls a roost tool always ends
            # this way -- the CLI reports `error_max_turns` and exits
            # non-zero after already handing over the tool call. The
            # SDK yields that ToolUseBlock (-> our ToolCallRequested,
            # above) and the ResultMessage first, then raises THIS from
            # query()'s own __anext__ (claude_agent_sdk 0.2.170,
            # _internal/query.py:405-430). A tool call the model
            # actually made is real work the turn runner must still
            # see -- recover it instead of letting the exception abort
            # the turn before any of it reaches the caller. Anything
            # else (a genuine failure, or max_turns hit with no tool
            # call at all) is still a real error and propagates.
            if exc.subtype == "error_max_turns" and saw_tool_use:
                yield TurnDone("tool_use")
                return
            if any(marker in str(exc) for marker in _UNREACHABLE_MARKERS):
                raise ModelUnreachable(str(exc)) from exc
            raise
