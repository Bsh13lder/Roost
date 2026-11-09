"""One bounded worker-model call for memory work (capture, summaries)."""

from __future__ import annotations

import asyncio

from roost.constants import MEMORY_WORKER_TIMEOUT_S, USAGE_KIND_BACKGROUND
from roost.llm.registry import WORKER
from roost.llm.types import ChatTurn, ImagePart, Model, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.usage.scope import note_usage

CAPTURE_AGENT = "memory-capture"
SUMMARY_AGENT = "chat-summary"


class WorkerError(RuntimeError):
    """The worker did something a text-only call must not."""


async def ask_worker(model: Model, *, agent: str, system: str, text: str, model_id: str = WORKER,
                     timeout_s: float | None = None, images: tuple[ImagePart, ...] = ()) -> str:
    """Send ``text`` (and ``images``, data only) to the worker model (``model_id``, Haiku unless a caller names
    another registry id) with no tools and return its reply."""
    request = ModelRequest(system=system, turns=(ChatTurn("user", text),), tools=(), model=model_id, agent=agent,
                           images=images)
    parts: list[str] = []
    async with asyncio.timeout(MEMORY_WORKER_TIMEOUT_S if timeout_s is None else timeout_s):
        async for event in model.stream(request):
            if isinstance(event, ToolCallRequested):
                raise WorkerError("The worker asked for a tool.")
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, TurnDone):
                await note_usage(model_id, event.usage, kind=USAGE_KIND_BACKGROUND)
    return "".join(parts)
