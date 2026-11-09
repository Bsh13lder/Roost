"""``SkillStore``: the user's skills (schema v26 ``skills``) and the per-bot off switch (``bot_skill_off``).

``name``, ``use_when`` and ``body`` are ``enc:v2`` under ``skills:<column>``; ``name_key`` is a keyed HMAC of the
folded name, so names are unique per user and found by name without plaintext. Every statement names ``user_id``,
so another user's skill reads as "no such skill". ``update`` is a compare-and-swap on ``revision``."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import SKILLS_PER_USER_MAX
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.records.revision import RevisionConflict
from roost.skills.models import Skill, SkillDraft, SkillOrigin, SkillPatch
from roost.skills.names import fold_name, name_key

_COLUMNS = "id, user_id, name, use_when, body, origin, tainted, created_by_bot, revision, created_at, updated_at"
_TEXT_FIELDS = ("name", "use_when", "body")


class SkillNameTaken(Exception):
    """Another skill of this user already has that (folded) name."""

    def __init__(self, existing: Skill) -> None:
        super().__init__("A skill with that name exists.")
        self.existing = existing


class SkillsFull(Exception):
    """The user already has ``SKILLS_PER_USER_MAX`` skills."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"skills:{column}")


def _seal(value: str, dek: bytes, user_id: str, column: str) -> str:
    return encrypt_field(value, dek, _aad(user_id, column))


def _to_skill(row: aiosqlite.Row, dek: bytes) -> Skill:
    uid = row["user_id"]
    texts = {field: decrypt_field(row[field], dek, _aad(uid, field)) or "" for field in _TEXT_FIELDS}
    return Skill(id=row["id"], user_id=uid, **texts, origin=row["origin"], tainted=bool(row["tainted"]),
                 created_by_bot=row["created_by_bot"], revision=row["revision"], created_at=row["created_at"],
                 updated_at=row["updated_at"])


class SkillStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: SkillDraft, *, origin: SkillOrigin, tainted: bool,
                     created_by_bot: str | None) -> Skill:
        """Add a skill. ``SkillNameTaken(existing)`` or ``SkillsFull`` when it cannot be added."""
        dek = await get_user_dek(self._config, user_id)
        key = name_key(dek, draft.name)
        existing = await self._by_key(user_id, key, dek)
        if existing is not None:
            raise SkillNameTaken(existing)
        skill_id, now = str(uuid4()), _now()
        values = (skill_id, user_id, *(_seal(getattr(draft, f), dek, user_id, f) for f in _TEXT_FIELDS), key,
                  origin, int(tainted), created_by_bot, now, now)
        await self._insert(user_id, values)
        made = await self.get(user_id, skill_id)
        if made is None:
            raise RuntimeError("The skill could not be read back.")
        return made

    async def _insert(self, user_id: str, values: tuple) -> None:
        async with db_session(self._config) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                count = await (await db.execute("SELECT count(*) FROM skills WHERE user_id = ?",
                                                (user_id,))).fetchone()
                if count[0] >= SKILLS_PER_USER_MAX:
                    raise SkillsFull()
                await db.execute(
                    "INSERT INTO skills (id, user_id, name, use_when, body, name_key, origin, tainted, created_by_bot,"
                    " revision, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?)", values)
                await db.commit()
            except aiosqlite.IntegrityError:
                await db.rollback()
                raise SkillNameTaken(await self._existing_after_race(user_id, values)) from None
            except BaseException:
                await db.rollback()
                raise

    async def _existing_after_race(self, user_id: str, values: tuple) -> Skill:
        dek = await get_user_dek(self._config, user_id)
        found = await self._by_key(user_id, values[5], dek)
        if found is None:
            raise RuntimeError("The skill could not be added.")
        return found

    async def get(self, user_id: str, skill_id: str) -> Skill | None:
        rows = await self._select(user_id, "AND id = ?", (skill_id,))
        return rows[0] if rows else None

    async def get_by_name(self, user_id: str, name: str) -> Skill | None:
        dek = await get_user_dek(self._config, user_id)
        return await self._by_key(user_id, name_key(dek, name), dek)

    async def list(self, user_id: str) -> tuple[Skill, ...]:
        """Every skill of this user, in folded-name order."""
        skills = await self._select(user_id, "", ())
        return tuple(sorted(skills, key=lambda s: (fold_name(s.name), s.id)))

    async def update(self, user_id: str, skill_id: str, patch: SkillPatch, *, base_revision: int,
                     tainted: bool) -> Skill | None:
        """Write the patch only at ``base_revision``. ``None``: no such skill; ``RevisionConflict(current)``: it
        changed; ``SkillNameTaken``: another skill has the new name."""
        dek = await get_user_dek(self._config, user_id)
        sets, params = self._patch_sets(user_id, patch, dek)
        if patch.name is not None:
            other = await self._by_key(user_id, name_key(dek, patch.name), dek)
            if other is not None and other.id != skill_id:
                raise SkillNameTaken(other)
        try:
            async with db_session(self._config) as db:
                cursor = await db.execute(
                    f"UPDATE skills SET {sets}tainted = ?, revision = revision + 1, updated_at = ? "
                    "WHERE id = ? AND user_id = ? AND revision = ?",
                    (*params, int(tainted), _now(), skill_id, user_id, base_revision))
                await db.commit()
        except aiosqlite.IntegrityError:
            raise SkillNameTaken(await self.get_by_name(user_id, patch.name or "")) from None
        current = await self.get(user_id, skill_id)
        if current is None:
            return None
        if cursor.rowcount == 0:
            raise RevisionConflict(current)
        return current

    @staticmethod
    def _patch_sets(user_id: str, patch: SkillPatch, dek: bytes) -> tuple[str, tuple]:
        sets: list[str] = []
        params: list[str] = []
        for field in _TEXT_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                sets.append(f"{field} = ?, ")
                params.append(_seal(value, dek, user_id, field))
        if patch.name is not None:
            sets.append("name_key = ?, ")
            params.append(name_key(dek, patch.name))
        return "".join(sets), tuple(params)

    async def delete(self, user_id: str, skill_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute("DELETE FROM skills WHERE id = ? AND user_id = ?", (skill_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def off_ids(self, user_id: str, bot_id: str) -> frozenset[str]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT skill_id FROM bot_skill_off WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))).fetchall()
        return frozenset(row[0] for row in rows)

    async def set_on(self, user_id: str, bot_id: str, skill_id: str, on: bool) -> bool:
        """Switch a skill on or off for one bot. False: the bot or the skill is not this user's."""
        async with db_session(self._config) as db:
            owned = await (await db.execute(
                "SELECT (SELECT 1 FROM bots WHERE id = ? AND user_id = ?), "
                "(SELECT 1 FROM skills WHERE id = ? AND user_id = ?)",
                (bot_id, user_id, skill_id, user_id))).fetchone()
            if owned[0] is None or owned[1] is None:
                return False
            if on:
                await db.execute("DELETE FROM bot_skill_off WHERE user_id = ? AND bot_id = ? AND skill_id = ?",
                                 (user_id, bot_id, skill_id))
            else:
                await db.execute("INSERT OR IGNORE INTO bot_skill_off (user_id, bot_id, skill_id, created_at) "
                                 "VALUES (?, ?, ?, ?)", (user_id, bot_id, skill_id, _now()))
            await db.commit()
        return True

    async def _by_key(self, user_id: str, key: str, dek: bytes) -> Skill | None:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM skills WHERE user_id = ? AND name_key = ?", (user_id, key))).fetchone()
        return None if row is None else _to_skill(row, dek)

    async def _select(self, user_id: str, extra: str, params: tuple) -> list[Skill]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM skills WHERE user_id = ? {extra}", (user_id, *params))).fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_to_skill(row, dek) for row in rows]
