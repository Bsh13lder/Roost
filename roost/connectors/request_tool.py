"""``request_connector``: a bot asks the user for a key it doesn't have, on an Add a key card.

The base URL passes the same address rules as the user's own form before any card shows; a refusal is the plain
sentence and no card. It works only in a run with a chat, at most ``CONNECTOR_REQUESTS_OPEN_PER_BOT_MAX`` open per
bot, and never for a name the user already has. The bot never sees a key: it hears back the user's answer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.bots.limits import fits_on_one_line
from roost.connectors import texts
from roost.connectors.address import AddressRefused, check_base_url
from roost.connectors.models import check_name, check_auth_name
from roost.connectors.requests import ConnectorRequestService, NewRequest
from roost.connectors.service import ConnectorService
from roost.constants import CONNECTOR_REQUESTS_OPEN_PER_BOT_MAX, CONNECTOR_WHY_MAX
from roost.mac.wrap import clean_name
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome


class RequestArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    service: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=1000)
    why: str = Field(min_length=1, max_length=2000)
    auth_style: str = "bearer"
    auth_name: str | None = Field(default=None, max_length=200)


def _checked(args: RequestArgs) -> tuple[str, str, str, str, str] | str:
    """(service, base_url, why, style, auth name), or the refusal sentence."""
    try:
        service = check_name(args.service)
    except ValueError as exc:
        return str(exc)
    why = args.why.strip()
    if len(why) > CONNECTOR_WHY_MAX or not fits_on_one_line(why):
        return texts.BAD_WHY
    try:
        base = check_base_url(args.base_url)
    except AddressRefused as exc:
        return exc.text
    if args.auth_style not in ("bearer", "header", "query"):
        return texts.BAD_STYLE
    try:
        name = check_auth_name(args.auth_style, args.auth_name)
    except ValueError as exc:
        return str(exc)
    return service, base.url, why, args.auth_style, name


class RequestTools:
    names: frozenset[str] = frozenset({"request_connector"})

    def __init__(self, connectors: ConnectorService, requests: ConnectorRequestService) -> None:
        self._connectors, self._requests = connectors, requests

    def activity(self, name: str) -> str:
        return "asking you for a key"

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        if ctx.thread_id is None:
            return ToolOutcome(texts.REQUEST_NEEDS_CHAT)
        try:
            args = RequestArgs.model_validate(arguments)
        except ValidationError:
            return ToolOutcome(texts.BAD_REQUEST)
        checked = _checked(args)
        if isinstance(checked, str):
            return ToolOutcome(checked)
        service, base_url, why, style, auth_name = checked
        refused = await self._refusal(ctx, service)
        if refused is not None:
            return ToolOutcome(refused)
        made = await self._requests.open_request(NewRequest(
            user_id=ctx.user_id, bot_id=ctx.bot_id, thread_id=ctx.thread_id, service=service, base_url=base_url,
            why=why, auth_style=style, auth_name=auth_name, tainted=ctx.tainted))
        return ToolOutcome(texts.REQUESTED.format(service=clean_name(made.service), host=made.host))

    async def _refusal(self, ctx: RecordContext, service: str) -> str | None:
        wanted = service.casefold()
        have = next((c for c in await self._connectors.list(ctx.user_id) if c.name.casefold() == wanted), None)
        if have is not None:
            return texts.ALREADY_HAVE.format(name=clean_name(have.name))
        open_ones = await self._requests.store.list_open(ctx.user_id, ctx.bot_id)
        if any(r.service.casefold() == wanted for r in open_ones):
            return texts.ALREADY_ASKED.format(service=clean_name(service))
        if len(open_ones) >= CONNECTOR_REQUESTS_OPEN_PER_BOT_MAX:
            return texts.TOO_MANY_REQUESTS
        return None
