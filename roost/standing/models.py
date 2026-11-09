"""Standing permission values: the pydantic input every boundary validates, and the frozen rows and run state.

A permission is fixed data (D3): a site, one action of ``post``/``send``/``submit``, a count per local day and a
last local day. ``StandingState`` is what one routine run's gate reads (precomputed, so the judge stays pure);
``StandingMatch`` is what the judge found, which the gate re-checks live and hands to the model check."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.computer_use.fence import normalise_host
from roost.standing.constants import STANDING_HOST_MAX, STANDING_MAX_PER_DAY_MAX

StandingAction = Literal["post", "send", "submit"]

BAD_HOST_TEXT = "Name the site as a plain address, such as x.com."
_WWW = "www."


def permission_site(host: str) -> str:
    """The site a host stands for: lower-case IDNA, ``www.`` dropped; "" when it isn't a usable domain."""
    found = normalise_host(host)
    if found.startswith(_WWW) and found.count(".") > 1:
        found = found[len(_WWW):]
    return found if "." in found else ""


class PermissionIn(BaseModel):
    """What the owner (or a bot's proposal) asks for: "Let it <action> on <host> up to <n> a day until <date>"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(min_length=1, max_length=STANDING_HOST_MAX)
    action: StandingAction
    max_per_day: int = Field(ge=1, le=STANDING_MAX_PER_DAY_MAX)
    until: date

    @field_validator("host")
    @classmethod
    def _a_site(cls, value: str) -> str:
        site = permission_site(value)
        if not site:
            raise ValueError(BAD_HOST_TEXT)
        return site


@dataclass(frozen=True)
class Permission:
    id: str
    user_id: str
    bot_id: str
    routine_id: str
    host: str
    action: StandingAction
    max_per_day: int
    until: str                 # YYYY-MM-DD, a local day
    used_day: str | None
    used_count: int
    created_at: str
    revoked_at: str | None

    def used_on(self, today: str) -> int:
        return self.used_count if self.used_day == today else 0


@dataclass(frozen=True)
class LivePermission:
    """A permission that holds today, with what is left of today's count."""
    id: str
    host: str
    action: StandingAction
    remaining: int


@dataclass(frozen=True)
class StandingState:
    """One routine run's standing permissions, read when the run starts."""
    routine_id: str
    instructions: str
    permissions: tuple[LivePermission, ...]
    today: str


@dataclass(frozen=True)
class StandingMatch:
    """A hard-floor act a permission covers. ``consume``: the act commits (a click or Enter) and uses one of the
    day's count; typing into a box on the site does not."""
    permission_id: str
    host: str
    action: StandingAction
    consume: bool
