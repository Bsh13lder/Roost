"""The apps' records and wire shapes (frozen)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class BotApp:
    """One package the owner said Yes to on one bot's computer."""
    id: str
    user_id: str
    bot_id: str
    package: str
    tainted: bool
    installed_at: str


@dataclass(frozen=True)
class AppInfo:
    """Debian's own words for a package, read on the bot's computer (``roost-apt describe``)."""
    package: str
    version: str
    description: str


class BotAppOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    package: str
    installed_at: str


def bot_app_out(app: BotApp) -> BotAppOut:
    return BotAppOut(id=app.id, package=app.package, installed_at=app.installed_at)
