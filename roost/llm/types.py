"""The model-agnostic LLM contract: requests in, events out.

Every provider (``ScriptedModel``, ``ClaudeSdkModel``) implements the same
``Model`` protocol, so ``roost/talk/runner.py`` (a later task) never has to
know which one it is driving. All data types are frozen — a provider
builds a new ``ModelRequest``/event per call rather than mutating one it
was handed, per the project's immutability rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol, Union

ChatRole = Literal["user", "assistant", "tool", "teammate"]

# C3 (computer use): a look's tool turn says its screenshot rides with this step; an older look's turn is
# rewritten in the request (never in storage) to say it is no longer shown. Only the newest look's image is sent.
SCREENSHOT_SHOWN = "[screenshot attached]"
SCREENSHOT_GONE = "[screenshot from an earlier look, not shown]"


class ModelUnreachable(RuntimeError):
    """The model's service could not be reached (no internet, DNS, a dropped connection): the run ends with a
    plain line saying so instead of the generic error."""


@dataclass(frozen=True)
class ToolSpec:
    """One tool the model may call this turn, in Claude tool-definition shape."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ChatTurn:
    """One entry in the rendered transcript.

    ``tool_call_id``/``tool_name`` are only set when ``role == "tool"`` —
    they identify which prior ``ToolCallRequested`` this turn's ``text``
    is the result of. ``role == "teammate"`` is another bot's room post —
    data, never the user's voice — and ``tool_name`` then carries the
    author's name.
    """

    role: ChatRole
    text: str
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class ImagePart:
    """One image the model sees with this step: a picture you attached (chat pictures, owner 2026-11-05, with its
    ``label`` line before it) or the newest look's masked JPEG (C3)."""

    media_type: Literal["image/jpeg"]
    data: bytes
    label: str = ""
    # The index of the turn it rides right after; None: after every turn. In place, the steps after it keep the
    # same prompt prefix, so the prompt cache reads it instead of writing it again (owner, 2026-11-07).
    after_turn: int | None = None


@dataclass(frozen=True)
class ModelRequest:
    """Everything a provider needs to run one turn."""

    system: str
    turns: tuple[ChatTurn, ...]
    tools: tuple[ToolSpec, ...]
    model: str
    agent: str = ""  # the bot's name — lets ScriptedTeamModel pick that bot's script
    effort: str | None = None
    images: tuple[ImagePart, ...] = ()  # your attached pictures, then at most the newest look's screenshot


@dataclass(frozen=True)
class TextDelta:
    """A chunk of assistant text."""

    text: str


@dataclass(frozen=True)
class ToolCallRequested:
    """The model wants to call a tool — the caller (``roost/talk``) decides
    whether to run it (``Gate.check``) and feeds the result back as the
    next ``ChatTurn`` with ``role="tool"``.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """What one model call cost in tokens, when the provider reports it (token usage,
    docs/plans/2026-11-04-roost-token-usage.md). ``cache_write`` is the provider's cache creation count."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass(frozen=True)
class TurnDone:
    """The model has finished producing output for this turn. ``usage`` is ``None`` when the provider said
    nothing about tokens; nothing downstream changes behaviour on it."""

    stop_reason: str
    usage: Usage | None = None


ModelEvent = Union[TextDelta, ToolCallRequested, TurnDone]


class Model(Protocol):
    """A provider that can stream a response to a ``ModelRequest``.

    Implementations are plain generator functions (``async def stream(self,
    request): yield ...``) — calling ``stream()`` returns the async
    iterator directly, with no ``await`` needed to get it, matching this
    signature exactly.
    """

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
