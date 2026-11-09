"""``suggest_model`` and ``set_bot_model``: the main bot proposes a model with an Ask card, or switches one
when the user asked in their own chat. Haiku is for background jobs, so neither tool ever picks it.

Every string built here from model text is escaped here, by its producer (see ``team_tools``)."""

from __future__ import annotations

import html
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.bots.models import Bot
from roost.bots.service import bot_out
from roost.bots.store import BotStore
from roost.constants import MAX_SUGGESTIONS_PER_RUN, MODEL_REASON_MAX_CHARS
from roost.events.hub import EventHub
from roost.llm.registry import (
    BOT_MODELS, EFFORTS, model_label, pickable_model_ids, resolve_bot_model,
)
from roost.models_check.store import SeenModelStore
from roost.talk.outcome import ToolOutcome
from roost.talk.store import TalkStore, message_out

Announce = Callable[[str], Awaitable[None]]
Effort = Literal[*EFFORTS]

MODEL_UNAVAILABLE_TEXT = "That model isn't available."
MODEL_SWITCHED_TEXT = "Switched {bot} to {label}"
BAD_SUGGEST_MODEL = (
    "Refused: suggest_model needs a teammate's name as bot, a model, optionally an effort "
    f"({', '.join(EFFORTS)}), and a reason of up to {MODEL_REASON_MAX_CHARS} characters."
)
BAD_SET_MODEL = (
    "Refused: set_bot_model needs a teammate's name as bot, a model, and optionally an effort "
    f"({', '.join(EFFORTS)})."
)
_NOT_MAIN = "Refused: only the main bot changes models."
_NOT_ON_REQUEST = ("Refused: models are changed only when the user asks you in their own chat with you. "
                   "Show a card with suggest_model instead.")
_ROOM = "Refused: model cards are shown only in your 1:1 chat."


async def _quiet(activity: str) -> None:
    """The default: no activity line."""


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bot: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=100)
    effort: Effort | None = None


class SuggestModelArgs(_Choice):
    reason: str = Field(min_length=1, max_length=MODEL_REASON_MAX_CHARS)


class SetBotModelArgs(_Choice):
    pass


def _matches(wanted: str, model_id: str, label: str, key: str | None) -> bool:
    folded = wanted.strip().casefold()
    return folded in {model_id.casefold(), label.casefold(), (key or "").casefold()} - {""}


class ModelTools:
    def __init__(self, scope: Any, *, bots: BotStore, talk: TalkStore, events: EventHub,
                 seen: SeenModelStore | None = None) -> None:
        self._scope = scope
        self._bots = bots
        self._talk = talk
        self._events = events
        self._seen = seen
        self._suggestions = 0

    async def suggest_model(self, arguments: dict[str, Any], *, tainted: bool) -> ToolOutcome:
        """Post an Ask card. Nothing changes until the user clicks its button."""
        refusal = self._suggest_refusal()
        if refusal is not None:
            return ToolOutcome(refusal)
        try:
            args = SuggestModelArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_SUGGEST_MODEL)
        picked = await self._pick(args)
        if isinstance(picked, str):
            return ToolOutcome(picked)
        bot, model_id, labels = picked
        label = model_label(model_id, labels)
        if resolve_bot_model(bot.model_override, frozenset(labels)) == model_id and args.effort in (None, bot.effort):
            return ToolOutcome(f"Refused: {html.escape(bot.name, quote=True)} already runs on {label}.")
        self._suggestions += 1
        card = {"bot_id": bot.id, "bot": bot.name, "model": model_id, "label": label,
                "effort": args.effort, "reason": args.reason.strip()}
        message = await self._talk.add_message(
            self._scope.user_id, self._scope.thread_id, role="bot", body=json.dumps(card), tainted=tainted,
            kind="model_suggestion", author_bot_id=self._scope.bot.id,
        )
        await self._events.publish(self._scope.user_id, {
            "type": "message", "thread_id": self._scope.thread_id, "message": message_out(message),
        })
        return ToolOutcome(f"Shown a card suggesting {html.escape(bot.name, quote=True)} switch to {label}. "
                           "Nothing changes until the user clicks it.")

    async def set_bot_model(self, arguments: dict[str, Any], *, tainted: bool, announce: Announce = _quiet) -> ToolOutcome:
        """The gate already refused a tainted run (write_change); the scope checks here are the second fence."""
        refusal = self._set_refusal(tainted)
        if refusal is not None:
            return ToolOutcome(refusal)
        try:
            args = SetBotModelArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(BAD_SET_MODEL)
        picked = await self._pick(args)
        if isinstance(picked, str):
            return ToolOutcome(picked)
        bot, model_id, labels = picked
        label = model_label(model_id, labels)
        await announce(f"switching {bot.name} to {label}")
        updated = await self._bots.set_model(self._scope.user_id, bot.id, model_id, args.effort)
        if updated is None:
            return ToolOutcome(f"Refused: there is no teammate named {html.escape(args.bot, quote=True)}.")
        line = MODEL_SWITCHED_TEXT.format(bot=bot.name, label=label) + (f" at {args.effort} effort" if args.effort else "")
        await self._announce_switch(updated, line, labels)
        return ToolOutcome(html.escape(line, quote=True) + ".")

    def _suggest_refusal(self) -> str | None:
        if not self._scope.bot.is_primary:
            return _NOT_MAIN
        if self._scope.in_room:
            return _ROOM
        if self._suggestions >= MAX_SUGGESTIONS_PER_RUN:
            return f"Refused: at most {MAX_SUGGESTIONS_PER_RUN} model cards per run."
        return None

    def _set_refusal(self, tainted: bool) -> str | None:
        if not self._scope.bot.is_primary:
            return _NOT_MAIN
        if self._scope.in_room or not self._scope.user_started:
            return _NOT_ON_REQUEST
        return None

    async def _pick(self, args: _Choice) -> tuple[Bot, str, Mapping[str, str]] | str:
        """The teammate and the pickable model the arguments name, or a plain refusal."""
        team = await self._bots.list(self._scope.user_id)
        key = args.bot.strip().lstrip("@").casefold()
        bot = next((b for b in team if b.id == args.bot or b.name.casefold() == key), None)
        if bot is None:
            return f"Refused: there is no teammate named {html.escape(args.bot, quote=True)}."
        labels = await self._seen.labels() if self._seen is not None else {}
        model_id = self._model_id(args.model, labels)
        return MODEL_UNAVAILABLE_TEXT if model_id is None else (bot, model_id, labels)

    @staticmethod
    def _model_id(wanted: str, labels: Mapping[str, str]) -> str | None:
        keys = {choice.id: choice.key for choice in BOT_MODELS}
        for model_id in sorted(pickable_model_ids(frozenset(labels))):
            if _matches(wanted, model_id, model_label(model_id, labels), keys.get(model_id)):
                return model_id
        return None

    async def _announce_switch(self, bot: Bot, line: str, labels: Mapping[str, str]) -> None:
        note = await self._talk.add_message(
            self._scope.user_id, self._scope.thread_id, role="activity", body=line, tainted=False,
            kind="model_switched", author_bot_id=self._scope.bot.id,
        )
        await self._events.publish(self._scope.user_id, {"type": "bot_updated", "bot": bot_out(bot, None, labels)})
        await self._events.publish(self._scope.user_id, {
            "type": "message", "thread_id": self._scope.thread_id, "message": message_out(note),
        })
