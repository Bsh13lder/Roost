"""The account's time zone (owner, 2026-11-09, docs/plans/2026-11-09-roost-time-zone.md).

- ``PUT /api/auth/timezone`` ``{"timezone": "<IANA>"}``: the zone the web app detected. It is stored on the
  account, becomes the install's zone at once (``roost.timezones``), and every enabled timed routine is planned
  again so 08:00 stays 08:00 on the new clock. Reminders and dues keep their stored moments.

The body is validated by hand, so a refusal (422) never echoes what was sent."""

from __future__ import annotations

import logging
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from roost.constants import TIMEZONE_NAME_MAX
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.timezones import is_zone_name, save_account_timezone, set_local_tz

logger = logging.getLogger(__name__)

timezone_router = APIRouter(prefix="/api/auth", tags=["auth"])

BAD_ZONE_TEXT: Final = "That isn't a time zone Roost knows. Send an IANA name such as Europe/Madrid."


class TimezoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    timezone: str = Field(min_length=1, max_length=TIMEZONE_NAME_MAX)

    @field_validator("timezone")
    @classmethod
    def _known(cls, value: str) -> str:
        if not is_zone_name(value):
            raise ValueError("unknown time zone")
        return value


class TimezoneOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str


async def _body(request: Request) -> TimezoneIn:
    """The body, or a 422 that never says what was sent."""
    try:
        return TimezoneIn.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail=[{"loc": ["body", "timezone"], "msg": BAD_ZONE_TEXT}]) from None


@timezone_router.put("/timezone", dependencies=[RequireOrigin])
async def put_timezone(request: Request, user: CurrentUser) -> TimezoneOut:
    body = await _body(request)
    await save_account_timezone(request.app.state.config, user.id, body.timezone)
    set_local_tz(body.timezone)
    replanned = await request.app.state.routine_store.replan_all(user.id)
    logger.info("Time zone set to %s; %d routine(s) planned again.", body.timezone, replanned)
    return TimezoneOut(timezone=body.timezone)
