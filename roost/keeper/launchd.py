"""The desk keeper's launchd agent — so it runs all the time, as you.

``make desk-keeper-install`` installs Roost into ``~/Roost/venv`` and runs
``python -m roost.keeper.launchd write ~/Library/LaunchAgents/
app.roost.desk-keeper.plist``, then bootstraps that plist into the user's
GUI launchd domain. launchd then starts the keeper at login
(``RunAtLoad``) and restarts it whenever it exits (``KeepAlive``).

Two macOS rules shape every path here:

- **TCC blocks launchd jobs from ``~/Desktop``** (silently: the job just
  fails to read its files). So the keeper never runs from the repo
  checkout — it runs from ``~/Roost/venv``, keeps data in ``~/Roost/data``
  and logs to ``~/Roost/logs`` — and ``render_plist`` refuses any home
  that would put one of those under a ``Desktop`` directory.
- **launchd never expands ``~``**, so every path is written absolute.

The keeper itself binds 127.0.0.1 only (``roost/config.py``); this plist
never sets ``ROOST_HOST`` or ``ROOST_IN_CONTAINER``.
"""

from __future__ import annotations

import os
import plistlib
import sys
from dataclasses import dataclass
from pathlib import Path

LAUNCHD_LABEL = "app.roost.desk-keeper"

# launchd's own default PATH has no /usr/local/bin, where Docker Desktop
# puts the `docker` CLI the keeper shells out to for workspace containers.
LAUNCHD_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"

_ROOST_DIRNAME = "Roost"
_TCC_BLOCKED_DIRNAME = "Desktop"
_PLIST_MODE = 0o644

_USAGE = "Usage: python -m roost.keeper.launchd write <plist-path>"

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_USAGE = 2


@dataclass(frozen=True)
class KeeperPaths:
    """Every absolute path the keeper's launchd agent points at."""

    python: Path
    data_dir: Path
    desks_dir: Path
    log_file: Path


def keeper_paths(home: Path) -> KeeperPaths:
    """The agent's paths under ``<home>/Roost``, validated.

    Raises ``ValueError`` for a relative ``home`` (launchd can't expand
    one) or for any path that would land under a ``Desktop`` directory
    (TCC would block the job from it).
    """
    if not home.is_absolute():
        raise ValueError(f"home must be an absolute path (got {str(home)!r}) — launchd never expands it.")
    root = home / _ROOST_DIRNAME
    paths = KeeperPaths(
        python=root / "venv" / "bin" / "python",
        data_dir=root / "data",
        desks_dir=root / "desks",
        log_file=root / "logs" / "keeper.log",
    )
    for path in (paths.python, paths.data_dir, paths.desks_dir, paths.log_file):
        if _TCC_BLOCKED_DIRNAME in path.parts:
            raise ValueError(
                f"{path} is under a {_TCC_BLOCKED_DIRNAME} directory — macOS TCC blocks "
                "launchd jobs there. Install the keeper from a home outside it."
            )
    return paths


def build_plist(home: Path) -> dict[str, object]:
    """The launchd agent definition, as a plain dict (see module docstring)."""
    paths = keeper_paths(home)
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [str(paths.python), "-m", "roost.keeper"],
        "EnvironmentVariables": {
            "ROOST_DATA_DIR": str(paths.data_dir),
            "ROOST_DESKS_DIR": str(paths.desks_dir),
            "PATH": LAUNCHD_PATH,
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(paths.log_file),
        "StandardErrorPath": str(paths.log_file),
    }


def render_plist(home: Path) -> bytes:
    """``build_plist(home)`` serialized as an XML property list."""
    return plistlib.dumps(build_plist(home))


def write_plist(target: Path, home: Path) -> None:
    """Write the agent plist for ``home`` to ``target`` (mode 0644).

    Rendered fully BEFORE anything touches ``target``, so a refused home
    leaves no file behind; then written to a sibling temp file and renamed
    over ``target``, so launchd never sees a half-written plist.
    """
    content = render_plist(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(content)
        tmp.chmod(_PLIST_MODE)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "write":
        print(_USAGE, file=sys.stderr)
        return _EXIT_USAGE

    target = Path(args[1]).expanduser()
    try:
        write_plist(target, Path.home())
    except (ValueError, OSError) as exc:
        print(f"Could not write the desk keeper's launchd plist: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    print(f"Wrote {target}")
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
