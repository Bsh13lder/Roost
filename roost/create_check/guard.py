"""``CreateCheckGuard``: what the gate does with a ``checked_create`` verdict before the bot is created.

The pure judge only saw a tainted ``create_bot`` in your own chat; the guard reads your newest own messages (through
the runner's ``OwnerSource``) and asks the main bot's own model. Any "no", no words of yours or an error is the old refusal, which
points the main bot to ``suggest_bot``, so the check can only ever skip that one tap, never widen what a bot may do."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

from roost.create_check.check import CreateFacts, create_fits
from roost.llm.registry import check_model
from roost.llm.types import Model
from roost.talk.tool_catalog import TAINTED_CREATE_BOT_TEXT
from roost.talk.verdict import Verdict

OwnerSource = Callable[[], Awaitable[tuple[str, ...]]]
REFUSED = Verdict("never", "tainted_change", TAINTED_CREATE_BOT_TEXT)


def _text(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    return value if isinstance(value, str) else ""


def create_facts(arguments: Mapping[str, Any], words: tuple[str, ...]) -> CreateFacts:
    return CreateFacts(words=words, name=_text(arguments, "name"), job=_text(arguments, "job"),
                       instructions=_text(arguments, "instructions"), role=_text(arguments, "role"))


class CreateCheckGuard:
    def __init__(self, worker: Model) -> None:
        self._worker = worker

    async def confirm(self, verdict: Verdict, arguments: Mapping[str, Any], source: OwnerSource | None,
                      *, model_id: str | None = None) -> Verdict:
        """``verdict`` when the main bot's own model (``model_id``) says the bot fits your words, else the refusal
        that points to ``suggest_bot``."""
        if source is None:
            return REFUSED
        facts = create_facts(arguments, await source())
        if not await create_fits(self._worker, facts, model_id=check_model(model_id)):
            return REFUSED
        return verdict
