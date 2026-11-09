"""``VaultStore``: site logins, sealed. ``host`` and ``label`` are ``enc:v2``; the unique key is an HMAC of the
normalised host, so one row per (bot, site) and the host never sits in plaintext. Every query names ``user_id``."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import SITE_LOGIN_LIST_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.vault.models import SiteLogin, VaultBotNotFound, clean_label, normalise_host

_KEY_LABEL = b"roost:site-login-host:v1"
_COLUMNS = "id, user_id, bot_id, host, label, created_at, updated_at, kept, clear_after_item_id"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_key(dek: bytes, host: str) -> str:
    sub = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(sub, host.encode("utf-8"), hashlib.sha256).hexdigest()


def _login(row: aiosqlite.Row, dek: bytes) -> SiteLogin:
    user_id = row["user_id"]
    return SiteLogin(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"],
        host=decrypt_field(row["host"], dek, user_aad(user_id, "site_logins:host")) or "",
        label=decrypt_field(row["label"], dek, user_aad(user_id, "site_logins:label")) or "",
        created_at=row["created_at"], updated_at=row["updated_at"],
        kept=bool(row["kept"]), clear_after_item_id=row["clear_after_item_id"],
    )


class VaultStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def remember(self, user_id: str, bot_id: str, host: str, label: str | None, *, kept: bool = True,
                       clear_after_item_id: str | None = None) -> SiteLogin:
        """Save, or replace the account label for this bot on this site, with whether it is kept on the
        computer (``label=None`` keeps a saved label). A kept login has no pending clear. ``VaultBotNotFound``:
        not your bot."""
        site, text = normalise_host(host), clean_label(label or "")
        dek = await get_user_dek(self._config, user_id)
        sealed_label = encrypt_field(text, dek, user_aad(user_id, "site_logins:label"))
        relabel = "label = ?, " if label is not None else ""
        pending = None if kept else clear_after_item_id
        now = _now_iso()
        async with db_session(self._config) as db:
            await self._require_bot(db, user_id, bot_id)
            key = host_key(dek, site)
            await db.execute(
                "INSERT INTO site_logins (id, user_id, bot_id, host, host_key, label, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (str(uuid4()), user_id, bot_id, encrypt_field(site, dek, user_aad(user_id, "site_logins:host")), key,
                 sealed_label, now, now),
            )
            await db.execute(
                f"UPDATE site_logins SET {relabel}updated_at = ?, kept = ?, clear_after_item_id = ?"
                " WHERE user_id = ? AND bot_id = ? AND host_key = ?",
                ((sealed_label,) if relabel else ()) + (now, int(kept), pending, user_id, bot_id, key),
            )
            await db.commit()
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM site_logins WHERE user_id = ? AND bot_id = ? AND host_key = ?",
                (user_id, bot_id, key))).fetchone()
        return _login(row, dek)

    @staticmethod
    async def _require_bot(db: aiosqlite.Connection, user_id: str, bot_id: str) -> None:
        owned = await (await db.execute("SELECT 1 FROM bots WHERE id = ? AND user_id = ?",
                                        (bot_id, user_id))).fetchone()
        if owned is None:
            raise VaultBotNotFound(bot_id)

    async def get(self, user_id: str, login_id: str, bot_id: str) -> SiteLogin | None:
        """That bot's login, or None when it is not this user's (or not that bot's)."""
        found = await self._select(user_id, "AND id = ? AND bot_id = ?", (login_id, bot_id), 1)
        return found[0] if found else None

    async def pending_clears(self, user_id: str, bot_id: str) -> tuple[SiteLogin, ...]:
        """The bot's "No, this time" logins: each waits for its continue item, then its site is cleared."""
        return await self._select(user_id, "AND bot_id = ? AND kept = 0", (bot_id,), SITE_LOGIN_LIST_LIMIT)

    async def pending_bots(self) -> tuple[tuple[str, str], ...]:
        """Boot only, across users: every (user_id, bot_id) with a pending clear. Ids only, nothing sealed."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT DISTINCT user_id, bot_id FROM site_logins WHERE kept = 0 ORDER BY user_id, bot_id",
            )).fetchall()
        return tuple((row["user_id"], row["bot_id"]) for row in rows)

    async def list_for_bot(self, user_id: str, bot_id: str, limit: int = SITE_LOGIN_LIST_LIMIT) -> tuple[SiteLogin, ...]:
        return await self._select(user_id, "AND bot_id = ?", (bot_id,), limit)

    async def list_all(self, user_id: str, limit: int = SITE_LOGIN_LIST_LIMIT) -> tuple[SiteLogin, ...]:
        return await self._select(user_id, "", (), limit)

    async def forget(self, user_id: str, login_id: str, bot_id: str | None = None) -> bool:
        """Remove that one bot-and-site label (only if it is that bot's when ``bot_id`` is given). False: no
        such login for this user."""
        scope, extra = ("", ()) if bot_id is None else (" AND bot_id = ?", (bot_id,))
        async with db_session(self._config) as db:
            cursor = await db.execute(f"DELETE FROM site_logins WHERE id = ? AND user_id = ?{scope}",
                                      (login_id, user_id, *extra))
            await db.commit()
        return cursor.rowcount > 0

    async def _select(self, user_id: str, extra: str, params: tuple, limit: int) -> tuple[SiteLogin, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM site_logins WHERE user_id = ? {extra} ORDER BY updated_at DESC LIMIT ?",
                (user_id, *params, limit))).fetchall()
        return tuple(_login(row, dek) for row in rows)
