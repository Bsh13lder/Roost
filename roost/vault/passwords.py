"""``VaultPasswordStore``: Vault: passwords (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md V1,
V2, V4). The site, user name and password are ``enc:v2`` under ``vault_passwords:<column>``; ``host_key`` and
``username_key`` are keyed HMACs, so one row per site and user name and nothing sits in plaintext. A list never
holds a password: only ``secret`` does, and only the fill reads it. Every query names ``user_id``."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.vault.models import normalise_host

VAULT_PASSWORDS_MAX: Final = 200
_HOST_LABEL: Final = b"roost:vault-password-host:v1"
_USER_LABEL: Final = b"roost:vault-password-username:v1"
_SEALED: Final = ("host", "username", "password")
_LIST_COLUMNS: Final = "id, user_id, host, username, always, created_at, updated_at, last_used_at"


class PasswordNotFound(LookupError):
    """No such saved login for this user."""


class PasswordsFull(RuntimeError):
    """The user already keeps ``VAULT_PASSWORDS_MAX`` logins."""


@dataclass(frozen=True)
class NewLogin:
    host: str          # normalised (``normalise_host``)
    username: str      # may be empty: a site that asks for the password alone
    password: str = field(repr=False)


@dataclass(frozen=True)
class SavedLogin:
    """What a list shows: never the password."""

    id: str
    host: str
    username: str
    always: bool
    created_at: str
    updated_at: str
    last_used_at: str | None


@dataclass(frozen=True)
class LoginSecret:
    """Only for the fill; never returned by a route, never in a prompt."""

    id: str
    host: str
    username: str
    password: str = field(repr=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(dek: bytes, label: bytes, value: str) -> str:
    sub = hmac.new(dek, label, hashlib.sha256).digest()
    return hmac.new(sub, value.encode("utf-8"), hashlib.sha256).hexdigest()


def host_serves(saved: str, page: str) -> bool:
    """A login saved for ``upwork.com`` serves ``upwork.com`` and its sub-sites, never a parent or a look-alike."""
    saved, page = normalise_host(saved), normalise_host(page)
    return bool(saved) and (page == saved or page.endswith(f".{saved}"))


def _hosts_serving(page: str) -> tuple[str, ...]:
    """The saved sites that could serve ``page``: itself and each parent with at least two labels."""
    labels = normalise_host(page).split(".")
    return tuple(".".join(labels[i:]) for i in range(len(labels) - 1)) if len(labels) > 1 else ()


def _seal(dek: bytes, user_id: str, column: str, value: str) -> str:
    sealed = encrypt_field(value, dek, user_aad(user_id, f"vault_passwords:{column}"))
    if sealed is None:
        raise ValueError("a vault value did not seal")
    return sealed


def _open(dek: bytes, row: aiosqlite.Row, column: str) -> str:
    return decrypt_field(row[column], dek, user_aad(row["user_id"], f"vault_passwords:{column}")) or ""


def _saved(dek: bytes, row: aiosqlite.Row) -> SavedLogin:
    return SavedLogin(id=row["id"], host=_open(dek, row, "host"), username=_open(dek, row, "username"),
                      always=bool(row["always"]), created_at=row["created_at"], updated_at=row["updated_at"],
                      last_used_at=row["last_used_at"])


class VaultPasswordStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def save(self, user_id: str, login: NewLogin) -> SavedLogin:
        """Save a login, or replace the password of the same site and user name. ``PasswordsFull`` past the cap."""
        dek = await get_user_dek(self._config, user_id)
        values = {"host": login.host, "username": login.username, "password": login.password}
        sealed = {column: _seal(dek, user_id, column, values[column]) for column in _SEALED}
        keys = (_key(dek, _HOST_LABEL, login.host), _key(dek, _USER_LABEL, login.username))
        async with db_session(self._config) as db:
            await db.execute("BEGIN IMMEDIATE")          # the room check and the insert are one step
            try:
                login_id = await self._write(db, user_id, keys, sealed, _now_iso())
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
        return await self._one(user_id, login_id)

    async def _write(self, db: aiosqlite.Connection, user_id: str, keys: tuple[str, str],
                     sealed: dict[str, str], now: str) -> str:
        found = await (await db.execute(
            "SELECT id FROM vault_passwords WHERE user_id = ? AND host_key = ? AND username_key = ?",
            (user_id, *keys))).fetchone()
        if found is not None:
            await db.execute("UPDATE vault_passwords SET password = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                             (sealed["password"], now, found["id"], user_id))
            return str(found["id"])
        await self._require_room(db, user_id)
        login_id = str(uuid4())
        await db.execute(
            "INSERT INTO vault_passwords (id, user_id, host, host_key, username, username_key, password, always,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)",
            (login_id, user_id, sealed["host"], keys[0], sealed["username"], keys[1], sealed["password"], now, now))
        return login_id

    async def list(self, user_id: str) -> tuple[SavedLogin, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_LIST_COLUMNS} FROM vault_passwords WHERE user_id = ?"
                                           " ORDER BY created_at", (user_id,))).fetchall()
        return tuple(sorted((_saved(dek, row) for row in rows), key=lambda s: (s.host, s.username)))

    async def for_host(self, user_id: str, page_host: str) -> tuple[SavedLogin, ...]:
        """The user's logins that serve this page's site (``host_serves``)."""
        hosts = _hosts_serving(page_host)
        if not hosts:
            return ()
        dek = await get_user_dek(self._config, user_id)
        keys = tuple(_key(dek, _HOST_LABEL, host) for host in hosts)
        marks = ",".join("?" * len(keys))
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_LIST_COLUMNS} FROM vault_passwords WHERE user_id = ? AND host_key IN ({marks})"
                " ORDER BY created_at", (user_id, *keys))).fetchall()
        return tuple(login for login in (_saved(dek, row) for row in rows) if host_serves(login.host, page_host))

    async def secret(self, user_id: str, login_id: str) -> LoginSecret:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT * FROM vault_passwords WHERE id = ? AND user_id = ?",
                                          (login_id, user_id))).fetchone()
        if row is None:
            raise PasswordNotFound(login_id)
        return LoginSecret(id=row["id"], host=_open(dek, row, "host"), username=_open(dek, row, "username"),
                           password=_open(dek, row, "password"))

    async def patch(self, user_id: str, login_id: str, *, password: str | None, always: bool | None) -> SavedLogin:
        dek = await get_user_dek(self._config, user_id)
        changes: dict[str, object] = {"updated_at": _now_iso()}
        if password is not None:
            changes["password"] = _seal(dek, user_id, "password", password)
        if always is not None:
            changes["always"] = int(always)
        sets = ", ".join(f"{column} = ?" for column in changes)     # fixed column names, never caller text
        async with db_session(self._config) as db:
            done = await db.execute(f"UPDATE vault_passwords SET {sets} WHERE id = ? AND user_id = ?",
                                    (*changes.values(), login_id, user_id))
            await db.commit()
        if done.rowcount == 0:
            raise PasswordNotFound(login_id)
        return await self._one(user_id, login_id)

    async def delete(self, user_id: str, login_id: str) -> None:
        async with db_session(self._config) as db:
            gone = await db.execute("DELETE FROM vault_passwords WHERE id = ? AND user_id = ?", (login_id, user_id))
            await db.commit()
        if gone.rowcount == 0:
            raise PasswordNotFound(login_id)

    async def mark_used(self, user_id: str, login_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("UPDATE vault_passwords SET last_used_at = ? WHERE id = ? AND user_id = ?",
                             (_now_iso(), login_id, user_id))
            await db.commit()

    async def _one(self, user_id: str, login_id: str) -> SavedLogin:
        found = next((login for login in await self.list(user_id) if login.id == login_id), None)
        if found is None:
            raise PasswordNotFound(login_id)
        return found

    @staticmethod
    async def _require_room(db: aiosqlite.Connection, user_id: str) -> None:
        row = await (await db.execute("SELECT COUNT(*) FROM vault_passwords WHERE user_id = ?",
                                      (user_id,))).fetchone()
        if row is not None and int(row[0]) >= VAULT_PASSWORDS_MAX:
            raise PasswordsFull()
