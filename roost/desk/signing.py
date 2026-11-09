"""HMAC request signing shared by the gateway's keeper client and the
keeper's own request-auth dependency (``roost/keeper/auth.py``).

Every signed request carries three headers — ``X-Roost-Ts`` (unix
seconds), ``X-Roost-Nonce`` (a random per-request token) and
``X-Roost-Sig`` (the HMAC-SHA256 hex digest below) — computed over the
method, path, body hash and a timestamp/nonce pair, so a captured request
cannot be replayed (the nonce is remembered for ``_NONCE_TTL_S``), reused
against a different endpoint (method/path are in the signed message), or
have its body altered in flight (the body's own sha256 is in the signed
message, so the HMAC changes too).

This module has no knowledge of HTTP frameworks: ``sign``/``signed_headers``
build headers from primitives, ``verify`` checks them against the same
primitives read back off a request. The keeper's FastAPI dependency
(``roost.keeper.auth.require_signed_body``) is the only place that touches
a ``Request`` object.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Mapping

# A request more than this many seconds away from "now" (either direction)
# is refused — generous enough for modest clock drift between the gateway
# and keeper processes (which run on the same machine), tight enough that
# a captured request is useless shortly after interception.
_CLOCK_SKEW_S = 30

# How long a seen nonce is remembered. Must comfortably exceed
# `_CLOCK_SKEW_S` so a request can never age out of the nonce cache while
# still being inside the timestamp window (which would let it replay).
_NONCE_TTL_S = 120

_NONCE_BYTES = 16


def sign(secret: str, method: str, path: str, body: bytes, ts: int, nonce: str) -> str:
    """Return the hex HMAC-SHA256 digest covering ``ts``, ``nonce``, ``method``,
    ``path`` and a hash of ``body`` — the exact message both sides sign."""
    msg = f"{ts}\n{nonce}\n{method.upper()}\n{path}\n{hashlib.sha256(body).hexdigest()}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def signed_headers(secret: str, method: str, path: str, body: bytes) -> dict[str, str]:
    """Build the three ``X-Roost-*`` headers for a fresh request right now."""
    ts = int(time.time())
    nonce = secrets.token_urlsafe(_NONCE_BYTES)
    sig = sign(secret, method, path, body, ts, nonce)
    return {"X-Roost-Ts": str(ts), "X-Roost-Nonce": nonce, "X-Roost-Sig": sig}


class NonceCache:
    """Remembers recently-seen nonces so a request can't be replayed.

    Not thread-safe by design — the keeper and the gateway's keeper client
    each run a single asyncio event loop, and this cache is always
    accessed from request-handling coroutines on that one loop.
    """

    def __init__(self) -> None:
        self._seen_at: dict[str, int] = {}

    def seen_recently(self, nonce: str, now: int) -> bool:
        self._evict_older_than(now)
        return nonce in self._seen_at

    def remember(self, nonce: str, now: int) -> None:
        self._seen_at[nonce] = now

    def _evict_older_than(self, now: int) -> None:
        expired = [n for n, seen_at in self._seen_at.items() if now - seen_at > _NONCE_TTL_S]
        for n in expired:
            del self._seen_at[n]


def verify(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    now: int,
    seen: NonceCache,
) -> bool:
    """Check a request's signature: fresh timestamp, unseen nonce, matching HMAC.

    Returns ``False`` (never raises) on any malformed or invalid input —
    missing headers, a non-integer timestamp, a stale timestamp, a
    replayed nonce, or a signature mismatch. The nonce is only recorded as
    seen once every other check has already passed, so a rejected attempt
    never burns the nonce for a legitimate retry.
    """
    ts_header = headers.get("X-Roost-Ts")
    nonce = headers.get("X-Roost-Nonce")
    sig = headers.get("X-Roost-Sig")
    if not ts_header or not nonce or not sig:
        return False

    try:
        ts = int(ts_header)
    except ValueError:
        return False

    if abs(now - ts) > _CLOCK_SKEW_S:
        return False
    if seen.seen_recently(nonce, now):
        return False

    expected = sign(secret, method, path, body, ts, nonce)
    if not hmac.compare_digest(expected, sig):
        return False

    seen.remember(nonce, now)
    return True
