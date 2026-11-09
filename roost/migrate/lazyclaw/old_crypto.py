# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/crypto/encryption.py and key_manager.py @ 21e1002
# (get_user_dek, derive_server_key, unwrap_dek, decrypt), adapted: read-only, strict.

"""Reading LazyClaw's keys and ciphertext. Nothing here writes anywhere.

The old DEK lives in a ``bytearray`` that ``close`` zeroes. Errors name the row and
field, never the secret, the key or any decrypted text.
"""

from __future__ import annotations

import sqlite3
from types import TracebackType

from cryptography.exceptions import InvalidTag

from roost.crypto.encryption import decrypt, derive_key, derive_wrapping_key, secure_zero, unwrap_dek, user_aad
from roost.migrate.lazyclaw.constants import (
    ENC_PREFIX, ENC_V2_PREFIX, LEGACY_FIXED_SALT, LEGACY_ITERATIONS, PASSWORD_KDF_ITERATIONS,
    UNREADABLE_MARKER, VERIFY_COLUMNS,
)


class OldCryptoError(Exception):
    """A LazyClaw key or value could not be read. The message is safe to show."""


def derive_legacy_key(server_secret: str, user_id: str) -> bytes:
    """LazyClaw's pre-envelope key (users whose ``encrypted_dek`` is NULL)."""
    return derive_key(server_secret + user_id, LEGACY_FIXED_SALT, LEGACY_ITERATIONS)


class OldKeys:
    """One LazyClaw user's DEK plus strict decryption with it."""

    def __init__(self, user_id: str, dek: bytearray) -> None:
        self.user_id = user_id
        self._dek: bytearray | None = dek
        self.plain_count = 0

    def __enter__(self) -> "OldKeys":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        if self._dek is not None:
            secure_zero(self._dek)
            self._dek = None

    def decrypt(self, value: str | None, where: str, aad_context: str | None = None) -> str | None:
        """Strict decrypt. ``where`` names the row ("tasks.<id>.title") for errors."""
        if self._dek is None:
            raise OldCryptoError("The LazyClaw key is already closed.")
        if value is None or value == "":
            return value
        if value == UNREADABLE_MARKER:
            raise OldCryptoError(f"LazyClaw itself could not read {where} ([encrypted]).")
        if not value.startswith(ENC_PREFIX):
            self.plain_count += 1
            return value
        return self._decrypt_token(value, where, aad_context)

    def _decrypt_token(self, value: str, where: str, aad_context: str | None) -> str:
        key = bytes(self._dek or b"")
        for aad in self._aads(value, aad_context):
            try:
                return decrypt(value, key, aad)
            except (InvalidTag, ValueError):
                continue
        raise OldCryptoError(f"Could not decrypt {where}: wrong key or damaged value.")

    def _aads(self, value: str, aad_context: str | None) -> list[bytes | None]:
        if not value.startswith(ENC_V2_PREFIX):
            return [None]
        candidates = [user_aad(self.user_id, aad_context)] if aad_context else []
        return [*candidates, user_aad(self.user_id)]


def _pick_user(conn: sqlite3.Connection, username: str | None) -> sqlite3.Row | tuple:
    if username is not None:
        rows = conn.execute(
            "SELECT id, encryption_salt, encrypted_dek FROM users WHERE username = ?", (username,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT id, encryption_salt, encrypted_dek FROM users").fetchall()
    if not rows:
        raise OldCryptoError("No LazyClaw user found" + (f" named {username!r}." if username else "."))
    if len(rows) > 1:
        raise OldCryptoError("More than one LazyClaw user: pass --old-username to pick one.")
    return rows[0]


def load_old_keys(conn: sqlite3.Connection, server_secret: str, username: str | None) -> OldKeys:
    """Unwrap the chosen user's DEK from the snapshot connection. Writes nothing."""
    user_id, salt, wrapped = _pick_user(conn, username)
    try:
        if wrapped:
            wrapping = derive_wrapping_key(server_secret, user_id, str(salt).encode("utf-8"))
            dek = unwrap_dek(wrapped, wrapping)
        else:
            dek = derive_legacy_key(server_secret, user_id)
    except (InvalidTag, ValueError) as exc:
        raise OldCryptoError(
            "That SERVER_SECRET does not open this LazyClaw user's key. Check the secret and try again."
        ) from exc
    return OldKeys(user_id, bytearray(dek))


def load_old_keys_by_password(conn: sqlite3.Connection, username: str, password: str) -> OldKeys:
    """Unwrap the DEK with the user's LazyClaw LOGIN password (``password_encrypted_dek``).

    LazyClaw: ``enc:v1(hex(master_key))`` under PBKDF2-SHA256(password, encryption_salt, 100k).
    The password is never stored or echoed. Call ``verify_keys`` before trusting the result.
    """
    row = conn.execute(
        "SELECT id, encryption_salt, password_encrypted_dek FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        raise OldCryptoError(f"No LazyClaw user named {username!r}.")
    user_id, salt, wrapped = row
    if not wrapped:
        raise OldCryptoError("This LazyClaw user has no password-wrapped key. Use --unlock server-secret.")
    try:
        key = derive_key(password, str(salt).encode("utf-8"), PASSWORD_KDF_ITERATIONS)
        raw = bytes.fromhex(decrypt(wrapped, key))
    except (InvalidTag, ValueError) as exc:
        raise OldCryptoError(
            "That password does not open this LazyClaw user's key. Check the username and password."
        ) from exc
    if len(raw) != 32:
        raise OldCryptoError("The unwrapped LazyClaw key has an unexpected length.")
    return OldKeys(user_id, bytearray(raw))


def _known_ciphertext(conn: sqlite3.Connection, user_id: str) -> tuple[str, str] | None:
    for table, column in VERIFY_COLUMNS:
        try:
            row = conn.execute(
                f'SELECT id, "{column}" FROM "{table}" WHERE user_id = ? AND "{column}" LIKE \'enc:%\' LIMIT 1',
                (user_id,),
            ).fetchone()
        except sqlite3.Error:
            continue
        if row:
            return f"{table}.{row[0]}.{column}", row[1]
    return None


def verify_keys(conn: sqlite3.Connection, keys: OldKeys) -> bool:
    """Check the key against one real ciphertext. True: proven. False: nothing to check against.

    Raises ``OldCryptoError`` when the key does not open the user's data (the password-wrapped
    key can differ from the key LazyClaw actually encrypted with).
    """
    found = _known_ciphertext(conn, keys.user_id)
    if found is None:
        return False
    where, token = found
    try:
        keys.decrypt(token, where)
    except OldCryptoError as exc:
        raise OldCryptoError("This key does not open the LazyClaw data. Try the other unlock method.") from exc
    return True
