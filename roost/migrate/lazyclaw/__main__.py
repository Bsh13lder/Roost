"""``python -m roost.migrate.lazyclaw``: the LazyClaw dry run.

Reads a read-only snapshot of LazyClaw's database, decrypts it in memory, maps it and prints a
report. It writes nothing to Roost and nothing to LazyClaw. The only files it makes are the
snapshot, in a 0700 temp dir, deleted at the end unless ``--keep-snapshot``. Secrets are asked
for with getpass and never printed; decrypted text is never logged.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TextIO

from roost.config import load_config
from roost.migrate.lazyclaw import apply_run
from roost.migrate.lazyclaw.guard import ROOST_RUNNING_MESSAGE, any_port_open
from roost.migrate.lazyclaw.constants import (
    APPLY_CONFIRM_PROMPT, APPLY_NO_WIPE_PROMPT, KEEPER_SECRET_FILE, OLD_PASSWORD_PROMPT, OLD_SECRET_PROMPT, OLD_USERNAME_PROMPT, RESTORE_STEPS, ROOST_PORTS, SERVER_SECRET_FILE, SNAPSHOT_DIR_PREFIX,
    UNLOCK_PASSWORD, UNLOCK_SERVER_SECRET,
)
from roost.migrate.lazyclaw.mapping import map_lazyclaw
from roost.migrate.lazyclaw.models import LazyData, RoostContext
from roost.migrate.lazyclaw.old_crypto import (
    OldCryptoError, OldKeys, load_old_keys, load_old_keys_by_password, verify_keys,
)
from roost.db.connection import close_pool
from roost.migrate.lazyclaw.readback import read_back
from roost.migrate.lazyclaw.reader import read_lazyclaw
from roost.migrate.lazyclaw.report import build_report, render_report
from roost.migrate.lazyclaw.source import SnapshotError, assert_private_dir, delete_snapshot, take_snapshot
from roost.migrate.lazyclaw.roost_side import RoostAccountError
from roost.migrate.lazyclaw.wipe import count_wipe, exact_wipe_counts
from roost.migrate.lazyclaw.writer import ImportRefused, apply_import
from roost.migrate.lazyclaw.undo import UndoError, undo_run
from roost.money.months import current_month

DRY_RUN_USER_ID = "dry-run-user"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m roost.migrate.lazyclaw", description=__doc__)
    p.add_argument("--source", type=Path, default=None, help="LazyClaw's lazyclaw.db (read only; not needed for --undo)")
    p.add_argument("--unlock", choices=(UNLOCK_PASSWORD, UNLOCK_SERVER_SECRET), default=UNLOCK_PASSWORD)
    p.add_argument("--old-username", default=None)
    p.add_argument("--old-secret-env", default=None, help="NAME of an env var holding SERVER_SECRET")
    p.add_argument("--roost-db", type=Path, default=None, help="Roost's roost.db, to count the wipe (read only)")
    p.add_argument("--work-dir", type=Path, default=None, help="an existing 0700 dir inside the temp dir")
    p.add_argument("--keep-snapshot", action="store_true")
    p.add_argument("--lazyclaw-stopped", action="store_true",
                   help="LazyClaw is stopped; read its leftover -wal from a private copy")
    p.add_argument("--apply", action="store_true", help="import into Roost (asks first); never wipes unless --wipe")
    p.add_argument("--wipe", action="store_true",
                   help="with --apply: first wipe this account's tasks and money. Works once ever per account")
    p.add_argument("--yes", action="store_true", help="with --apply: do not ask for the typed yes (never implies --wipe)")
    p.add_argument("--undo", metavar="RUN_ID", default=None, help="remove exactly what that import run added")
    p.add_argument("--force", action="store_true", help="with --undo: also remove rows changed since the import")
    return p


def _work_dir(arg: Path | None) -> Path:
    """The only place this tool writes: a 0700 dir inside the system temp dir."""
    if arg is None:
        return Path(tempfile.mkdtemp(prefix=SNAPSHOT_DIR_PREFIX + "work-"))
    assert_private_dir(arg)
    root = Path(tempfile.gettempdir()).resolve()
    if root not in arg.resolve().parents:
        raise SnapshotError(f"{arg} must be inside the temp folder {root} (and mode 0700).")
    return arg


def _unlock(args: argparse.Namespace, conn: sqlite3.Connection, getpass_fn: Callable[[str], str],
            input_fn: Callable[[str], str], env: Mapping[str, str]) -> OldKeys:
    if args.unlock == UNLOCK_PASSWORD:
        username = args.old_username or input_fn(OLD_USERNAME_PROMPT).strip()
        return load_old_keys_by_password(conn, username, getpass_fn(OLD_PASSWORD_PROMPT))
    secret = env.get(args.old_secret_env or "") or (None if args.old_secret_env else getpass_fn(OLD_SECRET_PROMPT))
    if not secret:
        raise OldCryptoError(f"The environment variable {args.old_secret_env} is empty or not set.")
    return load_old_keys(conn, secret, args.old_username)


def _context() -> RoostContext:
    return RoostContext(user_id=DRY_RUN_USER_ID, import_day=date.today(),
                        imported_at=datetime.now(timezone.utc).isoformat())


def _read(args: argparse.Namespace, snapshot_path: Path, getpass_fn, input_fn, env, out: TextIO) -> LazyData:
    conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
    try:
        with _unlock(args, conn, getpass_fn, input_fn, env) as keys:
            proven = verify_keys(conn, keys)
            print("Key verified against a real encrypted value." if proven
                  else "Warning: nothing encrypted to verify the key against.", file=out)
            return read_lazyclaw(conn, keys)
    finally:
        conn.close()


def _dry_report(data: LazyData, args: argparse.Namespace, out: TextIO) -> None:
    mapped = map_lazyclaw(data, _context())
    print(render_report(build_report(mapped, count_wipe(args.roost_db))), file=out)


def main(argv: list[str] | None = None, *, getpass_fn: Callable[[str], str] = getpass.getpass,
         input_fn: Callable[[str], str] = input, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         env: Mapping[str, str] | None = None, roost_ports: tuple[int, ...] = ROOST_PORTS,
         lazyclaw_ports: tuple[int, ...] | None = None) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if env is None else env
    if args.apply and args.undo:
        print("Use --apply or --undo, not both.", file=err)
        return 2
    if (args.apply or args.undo) and args.roost_db is None:
        print("--apply and --undo need --roost-db <path to roost.db>: they never guess where Roost's data is.",
              file=err)
        return 2
    if (args.apply or args.undo) and any_port_open(roost_ports):
        print(ROOST_RUNNING_MESSAGE, file=err)
        return 1
    if args.undo:
        return _undo(args, env, out, err)
    if args.source is None:
        print("--source <LazyClaw's lazyclaw.db> is required.", file=err)
        return 2
    try:
        work = _work_dir(args.work_dir)
    except SnapshotError as exc:
        print(str(exc), file=err)
        return 2
    try:
        return _dry_run(args, work, getpass_fn, input_fn, env, out, err, lazyclaw_ports)
    finally:
        if args.work_dir is None and not args.keep_snapshot:
            try:
                work.rmdir()
            except OSError:
                pass


def _dry_run(args, work: Path, getpass_fn, input_fn, env, out: TextIO, err: TextIO, lazyclaw_ports=None) -> int:
    try:
        snapshot = take_snapshot(args.source, base_dir=work, lazyclaw_ports=lazyclaw_ports,
                                 wal_ok=args.lazyclaw_stopped)
    except SnapshotError as exc:
        print(str(exc), file=err)
        return 1
    try:
        data = _read(args, snapshot.path, getpass_fn, input_fn, env, out)
        if args.apply:
            return _apply(args, data, input_fn, env, out, err)
        _dry_report(data, args, out)
        return 0
    except (OldCryptoError, SnapshotError) as exc:
        print(str(exc), file=err)
        return 1
    finally:
        if args.keep_snapshot:
            print(f"Snapshot kept at {snapshot.path} (owner only). Delete it when you are done.", file=out)
        else:
            delete_snapshot(snapshot)


def _config_for(args: argparse.Namespace, env: Mapping[str, str]):
    """Roost's config, pinned to the folder of the database the user named.

    This tool never makes a secret: Roost's server and keeper secrets must already exist (env or file),
    otherwise ``load_config`` would invent new ones and the account's key could never be unwrapped.
    """
    folder = args.roost_db.resolve().parent
    if not env.get("ROOST_SERVER_SECRET") and not (folder / SERVER_SECRET_FILE).is_file():
        raise RoostAccountError(f"Roost's server secret was not found ({SERVER_SECRET_FILE} next to the database, or "
                                "ROOST_SERVER_SECRET). Nothing was changed. Point --roost-db at the roost.db of the "
                                "Roost you use, and do not start from an empty folder.")
    if not (folder / KEEPER_SECRET_FILE).is_file():
        raise RoostAccountError(f"{KEEPER_SECRET_FILE} was not found next to the database, so this is not a Roost "
                                "data folder that has been used. Nothing was changed.")
    return load_config({**env, "ROOST_DATA_DIR": str(args.roost_db.resolve().parent)})


def _apply(args: argparse.Namespace, data: LazyData, input_fn, env, out: TextIO, err: TextIO) -> int:
    db_path = args.roost_db.resolve()
    if not db_path.is_file():
        print(f"Roost database not found: {db_path}", file=err)
        return 1
    now = datetime.now(timezone.utc).isoformat()
    run_id = apply_run.new_run_id()
    try:
        config = _config_for(args, env)
        backup = apply_run.backup_database(db_path, run_id)
        print(f"Backup of the Roost database: {backup}", file=out)
        account = apply_run.open_account(config, db_path, now)
        mapped = apply_run.map_for(account, data, now)
        conn = apply_run.connect(db_path)
        try:
            wipe = exact_wipe_counts(conn, account.user_id, account.general_id)
            print(render_report(build_report(mapped, wipe)), file=out)
            if mapped.blocked:
                print("Blocking anomalies: nothing was imported.", file=err)
                return 1
            prompt = APPLY_CONFIRM_PROMPT if args.wipe else APPLY_NO_WIPE_PROMPT
            if not args.yes and input_fn(prompt).strip().lower() != "yes":
                print("Not confirmed: nothing was changed (the backup file stays).", file=err)
                return 1
            result = apply_import(conn, account.dek, account.user_id, mapped, run_id=run_id, imported_at=now,
                                  general_id=account.general_id, wipe=args.wipe)
        finally:
            conn.close()
    except (RoostAccountError, ImportRefused, OSError, sqlite3.Error) as exc:
        print(f"Nothing was imported: {exc}", file=err)
        return 1
    _print_result(result, backup, out)
    return _verify(args, env, account.user_id, mapped, out, err)


def _verify(args: argparse.Namespace, env, user_id: str, mapped, out: TextIO, err: TextIO) -> int:
    """Read everything back through Roost's stores; the import is already committed."""
    try:
        found = asyncio.run(_read_back(_config_for(args, env), user_id, mapped))
    except Exception as exc:  # noqa: BLE001 - any failure here must be reported, never swallowed
        print(f"Read-back could not run ({type(exc).__name__}). Check the data before using Roost.", file=err)
        return 1
    if found.ok:
        done = ", ".join(f"{k} {v}" for k, v in found.checked.items())
        print(f"Read-back OK through Roost's stores and numbers: {done}.", file=out)
        return 0
    print(f"Read-back found {len(found.problems)} problem(s); the import is committed:", file=err)
    for problem in found.problems:
        print(f"  - {problem}", file=err)
    print("Undo it with --undo, or restore the backup.", file=err)
    return 1


async def _read_back(config, user_id: str, mapped):
    try:
        return await read_back(config, user_id, mapped, today_month=current_month())
    finally:
        await close_pool()


def _print_result(result, backup: Path, out: TextIO) -> None:
    if result.wiped is None:
        print("Nothing was wiped (a wipe needs --wipe and happens once ever per account; rows not yet linked "
              "were added).", file=out)
    done = ", ".join(f"{k} {v}" for k, v in sorted(result.imported.items())) or "nothing new"
    print(f"Imported: {done}. Skipped as already imported: {result.already}.", file=out)
    print(f"Run id: {result.run_id}", file=out)
    print(f"Undo this import: --undo {result.run_id} (adds back nothing the wipe removed).", file=out)
    print("Full restore of everything as it was before: " + RESTORE_STEPS.format(backup=backup) + ".", file=out)


def _undo(args: argparse.Namespace, env, out: TextIO, err: TextIO) -> int:
    db_path = args.roost_db.resolve()
    if not db_path.is_file():
        print(f"Roost database not found: {db_path}", file=err)
        return 1
    now = datetime.now(timezone.utc).isoformat()
    try:
        config = _config_for(args, env)
        safety = apply_run.backup_database(db_path, f"undo-{args.undo}")
        print(f"Backup of the Roost database: {safety}", file=out)
        account = apply_run.open_account(config, db_path, now)
        conn = apply_run.connect(db_path)
        try:
            result = undo_run(conn, account.dek, account.user_id, args.undo, general_id=account.general_id,
                              force=args.force)
        finally:
            conn.close()
    except (UndoError, RoostAccountError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=err)
        return 1
    done = ", ".join(f"{k} {v}" for k, v in sorted(result.removed.items())) or "nothing"
    print(f"Undone: removed {done}.", file=out)
    original = apply_run.find_backup(db_path, args.undo)
    where = f"{original}" if original else f"the pre-lazyclaw-{args.undo}.db file in the backups folder"
    print("The wipe that came before that import cannot be undone in place. For a full restore, "
          + RESTORE_STEPS.format(backup=where) + ".", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
