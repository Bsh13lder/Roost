"""``request_sign_in(site, why)``: the bot asks you to sign in on a site, on its own computer (your own chat only).

It opens nothing and types nothing. It returns the ``Block`` the run stops on (a Sign-in card on a Linux
computer, today's Stuck card on Mac Brave), or the refusal the bot reads. The site is checked like any address
the bot opens (``check_url``): a local or private address is refused."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import SIGN_IN_WHY_MAX_CHARS, STUCK_REASON_MAX_CHARS
from roost.desk.stuck import Block, host_of_url
from roost.desk.url_policy import UrlBlocked, check_url
from roost.records.tool_text import ToolText
from roost.signin.texts import BAD_SIGN_IN_ARGS_TEXT, SITE_REFUSED_TEXT
from roost.talk.instructions import ASK_ONLY_IN_CHAT_TEXT


class RequestSignInArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    site: str = Field(min_length=1, max_length=STUCK_REASON_MAX_CHARS)
    why: ToolText = Field(min_length=1, max_length=SIGN_IN_WHY_MAX_CHARS)


def _site_url(site: str) -> str:
    """A bare host becomes its https front page; an address is kept as it is."""
    return site if "://" in site else f"https://{site}/"


def sign_in_block(arguments: dict[str, Any], *, cards: bool) -> Block | str:
    """The block to stop on, or the refusal text. Only a run in your own chat may ask (``cards``)."""
    if not cards:
        return ASK_ONLY_IN_CHAT_TEXT
    try:
        args = RequestSignInArgs.model_validate(arguments)
    except ValidationError:
        return BAD_SIGN_IN_ARGS_TEXT
    try:
        url = check_url(_site_url(args.site))
    except UrlBlocked:
        return SITE_REFUSED_TEXT
    host = host_of_url(url)
    if not host:
        return SITE_REFUSED_TEXT
    return Block(reason="login", url=url, host=host, note=args.why, sign_in=True)
