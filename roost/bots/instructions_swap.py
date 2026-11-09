"""Compare-and-swap on a bot's instructions (A2: update_my_instructions and its Undo).

``swap_instructions`` writes ``new`` only while the bot's instructions are still exactly ``expected``. The read and
the write share one connection, and the ``UPDATE`` names the sealed value it read, so a change that lands between
them makes the write miss instead of being overwritten. Every query names ``user_id``."""

from __future__ import annotations

from datetime import datetime, timezone

from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

_INSTRUCTIONS_AAD = "bots:instructions"


async def swap_instructions(config: Config, user_id: str, bot_id: str, expected: str, new: str) -> bool:
    """True when the bot's instructions were ``expected`` and are now ``new``; False otherwise (nothing written)."""
    aad = user_aad(user_id, _INSTRUCTIONS_AAD)
    dek = await get_user_dek(config, user_id)
    async with db_session(config) as db:
        row = await (await db.execute(
            "SELECT instructions FROM bots WHERE id = ? AND user_id = ?", (bot_id, user_id))).fetchone()
        if row is None or decrypt_field(row["instructions"], dek, aad) != expected:
            return False
        cursor = await db.execute(
            "UPDATE bots SET instructions = ?, updated_at = ? WHERE id = ? AND user_id = ? AND instructions = ?",
            (encrypt(new, dek, aad), datetime.now(timezone.utc).isoformat(), bot_id, user_id, row["instructions"]))
        await db.commit()
    return cursor.rowcount == 1
