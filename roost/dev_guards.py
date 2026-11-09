"""Pure test/production data-isolation guard logic.

Lives in the main ``roost`` package (not under ``tests/``) for one reason:
it must stay importable from an isolated ``pytester`` subprocess project,
which gets its own throwaway rootdir with no access to this repo's
``tests/`` directory. See ``tests/test_tripwire_exit.py`` for the
end-to-end proof that violating either check below really exits a pytest
session with code 3, and ``tests/conftest.py`` for the real guard that
runs this on every test session.

Background: a 2026-07-03 production outage (this app's ancestor,
LazyClaw) happened because a host-run ``pytest`` picked up the live
production data directory when an env override was silently not honored.
This module exists so that class of bug is caught loudly, not silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

DEFAULT_REAL_DIRS: tuple[Path, ...] = (
    Path("~/Roost").expanduser(),
    Path("/Users/blckit/Desktop/Code_Projects/lazyclaw/data"),
)


class _MacConfigLike(Protocol):
    mac_home: Path
    mac_backups_dir: Path


def check_mac_home(
    config: _MacConfigLike, real_home: Path, real_dirs: tuple[Path, ...] = DEFAULT_REAL_DIRS
) -> str | None:
    """Return a violation message when the Mac folder settings point at the user's real files.

    Either one is fatal: ``mac_home`` (where the keeper judges and opens grants) must not be
    the real home folder, and ``mac_backups_dir`` must not sit inside a real Roost folder."""
    if config.mac_home.resolve() == real_home.resolve():
        return f"mac_home resolved to the real home folder {real_home.resolve()}; ROOST_MAC_HOME was not honored."
    if is_inside_any(config.mac_backups_dir, real_dirs):
        return (
            f"mac_backups_dir resolved to {config.mac_backups_dir.resolve()}, which is inside a real data "
            "directory; ROOST_MAC_BACKUPS_DIR was not honored."
        )
    return None


class _ConfigLike(Protocol):
    database_dir: Path
    desks_dir: Path


def is_inside_any(path: Path, real_dirs: tuple[Path, ...]) -> bool:
    """True if ``path`` resolves to, or inside, any of ``real_dirs``."""
    resolved = path.resolve()
    for real in real_dirs:
        real_resolved = real.resolve()
        if resolved == real_resolved or real_resolved in resolved.parents:
            return True
    return False


def check_data_isolation(
    data_dir: Path,
    desks_dir: Path,
    *,
    load_config: Callable[[], _ConfigLike],
    real_dirs: tuple[Path, ...] = DEFAULT_REAL_DIRS,
) -> str | None:
    """Return a violation message, or ``None`` if the override demonstrably took.

    Two independent checks, either one is fatal:

      1. The throwaway directories we're about to force tests onto are not
         themselves inside a real data directory (a broken tmp-dir
         factory, a hijacked default, a forbidden basetemp).
      2. ``load_config()`` — called by the caller AFTER setting the env
         override — actually resolves to those same directories (the
         "ignored override" case: a renamed env var, a wrong default
         order, a later refactor that stops honoring
         ``ROOST_DATA_DIR``/``ROOST_DESKS_DIR``).

    ``load_config`` is injected (rather than imported here) so this stays
    a pure function with no import-time side effects, and so tests can
    exercise both branches without a real ``RoostConfig``.
    """
    for label, resolved_dir in (
        ("ROOST_DATA_DIR", data_dir),
        ("ROOST_DESKS_DIR", desks_dir),
    ):
        if is_inside_any(resolved_dir, real_dirs):
            return (
                f"{label} resolved to {resolved_dir.resolve()}, which is "
                f"inside a real data directory ({[str(d) for d in real_dirs]})."
            )

    cfg = load_config()

    if cfg.database_dir.resolve() != data_dir.resolve():
        return (
            f"load_config() resolved database_dir to {cfg.database_dir.resolve()}, "
            f"not the overridden {data_dir.resolve()} — the ROOST_DATA_DIR "
            "override was not honored."
        )
    if cfg.desks_dir.resolve() != desks_dir.resolve():
        return (
            f"load_config() resolved desks_dir to {cfg.desks_dir.resolve()}, "
            f"not the overridden {desks_dir.resolve()} — the ROOST_DESKS_DIR "
            "override was not honored."
        )

    for label, cfg_dir in (
        ("database_dir", cfg.database_dir),
        ("desks_dir", cfg.desks_dir),
    ):
        if is_inside_any(cfg_dir, real_dirs):
            return (
                f"load_config() resolved {label} to {cfg_dir.resolve()}, which "
                f"is inside a real data directory ({[str(d) for d in real_dirs]})."
            )

    return None
