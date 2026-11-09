"""``ask_secret_field(kind, site, why)``: the bot asks you to type a password or code into the box on its own
computer (B3, owner decision 2026-10-23; ``docs/plans/2026-10-23-roost-tabs-signin-flow.md``).

It types nothing and reads no value. It returns the ``Block`` the run stops on (a Sign-in card with a masked
field), or the refusal the bot reads. Your own chat only; a Linux computer only; the page in front must be on
``site`` and show a password or code box (``PageTarget.secret_field``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import SIGN_IN_WHY_MAX_CHARS, STUCK_REASON_MAX_CHARS
from roost.desk.stuck import Block, host_of_url
from roost.desk.url_policy import UrlBlocked, check_url
from roost.llm.types import ToolSpec
from roost.records.tool_text import ToolText
from roost.talk.instructions import ASK_ONLY_IN_CHAT_TEXT

ASKED_TEXT = ("Asked: the user will type their {kind} into the box on {host} themselves; you never see it. Stop "
              "here. When they have, look and click the button that sends it (Next or Sign in).")

def _sign_in_secret(target: Any) -> bool:
    """A password or code box; never a card box (those only the Pay card fills)."""
    return bool(target.secret_field) and not target.card_field

BAD_ARGS_TEXT = ("Refused: ask_secret_field needs kind (password or code), the site, and a short why. For a "
                 "passkey, a security key or a QR code, use request_sign_in instead.")
LINUX_ONLY_TEXT = "Refused: ask_secret_field works only on your own Linux computer. Use request_sign_in."
OTHER_SITE_TEXT = "Refused: the page in front is on {host}, not that site. Look, then ask for the site you are on."
NO_BOX_TEXT = "Refused: there's no password or code box on the page in front. Look again first."

ASK_SECRET_FIELD_SPEC = ToolSpec(
    name="ask_secret_field",
    description=(
        "When the page in front shows a password, one-time-code or verification-code box, ask the user to type it "
        "into that box on your computer, then stop. It goes straight into the box: you never see it or type it. "
        "Afterwards look and click Next or Sign in yourself. For a passkey, a security key or a QR code, use "
        "request_sign_in. Works only in your own chat with the user."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["password", "code"]},
            "site": {"type": "string", "description": "The site you are signing in on: its host or address."},
            "why": {"type": "string", "description": f"Why you need it, in plain words (up to "
                                                     f"{SIGN_IN_WHY_MAX_CHARS} characters)."},
        },
        "required": ["kind", "site", "why"],
    },
)


class AskSecretFieldArgs(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    kind: Literal["password", "code"]
    site: str = Field(min_length=1, max_length=STUCK_REASON_MAX_CHARS)
    why: ToolText = Field(min_length=1, max_length=SIGN_IN_WHY_MAX_CHARS)


def _site_host(site: str) -> str:
    return host_of_url(site if "://" in site else f"https://{site}/").lower()


async def _page_refusal(page: Any, site_host: str) -> tuple[str, str]:
    """``(address, "")`` when the page in front is on the site and shows a secret box; else ``("", why not)``."""
    await page.geometry()                                  # the bot's tab in front: that is the page you will see
    url = await page.url()
    host = host_of_url(url).lower()
    if not host or host != site_host:
        return "", OTHER_SITE_TEXT.format(host=host or "no site")
    focused = await page.focused()
    if not (focused is not None and _sign_in_secret(focused)) and not any(_sign_in_secret(t) for t in await page.targets()):
        return "", NO_BOX_TEXT
    try:
        return check_url(url), ""
    except UrlBlocked:
        return "", OTHER_SITE_TEXT.format(host=host)


async def secret_field_block(arguments: dict[str, Any], *, cards: bool, page: Any) -> Block | str:
    """The block to stop on, or the refusal text."""
    if not cards:
        return ASK_ONLY_IN_CHAT_TEXT
    try:
        args = AskSecretFieldArgs.model_validate(arguments)
    except ValidationError:
        return BAD_ARGS_TEXT
    if page is None:
        return LINUX_ONLY_TEXT
    url, refusal = await _page_refusal(page, _site_host(args.site))
    if refusal:
        return refusal
    return Block(reason="login", url=url, host=host_of_url(url), note=args.why, sign_in=True, field=args.kind)
