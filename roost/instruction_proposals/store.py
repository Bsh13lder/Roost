"""``instruction_proposals``: one row per card, its payload sealed (enc:v2, ``instruction_proposals:payload``).

Every statement names ``user_id``; another user's proposal reads as no proposal. ``decide`` is a compare-and-set
on ``state``, so of two presses exactly one wins."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.instruction_proposals.models import InstructionPayload, InstructionProposal

_COLUMNS = ("id, user_id, bot_id, payload, tainted, from_routine, state, thread_id, message_id, created_at, "
            "decided_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str) -> bytes:
    return user_aad(user_id, "instruction_proposals:payload")


def _to_proposal(row: aiosqlite.Row, dek: bytes) -> InstructionProposal:
    user_id = row["user_id"]
    raw = decrypt_field(row["payload"], dek, _aad(user_id)) or "{}"
    return InstructionProposal(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"],
        payload=InstructionPayload.model_validate_json(raw), tainted=bool(row["tainted"]),
        from_routine=bool(row["from_routine"]), state=row["state"], thread_id=row["thread_id"],
        message_id=row["message_id"], created_at=row["created_at"], decided_at=row["decided_at"])


class InstructionProposalStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, bot_id: str, payload: InstructionPayload, *, thread_id: str,
                     tainted: bool, from_routine: bool) -> InstructionProposal:
        dek = await get_user_dek(self._config, user_id)
        proposal_id = str(uuid4())
        sealed = encrypt_field(payload.model_dump_json(), dek, _aad(user_id))
        async with db_session(self._config) as db:
            await db.execute(
                f"INSERT INTO instruction_proposals ({_COLUMNS}) VALUES (?,?,?,?,?,?,'open',?,NULL,?,NULL)",
                (proposal_id, user_id, bot_id, sealed, int(tainted), int(from_routine), thread_id, _now()))
            await db.commit()
        found = await self.get(user_id, proposal_id)
        if found is None:
            raise RuntimeError("The instructions card could not be read back.")
        return found

    async def get(self, user_id: str, proposal_id: str) -> InstructionProposal | None:
        found = await self._select(user_id, "AND id = ?", (proposal_id,))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[InstructionProposal, ...]:
        return await self._select(user_id, "AND state = 'open' ORDER BY created_at, rowid", ())

    async def count_open(self, user_id: str, bot_id: str) -> int:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM instruction_proposals WHERE user_id = ? AND bot_id = ? AND state = 'open'",
                (user_id, bot_id))).fetchone()
        return int(row[0])

    async def set_message(self, user_id: str, proposal_id: str, message_id: str) -> None:
        async with db_session(self._config) as db:
            await db.execute("UPDATE instruction_proposals SET message_id = ? WHERE id = ? AND user_id = ?",
                             (message_id, proposal_id, user_id))
            await db.commit()

    async def decide(self, user_id: str, proposal_id: str, state: str, *,
                     expected: str = "open") -> InstructionProposal | None:
        """Compare-and-set ``expected`` -> ``state``. ``None`` when it is not the user's or already decided."""
        decided = _now() if state != "open" else None
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE instruction_proposals SET state = ?, decided_at = ? "
                "WHERE id = ? AND user_id = ? AND state = ?",
                (state, decided, proposal_id, user_id, expected))
            await db.commit()
        return await self.get(user_id, proposal_id) if cursor.rowcount == 1 else None

    async def _select(self, user_id: str, extra: str, params: tuple) -> tuple[InstructionProposal, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM instruction_proposals WHERE user_id = ? {extra}",
                (user_id, *params))).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_to_proposal(row, dek) for row in rows)
