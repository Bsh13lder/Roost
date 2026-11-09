"""Envelope encryption key manager.

Manages per-user Data Encryption Keys (DEKs) using the envelope pattern:

    SERVER_SECRET + user_id + per_user_salt
        → PBKDF2 (600K iterations)
        → wrapping_key
        → AES-GCM-wraps DEK
        → stored as ``encrypted_dek`` in users table

    DEK (random 256-bit)
        → encrypts ALL user data (messages, threads, bots, events, ...)

Benefits:
- Per-user isolation: each user has a unique random DEK
- Memory safety: DEKs cleared from cache on logout / TTL expiry
- Key rotation: re-wrapping a DEK under a new server secret never touches
  the data it encrypts (not implemented here — no deployed secret has
  ever needed rotating yet; add ``rotate_server_secret`` back if one
  does, re-wrapping each user's ``encrypted_dek`` the same way
  ``create_user_dek`` wraps a fresh one)

Night-1 trim: the carried version also had a "legacy migration" branch
in ``get_user_dek`` for users created before envelope encryption existed
(deriving a key straight from ``SERVER_SECRET`` instead of unwrapping a
stored DEK) and a ``rotate_server_secret``/``clear_all_deks`` pair for
rotating the server secret across all users. Roost has no pre-envelope
users — ``register_user`` always calls ``create_user_dek`` before any
data is encrypted — and no server-secret-rotation operator flow exists
yet, so both were dead code paths here; see ``roost/crypto/encryption.py``
for the matching trim of their underlying primitives.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

from roost.config import Config
from roost.crypto.encryption import (
    derive_wrapping_key,
    generate_dek,
    secure_zero,
    unwrap_dek,
    wrap_dek,
)
from roost.db.connection import db_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory DEK cache with TTL
# ---------------------------------------------------------------------------

_DEK_CACHE_TTL = 3600.0  # 1 hour
_DEK_CACHE_MAX = 128

@dataclass
class _CachedDEK:
    dek: bytearray  # mutable so we can zero it
    created_at: float


_cache: dict[str, _CachedDEK] = {}
_cache_lock = threading.Lock()


def _evict_expired() -> None:
    """Remove expired entries. Must be called with _cache_lock held."""
    now = time.monotonic()
    expired = [
        uid for uid, entry in _cache.items()
        if (now - entry.created_at) >= _DEK_CACHE_TTL
    ]
    for uid in expired:
        entry = _cache.pop(uid)
        secure_zero(entry.dek)


def _cache_dek(user_id: str, dek: bytes) -> bytes:
    """Store a DEK in cache. Returns the same DEK bytes."""
    with _cache_lock:
        _evict_expired()
        # Evict oldest if full
        if len(_cache) >= _DEK_CACHE_MAX and user_id not in _cache:
            oldest_uid = min(_cache, key=lambda k: _cache[k].created_at)
            old = _cache.pop(oldest_uid)
            secure_zero(old.dek)

        # Replace existing entry
        existing = _cache.pop(user_id, None)
        if existing is not None:
            secure_zero(existing.dek)

        _cache[user_id] = _CachedDEK(
            dek=bytearray(dek),
            created_at=time.monotonic(),
        )
    return dek


def _get_cached_dek(user_id: str) -> bytes | None:
    """Get DEK from cache if present and not expired."""
    with _cache_lock:
        entry = _cache.get(user_id)
        if entry is None:
            return None
        if (time.monotonic() - entry.created_at) >= _DEK_CACHE_TTL:
            secure_zero(entry.dek)
            _cache.pop(user_id, None)
            return None
        return bytes(entry.dek)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_user_dek(config: Config, user_id: str) -> bytes:
    """Get the Data Encryption Key for a user.

    1. Returns from cache if available and not expired.
    2. Loads ``encrypted_dek`` from the users table and unwraps it with
       the wrapping key derived from the server secret + user salt.

    Raises ``ValueError`` if the user doesn't exist, or has no
    ``encrypted_dek`` yet — every account gets one at registration (see
    ``create_user_dek``), so a missing one means a corrupted row, not a
    normal state to silently paper over.

    CPU-bound key derivation (PBKDF2, unwrap) runs in a thread pool to
    avoid blocking the async event loop.
    """
    # Fast path: cache hit
    cached = _get_cached_dek(user_id)
    if cached is not None:
        return cached

    # Load user's salt and wrapped DEK from DB
    async with db_session(config) as db:
        row = await db.execute(
            "SELECT encryption_salt, encrypted_dek FROM users WHERE id = ?",
            (user_id,),
        )
        result = await row.fetchone()

    if not result:
        raise ValueError(f"User {user_id} not found")

    user_salt: str = result[0]
    encrypted_dek_token: str | None = result[1]
    if not encrypted_dek_token:
        raise ValueError(
            f"User {user_id} has no encryption key set up — this should "
            "never happen for an account created through register_user()."
        )

    def unwrap() -> bytes:
        wrapping_key = derive_wrapping_key(
            config.server_secret, user_id, user_salt.encode("utf-8"),
        )
        return unwrap_dek(encrypted_dek_token, wrapping_key)

    dek = await asyncio.to_thread(unwrap)
    return _cache_dek(user_id, dek)


async def create_user_dek(
    config: Config,
    user_id: str,
    user_salt: str,
) -> bytes:
    """Generate and store a new DEK for a freshly registered user.

    Call this during registration, BEFORE any data is encrypted.
    """
    dek = generate_dek()
    await _store_wrapped_dek(config, user_id, user_salt, dek)
    return _cache_dek(user_id, dek)


def clear_user_dek(user_id: str) -> None:
    """Remove a user's DEK from cache (call on logout)."""
    with _cache_lock:
        entry = _cache.pop(user_id, None)
        if entry is not None:
            secure_zero(entry.dek)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _store_wrapped_dek(
    config: Config,
    user_id: str,
    user_salt: str,
    dek: bytes,
) -> None:
    """Wrap a DEK and store it in the users table."""
    wrapping_key = derive_wrapping_key(
        config.server_secret, user_id, user_salt.encode("utf-8"),
    )
    wrapped = wrap_dek(dek, wrapping_key)
    async with db_session(config) as db:
        await db.execute(
            "UPDATE users SET encrypted_dek = ? WHERE id = ?",
            (wrapped, user_id),
        )
        await db.commit()
