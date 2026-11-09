"""The install's one time zone (owner, 2026-11-09, docs/plans/2026-11-09-roost-time-zone.md).

Roost has one account per install, so the zone is install-wide: the account's own (``users.timezone``, set by the
web app's auto-detect through ``PUT /api/auth/timezone``), else the ``ROOST_TIMEZONE`` env var, else UTC. The
account's zone is held process-wide (loaded at startup, replaced by the PUT); every caller asks ``local_tz()`` at
use time, never at import, so a change applies at once. Stored moments stay UTC; only days and wall clocks follow."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from roost.config import RoostConfig
from roost.constants import TIMEZONE_ENV, TIMEZONE_FALLBACK, TIMEZONE_NAME_MAX
from roost.db.connection import db_session

__all__ = (
    "TIMEZONE_ENV", "is_zone_name", "load_local_tz", "local_tz", "local_tz_name", "read_account_timezone",
    "save_account_timezone", "set_local_tz", "zone_city",
)

logger = logging.getLogger(__name__)

_REFUSED = frozenset({"localtime"})

# The account's zone, or None for "not set": one immutable value swapped whole, never edited in place.
_account_zone: str | None = None


@lru_cache(maxsize=1)
def _known_zones() -> frozenset[str]:
    return frozenset(available_timezones()) - _REFUSED


def is_zone_name(name: object) -> bool:
    """An IANA zone name this machine knows (never ``localtime``), at most ``TIMEZONE_NAME_MAX`` characters."""
    return isinstance(name, str) and 0 < len(name) <= TIMEZONE_NAME_MAX and name in _known_zones()


def set_local_tz(name: str | None) -> None:
    """Hold ``name`` as the account's zone (``None`` clears it). Raises ``ValueError`` for an unknown name."""
    global _account_zone
    if name is not None and not is_zone_name(name):
        raise ValueError("That isn't a time zone Roost knows.")
    _account_zone = name


def _env_zone() -> str:
    name = os.environ.get(TIMEZONE_ENV, "").strip()
    if not name:
        return TIMEZONE_FALLBACK
    if not is_zone_name(name):
        logger.warning("%s is not a known time zone; using %s.", TIMEZONE_ENV, TIMEZONE_FALLBACK)
        return TIMEZONE_FALLBACK
    return name


def local_tz_name() -> str:
    """The effective zone's IANA name: the account's, else the env's, else UTC."""
    return _account_zone if _account_zone is not None else _env_zone()


def local_tz() -> ZoneInfo:
    """The effective zone (``ZoneInfo`` caches by name, so this is cheap)."""
    return ZoneInfo(local_tz_name())


def zone_city(name: str | None = None) -> str:
    """The zone's place for words such as "Madrid time" / "New York time": its last segment, ``_`` as a space."""
    return (name or local_tz_name()).rsplit("/", 1)[-1].replace("_", " ")


async def read_account_timezone(config: RoostConfig, user_id: str) -> str | None:
    """The account's stored zone, or ``None`` when it never set one (or it no longer reads)."""
    async with db_session(config) as db:
        row = await (await db.execute("SELECT timezone FROM users WHERE id = ?", (user_id,))).fetchone()
    value = row[0] if row else None
    return value if is_zone_name(value) else None


async def save_account_timezone(config: RoostConfig, user_id: str, name: str) -> None:
    """Store ``name`` for the account. Raises ``ValueError`` for an unknown name."""
    if not is_zone_name(name):
        raise ValueError("That isn't a time zone Roost knows.")
    async with db_session(config) as db:
        await db.execute("UPDATE users SET timezone = ? WHERE id = ?", (name, user_id))
        await db.commit()


async def load_local_tz(config: RoostConfig) -> str:
    """At startup: hold the account's zone (the first account with one), else clear it. Returns the effective name."""
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT timezone FROM users WHERE timezone IS NOT NULL ORDER BY created_at, rowid")).fetchall()
    stored = next((row[0] for row in rows if is_zone_name(row[0])), None)
    set_local_tz(stored)
    return local_tz_name()
