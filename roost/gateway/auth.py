"""Authentication: registration, login, sessions, and FastAPI dependency.

Carried from LazyClaw's ``lazyclaw/gateway/auth.py`` (git history preserved
via git-filter-repo), trimmed to the Night-1 contract (see the shared
contract's HTTP API table):

- Single-account registration — ``POST /register`` returns 403 once any
  user exists. There is no invite-token/multi-user flow, so the admin
  role distinction, invite tokens, and account-recovery (phrase-based)
  flows the carried version had are all gone — they had no contract
  route to serve. ``roost/crypto/recovery.py`` and ``vault.py`` (also
  unused by anything in the contract) were deleted outright rather than
  carried forward untested.
- The ``User`` dataclass is trimmed to ``id``/``username`` — the only
  fields any contract response shape ever returns.
- Every route handler reads its ``RoostConfig`` from
  ``request.app.state.config`` (set by ``create_app``) instead of a
  module-level lazily-cached ``load_config()`` call — the app-factory
  design means each ``create_app()`` instance must be self-contained;
  a shared module cache would leak one test's (or one app's) config into
  another's.
- Rate limiters are likewise per-app-instance state
  (``request.app.state.*_limiter``, constructed in ``create_app``) rather
  than module globals, for the same reason: a module-global limiter
  would silently share its attempt counters across every ``create_app()``
  call in the process (e.g. every test).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
import time as _time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from roost.bots.main_bot import ensure_main_bot
from roost.config import Config
from roost.constants import (
    MAX_PASSWORD_LENGTH,
    MAX_USERNAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
    SESSION_LIFETIME_HOURS,
)
from roost.crypto.key_manager import clear_user_dek, create_user_dek
from roost.db.connection import db_session, ensure_initialized
from roost.gateway.origin import require_origin
from roost.timezones import read_account_timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class User:
    id: str
    username: str


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), stored_hash.encode())


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

async def register_user(config: Config, username: str, password: str) -> User:
    """Create a new user: bcrypt password hash, random salt, fresh DEK.

    Raises ``ValueError`` if the username is already taken. Single-
    account enforcement ("closed after the first user") is the route
    handler's job (it needs to answer 403 even for a *different*
    username), not this function's — this only guards the DB's own
    uniqueness constraint against a races-with-itself double call.
    """
    user_id = str(uuid4())
    salt = _generate_salt()
    pw_hash = hash_password(password)

    async with db_session(config) as db:
        existing = await db.execute("SELECT id FROM users WHERE username = ?", (username,))
        if await existing.fetchone():
            raise ValueError(f"Username '{username}' already taken")

        await db.execute(
            "INSERT INTO users (id, username, password_hash, encryption_salt) "
            "VALUES (?, ?, ?, ?)",
            (user_id, username, pw_hash, salt),
        )
        await db.commit()

    # Envelope-encrypt a fresh DEK for this user BEFORE any of their data
    # is ever encrypted.
    await create_user_dek(config, user_id, salt)

    logger.info("Registered user %s (%s)", username, user_id)
    return User(id=user_id, username=username)


def _generate_salt() -> str:
    return secrets.token_urlsafe(16)


async def authenticate_user(config: Config, username: str, password: str) -> User | None:
    """Verify credentials. Returns the User, or None if invalid."""
    async with db_session(config) as db:
        row = await db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        )
        result = await row.fetchone()

    if not result:
        return None
    if not verify_password(password, result[2]):
        return None
    return User(id=result[0], username=result[1])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _session_key(config: Config, token: str) -> str:
    """What the sessions table stores: HMAC-SHA256(server secret, token).

    A stolen database row is therefore not a usable cookie.
    """
    return hmac.new(
        config.server_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


async def create_session(config: Config, user_id: str, expires_hours: int = SESSION_LIFETIME_HOURS) -> str:
    """Create a session row, return the session_id token."""
    session_id = str(uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()

    async with db_session(config) as db:
        await db.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
            (_session_key(config, session_id), user_id, expires_at),
        )
        await db.commit()

    return session_id


async def get_session_user(config: Config, session_id: str) -> User | None:
    """Look up a session, check expiry, return its User (or None)."""
    key = _session_key(config, session_id)
    async with db_session(config) as db:
        row = await db.execute(
            "SELECT s.user_id, s.expires_at, u.username, s.id "
            "FROM sessions s JOIN users u ON s.user_id = u.id "
            "WHERE s.id = ?",
            (key,),
        )
        result = await row.fetchone()

    if not result or not hmac.compare_digest(result[3], key):
        return None

    expires_at = datetime.fromisoformat(result[1])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None

    return User(id=result[0], username=result[2])


async def delete_session(config: Config, session_id: str) -> None:
    """Delete a session row."""
    async with db_session(config) as db:
        await db.execute(
            "DELETE FROM sessions WHERE id = ?", (_session_key(config, session_id),)
        )
        await db.commit()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME = "roost_session"


async def get_current_user(request: Request) -> User:
    """Extract the session cookie, resolve the user. Raises 401 on failure."""
    config = request.app.state.config
    await ensure_initialized(config)

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await get_session_user(config, session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return user


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory per-key sliding-window rate limiter.

    Public (not ``_RateLimiter``) and stateless-to-construct: each
    ``create_app()`` call builds its own instances and hangs them off
    ``app.state`` (see ``roost/gateway/app.py``) rather than sharing
    module-level limiters across every app instance in the process.

    ``disabled`` (S1 Task 10): ``make e2e`` runs every spec file against
    ONE shared gateway process (``ROOST_MODEL=scripted``), so the per-IP
    login limit meant for an attacker is reachable from plain, correct
    logins once a suite spans enough spec files. Scripted mode never runs
    with a real model in production, so lifting the limit there only for
    that mode can't open a hole for a real attacker.
    """

    def __init__(self, max_requests: int, window_seconds: int, *, disabled: bool = False) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._disabled = disabled
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Returns True if the request is allowed, False if rate-limited."""
        if self._disabled:
            return True
        now = _time.monotonic()
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if now - t < self._window]
        if len(self._requests[key]) >= self._max:
            return False
        self._requests[key].append(now)
        return True


# Tiny denylist of the most-guessed passwords. Not exhaustive — length +
# this denylist + bcrypt + rate limiting are the real defenses; this just
# rejects the laziest choices that still pass a plain length check.
_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "password1!",
    "12345678", "123456789", "1234567890", "qwerty123",
    "iloveyou1", "administrator", "letmein123", "welcome123",
    "trustno1", "superman1", "hello1234", "changeme1",
    "roost1234", "roostroost",
})


class RegisterRequest(BaseModel):
    username: str = Field(min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH, pattern=r"^[\w.-]+$")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _reject_common_password(cls, v: str) -> str:
        if v.lower() in _COMMON_PASSWORDS:
            raise ValueError("Password is too common — choose a less guessable one.")
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=MAX_USERNAME_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


def _is_production(config: Config) -> bool:
    """Whether the gateway's secure-cookie flag should be set.

    ``config.host`` is validated loopback-only by ``load_config`` (see
    the Global Constraints: every listener binds 127.0.0.1, never
    0.0.0.0), so this is always False today — written as a check against
    ``config.host`` rather than a hardcoded ``False`` so it keeps meaning
    something if that constraint is ever relaxed.

    The one exception ``load_config`` allows — ``0.0.0.0`` inside the
    gateway container — is still plain HTTP on the host's 127.0.0.1:18800
    only (docker-compose.yml publishes nothing else), so it is not
    "production" either: a Secure cookie there would never be sent back.
    """
    if config.in_container:
        return False
    return config.host not in ("127.0.0.1", "localhost")


def _set_session_cookie(response: Response, config: Config, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=_is_production(config),
        samesite="strict",
        max_age=SESSION_LIFETIME_HOURS * 3600,
    )


@auth_router.post("/register", status_code=201, dependencies=[Depends(require_origin)])
async def register(body: RegisterRequest, request: Request, response: Response):
    config = request.app.state.config
    await ensure_initialized(config)

    client_ip = request.client.host if request.client else "unknown"
    if not request.app.state.register_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")

    async with db_session(config) as db:
        count_row = await db.execute("SELECT COUNT(*) FROM users")
        count_result = await count_row.fetchone()
        user_count = count_result[0] if count_result else 0

    if user_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Registration is closed — Roost supports a single account.",
        )

    try:
        user = await register_user(config, body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    try:
        await ensure_main_bot(request.app.state.bots, user.id)
    except Exception:
        # The account exists either way; the next boot's ensure_main_bots repairs it.
        logger.exception("Could not create the main bot for new user %s", user.id)

    session_id = await create_session(config, user.id)
    _set_session_cookie(response, config, session_id)
    return {"id": user.id, "username": user.username}


@auth_router.post("/login", dependencies=[Depends(require_origin)])
async def login(body: LoginRequest, request: Request, response: Response):
    config = request.app.state.config
    await ensure_initialized(config)

    client_ip = request.client.host if request.client else "unknown"
    if not request.app.state.login_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    if not request.app.state.login_username_limiter.check(body.username.lower()):
        raise HTTPException(status_code=429, detail="Too many login attempts for this account. Try again later.")

    user = await authenticate_user(config, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = await create_session(config, user.id)
    _set_session_cookie(response, config, session_id)
    return {"id": user.id, "username": user.username}


@auth_router.post("/logout", status_code=204, dependencies=[Depends(require_origin)])
async def logout(request: Request, response: Response) -> None:
    config = request.app.state.config
    await ensure_initialized(config)

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        user = await get_session_user(config, session_id)
        if user:
            clear_user_dek(user.id)
        await delete_session(config, session_id)

    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=_is_production(config),
        samesite="strict",
    )


@auth_router.get("/me")
async def me(request: Request, user: User = Depends(get_current_user)):
    zone = await read_account_timezone(request.app.state.config, user.id)
    return {"id": user.id, "username": user.username, "timezone": zone}
