"""Vault: site logins models. A login is a (bot, site) pair with the account label you typed."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from roost.constants import SITE_LOGIN_LABEL_MAX_CHARS


NO_SITE_TEXT = ("I couldn't tell which site you signed in on, so I didn't save the account. "
                "Give it back without one.")
AccountLabel = Annotated[str, StringConstraints(max_length=SITE_LOGIN_LABEL_MAX_CHARS)]


class GiveBackIn(BaseModel):
    """``DELETE /control`` and ``/stuck/{id}/clear`` may say which account you used. Blank means none."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account: AccountLabel | None = None


def signed_in_line(host: str, label: str) -> str:
    return f"I signed in on {host} as {label}."


class NoSite(ValueError):
    """There is no web address to attach the account to."""


class VaultBotNotFound(LookupError):
    """The bot is not this user's."""


@dataclass(frozen=True)
class SiteLogin:
    id: str
    user_id: str
    bot_id: str
    host: str
    label: str
    created_at: str
    updated_at: str
    kept: bool = True                       # Sign-in card: stays signed in on the bot's computer
    clear_after_item_id: str | None = None  # "No, this time": the site is cleared once this item is finished


class SiteLoginOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    bot_id: str
    host: str
    label: str
    updated_at: str
    kept: bool = True


def site_login_out(login: SiteLogin) -> SiteLoginOut:
    return SiteLoginOut(id=login.id, bot_id=login.bot_id, host=login.host, label=login.label,
                        updated_at=login.updated_at, kept=login.kept)


def normalise_host(text: str) -> str:
    """The site of an address or a bare host: lower case, no scheme, port, path or leading ``www.``.
    An empty string when there is none."""
    raw = (text or "").strip().lower()
    if not raw:
        return ""
    parts = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parts.hostname or "").rstrip(".")
    host = host.removeprefix("www.")
    return host if "." in host or host == "localhost" else ""


def clean_label(text: str) -> str:
    return " ".join((text or "").split())[:SITE_LOGIN_LABEL_MAX_CHARS]
