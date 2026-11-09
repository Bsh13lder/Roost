"""``AppStore``: the packages the owner said Yes to (schema v32 ``bot_apps``).

``package`` is ``enc:v2`` under ``bot_apps:package``; the unique key is a keyed HMAC of the name, so one row per
(bot, package) and the name never sits in plaintext. Every query names ``user_id``, so another user's bot or app
reads as none; ``owner_of`` alone reads by bot id, for the reinstall at a fresh start (ids only, nothing sealed)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.apps.constants import APPS_PER_BOT_MAX
from roost.apps.models import BotApp
from roost.apps.names import package_key
from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

_COLUMNS = "id, user_id, bot_id, package, tainted, installed_at"
_AAD = "bot_apps:package"


class AppBotNotFound(LookupError):
    """Not this user's bot."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _app(row: aiosqlite.Row, dek: bytes) -> BotApp:
    user_id = row["user_id"]
    return BotApp(id=row["id"], user_id=user_id, bot_id=row["bot_id"],
                  package=decrypt_field(row["package"], dek, user_aad(user_id, _AAD)) or "",
                  tainted=bool(row["tainted"]), installed_at=row["installed_at"])


class AppStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def add(self, user_id: str, bot_id: str, package: str, *, tainted: bool) -> BotApp:
        """Record the package for this bot (the existing row when it is there). ``AppBotNotFound``: not your bot."""
        dek = await get_user_dek(self._config, user_id)
        key = package_key(dek, package)
        async with db_session(self._config) as db:
            owned = await (await db.execute("SELECT 1 FROM bots WHERE id = ? AND user_id = ?",
                                            (bot_id, user_id))).fetchone()
            if owned is None:
                raise AppBotNotFound(bot_id)
            await db.execute(
                "INSERT INTO bot_apps (id, user_id, bot_id, package, package_key, tainted, installed_at)"
                " VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (str(uuid4()), user_id, bot_id, encrypt_field(package, dek, user_aad(user_id, _AAD)), key,
                 int(tainted), _now_iso()),
            )
            await db.commit()
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM bot_apps WHERE user_id = ? AND bot_id = ? AND package_key = ?",
                (user_id, bot_id, key))).fetchone()
        return _app(row, dek)

    async def find(self, user_id: str, bot_id: str, package: str) -> BotApp | None:
        dek = await get_user_dek(self._config, user_id)
        found = await self._select(user_id, "AND bot_id = ? AND package_key = ?",
                                   (bot_id, package_key(dek, package)), dek)
        return found[0] if found else None

    async def get(self, user_id: str, bot_id: str, app_id: str) -> BotApp | None:
        found = await self._select(user_id, "AND bot_id = ? AND id = ?", (bot_id, app_id))
        return found[0] if found else None

    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[BotApp, ...]:
        return await self._select(user_id, "AND bot_id = ?", (bot_id,))

    async def packages(self, user_id: str, bot_id: str) -> tuple[str, ...]:
        return tuple(app.package for app in await self.list_for_bot(user_id, bot_id))

    async def delete(self, user_id: str, bot_id: str, app_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM bot_apps WHERE id = ? AND user_id = ? AND bot_id = ?",
                                      (app_id, user_id, bot_id))
            await db.commit()
        return cursor.rowcount > 0

    async def owner_of(self, bot_id: str) -> str | None:
        """A fresh start only: the user whose approved apps this bot has, if any. Ids only, nothing sealed."""
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT DISTINCT user_id FROM bot_apps WHERE bot_id = ? LIMIT 1",
                                          (bot_id,))).fetchone()
        return None if row is None else row["user_id"]

    async def _select(self, user_id: str, extra: str, params: tuple, dek: bytes | None = None) -> tuple[BotApp, ...]:
        dek = dek if dek is not None else await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM bot_apps WHERE user_id = ? {extra} ORDER BY installed_at, id LIMIT ?",
                (user_id, *params, APPS_PER_BOT_MAX))).fetchall()
        return tuple(_app(row, dek) for row in rows)
