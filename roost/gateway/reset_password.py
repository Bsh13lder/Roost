"""Set a new Roost password from the terminal, for when you can't sign in.

    python -m roost.gateway.reset_password --list      # the usernames (no passwords)
    python -m roost.gateway.reset_password <username>  # asks twice for the new password, hidden

Your data stays readable: its key is sealed with the server secret, never with your password
(``roost/crypto/encryption.py``). Every session of that user ends, so each browser signs in again.
The password is never printed or logged.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable
from typing import TypeVar

from roost.config import Config, load_config
from roost.constants import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from roost.db.connection import close_pool, db_session, ensure_initialized
from roost.gateway.auth import hash_password

T = TypeVar("T")


class ResetError(ValueError):
    """A reset that can't be done, in words for the terminal."""


async def list_usernames(config: Config) -> tuple[str, ...]:
    await ensure_initialized(config)
    async with db_session(config) as db:
        rows = await (await db.execute("SELECT username FROM users ORDER BY username")).fetchall()
    return tuple(row[0] for row in rows)


async def reset_password(config: Config, username: str, password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ResetError(f"The password needs at least {MIN_PASSWORD_LENGTH} and at most "
                         f"{MAX_PASSWORD_LENGTH} characters.")
    await ensure_initialized(config)
    async with db_session(config) as db:
        row = await (await db.execute("SELECT id FROM users WHERE username = ?", (username,))).fetchone()
        if row is None:
            raise ResetError(f"No Roost user named {username}. Run with --list to see the usernames.")
        await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row[0]))
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (row[0],))
        await db.commit()


async def _closing(work: Awaitable[T]) -> T:
    """Run the work, then close the shared database connection so the process can exit."""
    try:
        return await work
    finally:
        await close_pool()


def _ask_password() -> str:
    first = getpass.getpass("New password: ")
    if getpass.getpass("Same password again: ") != first:
        raise ResetError("The two passwords didn't match. Nothing changed.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roost.gateway.reset_password")
    parser.add_argument("username", nargs="?")
    parser.add_argument("--list", action="store_true", help="show the usernames")
    args = parser.parse_args(argv)
    config = load_config()
    try:
        if args.list or not args.username:
            print("\n".join(asyncio.run(_closing(list_usernames(config)))) or "No users yet.")
            return 0
        asyncio.run(_closing(reset_password(config, args.username, _ask_password())))
    except ResetError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Password changed for {args.username}. Sign in again in each browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
