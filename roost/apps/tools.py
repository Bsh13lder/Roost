"""``AppTools``: install_app, remove_app and list_apps (docs/plans/2026-10-22-roost-install-app.md §1).

install_app and remove_app never run from ``run``: the gate always asks, ``prepare`` builds the card (the bot's
name, the package, the reason, Debian's one-line description), and only ``execute``, after the owner's Yes on
exactly that stored call, reaches the computer. ``list_apps`` reads the approved list."""

from __future__ import annotations

import html
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from roost.apps import texts
from roost.apps.constants import APP_WHY_MAX_CHARS
from roost.apps.service import AppService
from roost.approvals.models import PendingCall
from roost.constants import APPROVAL_TITLE_MAX_CHARS
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

NAMES = frozenset({"install_app", "remove_app", "list_apps"})
_ACTIVITY = {"install_app": "installing an app", "remove_app": "removing an app", "list_apps": "looking at apps"}
_FLOOR = "install_app"
_TOPIC = "programs"


class _Install(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    package: StrictStr = Field(max_length=200)
    why: StrictStr = Field(min_length=1, max_length=APP_WHY_MAX_CHARS)


class _Remove(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    package: StrictStr = Field(max_length=200)


def _parsed(name: str, arguments: dict[str, Any]) -> _Install | _Remove | str:
    try:
        return (_Install if name == "install_app" else _Remove).model_validate(arguments)
    except ValidationError:
        return texts.BAD_WHY.format(limit=APP_WHY_MAX_CHARS) if name == "install_app" else texts.BAD_NAME


class AppTools:
    names: frozenset[str] = NAMES

    def __init__(self, service: AppService) -> None:
        self._service = service

    def activity(self, name: str) -> str:
        return _ACTIVITY.get(name, "looking at apps")

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        if name != "list_apps":
            return ToolOutcome(texts.ASK_ONLY)
        apps = await self._service.store.list_for_bot(ctx.user_id, ctx.bot_id)
        if not apps:
            return ToolOutcome(texts.NO_APPS)
        lines = "\n".join(f"- {html.escape(app.package)}" for app in apps)
        return ToolOutcome(f"{texts.APPS_HEADER}\n{lines}")

    async def prepare(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> PendingCall | str:
        args = _parsed(name, arguments)
        if isinstance(args, str):
            return args
        bot = await self._service.linux_bot(ctx.user_id, ctx.bot_id)
        if isinstance(bot, str):
            return bot
        if isinstance(args, _Install):
            return await self._install_card(args, bot.name, ctx)
        if await self._service.store.find(ctx.user_id, ctx.bot_id, args.package) is None:
            return texts.NOT_MINE.format(package=args.package)
        title = texts.REMOVE_TITLE.format(bot=bot.name, package=args.package)
        return PendingCall(tool=name, arguments={"package": args.package}, topic=_TOPIC,
                           title=title[:APPROVAL_TITLE_MAX_CHARS], floor=_FLOOR, tainted_basis=ctx.tainted)

    async def _install_card(self, args: _Install, bot_name: str, ctx: RecordContext) -> PendingCall | str:
        info = await self._service.describe(ctx.user_id, ctx.bot_id, args.package)
        if isinstance(info, str):
            return info
        title = texts.INSTALL_TITLE.format(bot=bot_name, package=args.package)
        return PendingCall(tool="install_app", arguments={"package": args.package, "why": args.why}, topic=_TOPIC,
                           title=title[:APPROVAL_TITLE_MAX_CHARS], detail=info.description, floor=_FLOOR,
                           tainted_basis=ctx.tainted)

    async def execute(self, name: str, resolved: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        """The card's stored call, after the owner's Yes. The service checks the name and the bot again."""
        args = _parsed(name, resolved)
        if isinstance(args, str):
            return ToolOutcome(args, failed=True)
        if name == "install_app":
            result = await self._service.install(ctx.user_id, ctx.bot_id, args.package, tainted=ctx.tainted)
        else:
            result = await self._service.remove(ctx.user_id, ctx.bot_id, args.package, tainted=ctx.tainted)
        return ToolOutcome(result.text, failed=not result.ok)
