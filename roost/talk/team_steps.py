"""``TeamSteps``: ``create_bot`` and ``set_bot_model`` as card steps (topic ``team``).

In Ask every time (and in a Proposal) these two calls wait for the user's OK like any other change. ``prepare``
validates the call and names it in plain words; ``execute`` runs the STORED call through the same checks the
live tools use (the main bot only, a clean run, a real teammate and an allowed model) once the user says Yes.
Nothing here reads the model's later words."""

from __future__ import annotations

import html
from typing import Any

from pydantic import ValidationError

from roost.approvals.models import PendingCall
from roost.bots.store import BotStore
from roost.events.hub import EventHub
from roost.models_check.store import SeenModelStore
from roost.talk.domain_tools import RecordContext
from roost.talk.model_tools import BAD_SET_MODEL, SetBotModelArgs
from roost.talk.outcome import ToolOutcome
from roost.talk.store import TalkStore
from roost.talk.team_tools import BAD_CREATE, CreateBotArgs, RunScope, TeamTools

NAMES = frozenset({"create_bot", "set_bot_model"})
_NOT_MAIN = "Refused: only the main bot does this."
_NO_CHAT = "Refused: this needs the user's own chat with you."
_ACTIVITY = {"create_bot": "creating a bot", "set_bot_model": "switching a model"}


class TeamSteps:
    names: frozenset[str] = NAMES

    def __init__(self, bots: BotStore, talk: TalkStore, events: EventHub, seen: SeenModelStore | None = None) -> None:
        self._bots, self._talk, self._events, self._seen = bots, talk, events, seen

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        pending = await self.prepare(name, arguments, ctx)
        if isinstance(pending, str):
            return ToolOutcome(pending, failed=True)
        return await self.execute(name, dict(pending.arguments), ctx, approved=False)

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        bot = await self._bots.get(ctx.user_id, ctx.bot_id)
        if bot is None or not bot.is_primary:
            return _NOT_MAIN
        try:
            if name == "create_bot":
                args = CreateBotArgs.model_validate(arguments)
                title = f"Create the bot {html.escape(args.name, quote=True)}"
            else:
                args = SetBotModelArgs.model_validate(arguments)
                effort = f" at {args.effort} effort" if args.effort else ""
                title = f"Switch {html.escape(args.bot, quote=True)} to {html.escape(args.model, quote=True)}{effort}"
        except ValidationError:
            return BAD_CREATE if name == "create_bot" else BAD_SET_MODEL
        stored = args.model_dump(mode="json", exclude_none=True)
        return PendingCall(tool=name, arguments=stored, topic="team", title=title,
                           detail=stored.get("job", ""))

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext, *,
                      approved: bool = True) -> ToolOutcome:
        """``approved``: your Yes on its card or Accept on a Proposal, which is the create check for a tainted run."""
        bot = await self._bots.get(ctx.user_id, ctx.bot_id)
        if bot is None or ctx.thread_id is None:
            return ToolOutcome(_NOT_MAIN if bot is None else _NO_CHAT, failed=True)
        scope = RunScope(user_id=ctx.user_id, bot=bot, thread_id=ctx.thread_id, in_room=False, user_started=True)
        team = TeamTools(scope, bots=self._bots, talk=self._talk, events=self._events, port=None,  # type: ignore[arg-type]
                         seen_models=self._seen)
        if name == "create_bot":
            outcome = await team.create_bot(resolved, tainted=ctx.tainted, checked=approved)
        else:
            outcome = await team.models.set_bot_model(resolved, tainted=ctx.tainted)
        return ToolOutcome(outcome.text, failed=outcome.text.startswith("Refused") or outcome.text == "That model isn't available.")
