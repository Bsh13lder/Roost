"""``run_helper``: the shared step loop with a silent sink.

A helper's text never reaches the chat: it is collected and handed back as a
``HelperResult``. The caller builds the ``ToolRunner`` (the gate, the read-only
allowlist, the parent's taint and link scope), so this module holds no policy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from roost.constants import HELPER_MAX_SECONDS, HELPER_MAX_STEPS, USAGE_KIND_HELPER
from roost.helpers.prompt import helper_instructions
from roost.llm.types import ChatTurn, Model, ModelRequest, ToolSpec
from roost.talk.steps import step_loop
from roost.talk.tool_runner import ToolRunner
from roost.usage.scope import kind_scope

HELPER_LIMIT_TEXT = "(The helper stopped at its step or time limit.)"
HELPER_SILENT_TEXT = "The helper finished without a report."


@dataclass(frozen=True)
class HelperResult:
    text: str
    tainted: bool
    link_scope: tuple[str, ...]
    sees_records: bool
    capped: bool = False   # it stopped at its step or time limit


def _helper_usage():
    """A helper's steps count as the parent bot's, kind ``helper``."""
    return kind_scope(USAGE_KIND_HELPER)


def _report(text: str, capped: bool) -> str:
    body = text.strip() or (HELPER_SILENT_TEXT if not capped else "")
    return f"{body} {HELPER_LIMIT_TEXT}".strip() if capped else body


async def run_helper(
    *, task: str, model: Model, model_id: str, tool_runner: ToolRunner, tools: tuple[ToolSpec, ...], agent: str,
    max_steps: int = HELPER_MAX_STEPS, deadline_s: float = HELPER_MAX_SECONDS, effort: str | None = None,
) -> HelperResult:
    """Run one helper to its report. ``agent`` is ``"<bot>/helper-<n>"``. A step or time limit ends it
    with whatever it had said so far, marked as cut short. Cancellation (Stop) propagates."""
    bot_name = agent.split("/", 1)[0]
    system = helper_instructions(bot_name)
    first = (ChatTurn("user", task),)
    chunks: list[str] = []

    async def collect(text: str) -> None:
        chunks.append(text)

    try:
        with _helper_usage():
            async with asyncio.timeout(deadline_s):
                text, capped = await step_loop(
                    model=model, tool_runner=tool_runner, max_steps=max_steps, deadline_s=deadline_s,
                    request_for=lambda added: ModelRequest(
                        system=system, turns=first + added, tools=tools, model=model_id, agent=agent,
                        effort=effort),
                    on_delta=collect,
                )
    except TimeoutError:
        text, capped = "".join(chunks), True
    snap = tool_runner.snapshot()
    return HelperResult(text=_report(text, capped), tainted=snap.tainted, link_scope=snap.link_scope.as_tuple(),
                        sees_records=snap.sees_records, capped=capped)
