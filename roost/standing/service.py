"""``PermissionService``: the owner adds, lists and revokes a routine's standing permissions.

Raw input from a route or a bot's proposal goes through ``parse_permission``, which answers every mistake with one
plain sentence (``PermissionRefused``), and ``check_window``, which keeps the end date between today and
``STANDING_UNTIL_MAX_DAYS`` local days ahead. A routine holds at most ``STANDING_PER_ROUTINE_MAX`` live ones; a new
one for the same site and action replaces the old. Another user's routine is ``NoSuchRoutine`` (404)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from roost.standing.constants import (
    STANDING_ACTIONS,
    STANDING_MAX_PER_DAY_MAX,
    STANDING_PER_ROUTINE_MAX,
    STANDING_UNTIL_MAX_DAYS,
)
from roost.standing.models import BAD_HOST_TEXT, Permission, PermissionIn
from roost.standing.store import PermissionRoutineNotFound, PermissionStore
from roost.work.runs import madrid_today

ACTION_TEXT = "Pick " + ", ".join(STANDING_ACTIONS[:-1]) + f" or {STANDING_ACTIONS[-1]}."
COUNT_TEXT = f"Pick 1 to {STANDING_MAX_PER_DAY_MAX} a day."
DATE_TEXT = "Pick an end date."
PAST_TEXT = "Pick an end date from today on."
FAR_TEXT = f"Pick an end date at most {STANDING_UNTIL_MAX_DAYS} days ahead."
FULL_TEXT = f"This routine already has {STANDING_PER_ROUTINE_MAX} standing permissions. Revoke one first."
_FIELD_TEXT = {"host": BAD_HOST_TEXT, "action": ACTION_TEXT, "max_per_day": COUNT_TEXT, "until": DATE_TEXT}


class PermissionRefused(ValueError):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class NoSuchPermission(LookupError):
    """Not there, already revoked, or not the user's."""


def parse_permission(data: Mapping[str, Any]) -> PermissionIn:
    """``PermissionIn`` from raw fields, or ``PermissionRefused`` naming the first field that is wrong."""
    try:
        return PermissionIn.model_validate(dict(data))
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0]) if error["loc"] else ""
            if field in _FIELD_TEXT:
                raise PermissionRefused(_FIELD_TEXT[field]) from None
        raise PermissionRefused(f"A standing permission needs {', '.join(_FIELD_TEXT)}.") from None


def check_window(draft: PermissionIn, today: date) -> None:
    if draft.until < today:
        raise PermissionRefused(PAST_TEXT)
    if draft.until > today + timedelta(days=STANDING_UNTIL_MAX_DAYS):
        raise PermissionRefused(FAR_TEXT)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PermissionService:
    def __init__(self, store: PermissionStore, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._store = store
        self._clock = clock

    def today(self) -> str:
        return madrid_today(self._clock())

    async def list(self, user_id: str, routine_id: str) -> tuple[Permission, ...]:
        """The routine's live permissions (another user's routine lists none)."""
        return await self._store.list_for_routine(user_id, routine_id, self.today())

    async def add(self, user_id: str, routine_id: str, data: Mapping[str, Any] | PermissionIn) -> Permission:
        """Validate and store. ``PermissionRefused`` (422 text); ``PermissionRoutineNotFound`` (404)."""
        draft = data if isinstance(data, PermissionIn) else parse_permission(data)
        today = self.today()
        check_window(draft, date.fromisoformat(today))
        live = await self._store.list_for_routine(user_id, routine_id, today)
        replaces = any(p.host == draft.host and p.action == draft.action for p in live)
        if len(live) >= STANDING_PER_ROUTINE_MAX and not replaces:
            raise PermissionRefused(FULL_TEXT)
        return await self._store.create(user_id, routine_id, draft)

    async def revoke(self, user_id: str, routine_id: str, permission_id: str) -> None:
        if not await self._store.revoke(user_id, routine_id, permission_id):
            raise NoSuchPermission(permission_id)


__all__ = ["NoSuchPermission", "PermissionRefused", "PermissionRoutineNotFound", "PermissionService",
           "check_window", "parse_permission"]
