"""Roost CLI entry point.

``python -m roost``                    — serve the gateway on config.host:port.
``python -m roost create-user <name>`` — create the (single) account
    interactively, without going through the web UI's register flow.
    Exists for first-run setup and for recovering access if the web flow
    is ever unreachable; unlike ``POST /api/auth/register`` it does not
    refuse once an account already exists — it's an operator tool, not
    the contract's single-account HTTP route.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

import uvicorn

from roost.config import load_config
from roost.log_rotation import install_process_log, logs_dir_for
from roost.db.connection import close_pool, init_db
from roost.constants import MIN_PASSWORD_LENGTH
from roost.db.connection import db_session
from roost.gateway.auth import hash_password, register_user

_USAGE = "Usage: python -m roost create-user <username> | reset-password <username>"


def _strip_leaked_anthropic_api_key() -> None:
    """Final review, finding 7: ``roost.llm.claude_sdk.build_options``
    removes ``ANTHROPIC_API_KEY`` from its OWN ``options.env`` copy, but
    the installed Claude SDK builds the CLI's subprocess environment as
    ``{**os.environ, ..., **options.env}`` -- omitting a key from the
    right-hand dict never removes it from the left, so a key already
    sitting in THIS PROCESS's env survives that merge untouched (it
    breaks subscription login; see the Global Constraints). The only
    fix that actually works is removing it from the process's own env,
    once, here -- before ``uvicorn.run`` (and so before any request's
    SDK call) can ever see it.
    """
    os.environ.pop("ANTHROPIC_API_KEY", None)


def _serve() -> None:
    _strip_leaked_anthropic_api_key()
    config = load_config()
    install_process_log(logs_dir_for(config.database_dir), "gateway.log", config.log_level,
                        fallback_dir=config.database_dir / "logs")
    uvicorn.run(
        "roost.gateway.app:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )


async def _create_user(username: str) -> None:
    config = load_config()
    await init_db(config)
    try:
        password = getpass.getpass("Password: ")
        try:
            user = await register_user(config, username, password)
        except ValueError as exc:
            print(f"Could not create user: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(f"Created user {user.username!r} (id={user.id}).")
    finally:
        await close_pool()


def _ask_new_password() -> str:
    first = getpass.getpass("New password: ")
    if len(first) < MIN_PASSWORD_LENGTH:
        print(f"The password needs at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        raise SystemExit(1)
    if getpass.getpass("Type it again: ") != first:
        print("The two passwords don't match. Nothing was changed.", file=sys.stderr)
        raise SystemExit(1)
    return first


async def _reset_password(username: str) -> None:
    """Operator recovery: replace the login hash and end every session. The data key is not tied to the
    password (it is wrapped by the server secret), so all data stays readable."""
    config = load_config()
    await init_db(config)
    try:
        password = _ask_new_password()
        async with db_session(config) as db:
            row = await (await db.execute("SELECT id FROM users WHERE username = ?", (username,))).fetchone()
            if row is None:
                print(f"No account called {username!r}.", file=sys.stderr)
                raise SystemExit(1)
            await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row[0]))
            await db.execute("DELETE FROM sessions WHERE user_id = ?", (row[0],))
            await db.commit()
        print(f"Password changed for {username!r}. Log in with the new one.")
    finally:
        await close_pool()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv

    if not args:
        _serve()
        return

    if args[0] == "create-user":
        if len(args) != 2:
            print(_USAGE, file=sys.stderr)
            raise SystemExit(1)
        asyncio.run(_create_user(args[1]))
        return

    if args[0] == "reset-password":
        if len(args) != 2:
            print(_USAGE, file=sys.stderr)
            raise SystemExit(1)
        asyncio.run(_reset_password(args[1]))
        return

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
