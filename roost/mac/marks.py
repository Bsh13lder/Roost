"""``MacMarkStore``: what Roost last knew of a file it wrote (schema v23 ``mac_file_marks``).

The key is a keyed hash of the grant and the relative path, never the path itself. A mark says "this
file, with exactly this hash, was written by this bot, in a clean or a tainted run". A read whose hash
equals the bot's own clean mark does not taint the run."""

from __future__ import annotations

import hashlib
import hmac
import unicodedata
from datetime import datetime, timezone

from roost.config import RoostConfig
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.mac.models import FileMark

_KEY_LABEL = b"roost:mac-path:v1"


def path_key(dek: bytes, grant_id: str, rel_path: str) -> str:
    """Hex ``HMAC-SHA256(HMAC(dek, label), "{grant_id}\\n{NFC path}")``."""
    key = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    message = f"{grant_id}\n{unicodedata.normalize('NFC', rel_path)}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


class MacMarkStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def get(self, user_id: str, grant_id: str, rel_path: str) -> FileMark | None:
        key = path_key(await get_user_dek(self._config, user_id), grant_id, rel_path)
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT sha256, bot_id, written_tainted, updated_at FROM mac_file_marks "
                "WHERE user_id = ? AND grant_id = ? AND path_key = ?", (user_id, grant_id, key))).fetchone()
        if row is None:
            return None
        return FileMark(row["sha256"], row["bot_id"], bool(row["written_tainted"]), row["updated_at"])

    async def upsert(self, user_id: str, grant_id: str, rel_path: str, sha256: str, bot_id: str | None,
                     *, written_tainted: bool) -> None:
        key = path_key(await get_user_dek(self._config, user_id), grant_id, rel_path)
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO mac_file_marks (user_id, grant_id, path_key, sha256, bot_id, written_tainted, updated_at) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id, grant_id, path_key) DO UPDATE SET "
                "sha256 = excluded.sha256, bot_id = excluded.bot_id, written_tainted = excluded.written_tainted, "
                "updated_at = excluded.updated_at",
                (user_id, grant_id, key, sha256, bot_id, int(written_tainted), datetime.now(timezone.utc).isoformat()))
            await db.commit()

    async def clean_for(self, user_id: str, grant_id: str, rel_path: str, sha256: str, bot_id: str) -> bool:
        """True when ``sha256`` is exactly what this bot wrote to this file in a clean run."""
        mark = await self.get(user_id, grant_id, rel_path)
        return (mark is not None and mark.sha256 == sha256 and not mark.written_tainted
                and mark.bot_id == bot_id)
