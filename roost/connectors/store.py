"""``ConnectorStore``: the user's connectors (schema v31 ``connectors``).

Every text column is ``enc:v2`` under ``connectors:<column>``; ``bot_ids`` is a plaintext list of ids. Every
statement names ``user_id``, so another user's connector reads as none. The key is read only by ``secret_of``;
``Connector`` never carries it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.connectors.address import check_base_url
from roost.connectors.models import Connector
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

_SEALED = ("name", "purpose", "base_url", "auth_name", "secret", "secret_hint", "allowed_prefixes")
_SHOWN = ("id", "user_id", "name", "purpose", "base_url", "auth_style", "auth_name", "secret_hint",
          "allowed_prefixes", "bot_ids", "created_at", "updated_at")
_COLUMNS = ", ".join(_SHOWN)
_WRITABLE = frozenset((*_SEALED, "auth_style", "bot_ids"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"connectors:{column}")


def _seal(value: str, dek: bytes, user_id: str, column: str) -> str:
    return encrypt_field(value, dek, _aad(user_id, column))


def _open(row: aiosqlite.Row, dek: bytes, column: str) -> str:
    return decrypt_field(row[column], dek, _aad(row["user_id"], column)) or ""


def _to_connector(row: aiosqlite.Row, dek: bytes) -> Connector:
    base_url = _open(row, dek, "base_url")
    bot_ids = row["bot_ids"]
    return Connector(
        id=row["id"], user_id=row["user_id"], name=_open(row, dek, "name"), purpose=_open(row, dek, "purpose"),
        base_url=base_url, host=check_base_url(base_url).host, auth_style=row["auth_style"],
        auth_name=_open(row, dek, "auth_name"), key_hint=_open(row, dek, "secret_hint"),
        allowed_prefixes=tuple(json.loads(_open(row, dek, "allowed_prefixes") or "[]")),
        bot_ids=None if bot_ids is None else tuple(json.loads(bot_ids)),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _plain(column: str, value: Any) -> Any:
    """A column's stored form before sealing (lists as JSON)."""
    if column == "allowed_prefixes":
        return json.dumps(list(value))
    if column == "bot_ids":
        return None if value is None else json.dumps(list(value))
    return value


class ConnectorStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def _dek(self, user_id: str) -> bytes:
        return await get_user_dek(self._config, user_id)

    def _row_values(self, user_id: str, fields: Mapping[str, Any], dek: bytes) -> dict[str, Any]:
        unknown = set(fields) - _WRITABLE
        if unknown:
            raise ValueError("Unknown connector columns.")
        out: dict[str, Any] = {}
        for column, value in fields.items():
            plain = _plain(column, value)
            out[column] = _seal(plain, dek, user_id, column) if column in _SEALED else plain
        return out

    async def create(self, user_id: str, fields: Mapping[str, Any]) -> Connector:
        """Insert one connector; ``fields`` holds every column but the ids and times."""
        dek = await self._dek(user_id)
        connector_id, now = str(uuid4()), _now()
        values = {"id": connector_id, "user_id": user_id, **self._row_values(user_id, fields, dek),
                  "created_at": now, "updated_at": now}
        names = ", ".join(values)
        async with db_session(self._config) as db:
            await db.execute(f"INSERT INTO connectors ({names}) VALUES ({', '.join('?' * len(values))})",
                             tuple(values.values()))
            await db.commit()
        made = await self.get(user_id, connector_id)
        if made is None:
            raise RuntimeError("The connector could not be read back.")
        return made

    async def count(self, user_id: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT count(*) FROM connectors WHERE user_id = ?", (user_id,))).fetchone()
        return int(row[0])

    async def get(self, user_id: str, connector_id: str) -> Connector | None:
        rows = await self._select(user_id, "AND id = ?", (connector_id,))
        return rows[0] if rows else None

    async def list(self, user_id: str) -> tuple[Connector, ...]:
        rows = await self._select(user_id, "", ())
        return tuple(sorted(rows, key=lambda c: (c.name.casefold(), c.id)))

    async def update(self, user_id: str, connector_id: str, fields: Mapping[str, Any]) -> Connector | None:
        if fields:
            dek = await self._dek(user_id)
            values = self._row_values(user_id, fields, dek)
            sets = ", ".join(f"{column} = ?" for column in values)
            async with db_session(self._config) as db:
                await db.execute(f"UPDATE connectors SET {sets}, updated_at = ? WHERE id = ? AND user_id = ?",
                                 (*values.values(), _now(), connector_id, user_id))
                await db.commit()
        return await self.get(user_id, connector_id)

    async def delete(self, user_id: str, connector_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM connectors WHERE id = ? AND user_id = ?", (connector_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def secret_of(self, user_id: str, connector_id: str) -> str | None:
        """The key, for the one request that sends it. Never stored on a ``Connector``."""
        async with db_session(self._config) as db:
            row = await (await db.execute("SELECT user_id, secret FROM connectors WHERE id = ? AND user_id = ?",
                                          (connector_id, user_id))).fetchone()
        return None if row is None else _open(row, await self._dek(user_id), "secret")

    async def _select(self, user_id: str, extra: str, params: tuple) -> list[Connector]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM connectors WHERE user_id = ? {extra}",
                                           (user_id, *params))).fetchall()
        if not rows:
            return []
        dek = await self._dek(user_id)
        return [_to_connector(row, dek) for row in rows]
