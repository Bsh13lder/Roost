"""The teach step log in the database: one sealed row per bot while you teach it (schema v28).

``steps`` is a JSON list of ``TeachStep`` sealed under ``teach_sessions:steps``. ``append`` re-seals the whole
list (it is at most ``TEACH_STEPS_MAX`` small steps), keeps a repeat of the last step once and stops at the cap.
Every statement names ``user_id``: another user's bot has no session."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite
from pydantic import TypeAdapter

from roost.config import Config
from roost.constants import TEACH_STEPS_MAX
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.teach.models import TeachSession, TeachStep
from roost.teach.steps import same_step

_STEPS = TypeAdapter(tuple[TeachStep, ...])
_COLUMNS = "id, user_id, bot_id, steps, capped, started_at"


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "teach_sessions:steps")


def _dump(steps: tuple[TeachStep, ...]) -> str:
    return json.dumps([step.model_dump() for step in steps])


class TeachStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def begin(self, user_id: str, bot_id: str) -> TeachSession:
        """A new, empty log for this bot; an older one is thrown away."""
        dek = await get_user_dek(self._config, user_id)
        started = datetime.now(timezone.utc).isoformat()
        async with db_session(self._config) as db:
            await db.execute("DELETE FROM teach_sessions WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))
            await db.execute(
                f"INSERT INTO teach_sessions ({_COLUMNS}, step_count) VALUES (?,?,?,?,0,?,0)",
                (str(uuid4()), user_id, bot_id, encrypt_field(_dump(()), dek, _aad(user_id)), started))
            await db.commit()
        found = await self.get(user_id, bot_id)
        if found is None:
            raise RuntimeError("The teach session could not be read back.")
        return found

    async def get(self, user_id: str, bot_id: str) -> TeachSession | None:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_COLUMNS} FROM teach_sessions WHERE user_id = ? AND bot_id = ?",
                (user_id, bot_id))).fetchone()
        if row is None:
            return None
        return await self._session(row)

    async def append(self, user_id: str, bot_id: str, step: TeachStep) -> bool:
        """Add one step. False when there is no session, the step repeats the last one, or the log is full."""
        session = await self.get(user_id, bot_id)
        if session is None or (session.steps and same_step(session.steps[-1], step)):
            return False
        if len(session.steps) >= TEACH_STEPS_MAX:
            await self._write(session, session.steps, capped=True)
            return False
        await self._write(session, (*session.steps, step), capped=session.capped)
        return True

    async def delete(self, user_id: str, bot_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("DELETE FROM teach_sessions WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))
            await db.commit()

    async def _write(self, session: TeachSession, steps: tuple[TeachStep, ...], *, capped: bool) -> None:
        dek = await get_user_dek(self._config, session.user_id)
        sealed = encrypt_field(_dump(steps), dek, _aad(session.user_id))
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE teach_sessions SET steps = ?, step_count = ?, capped = ? WHERE id = ? AND user_id = ?",
                (sealed, len(steps), int(capped), session.id, session.user_id))
            await db.commit()

    async def _session(self, row: aiosqlite.Row) -> TeachSession:
        user_id = row["user_id"]
        dek = await get_user_dek(self._config, user_id)
        raw = decrypt_field(row["steps"], dek, _aad(user_id)) or "[]"
        return TeachSession(id=row["id"], user_id=user_id, bot_id=row["bot_id"],
                            steps=_STEPS.validate_json(raw), capped=bool(row["capped"]),
                            started_at=row["started_at"])
