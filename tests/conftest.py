"""Root pytest configuration — test/production data isolation guardrail.

2026-07-03 outage (LazyClaw, this repo's ancestor): ``docker-compose.yml``
bind-mounted ``./data`` to ``/app/data``, so the PRODUCTION SQLite DB lived
at the repo-relative ``./data/lazyclaw.db``. ``lazyclaw/config.py::load_config``
defaulted ``database_dir`` to that same ``./data`` whenever the
``DATABASE_DIR`` env var was unset. A host-run ``pytest tests/`` therefore
opened the live prod DB; the run was killed mid-write and ``init_db``
(``lazyclaw/db/connection.py``) hit
``sqlite3.DatabaseError: database disk image is malformed`` on the next
container boot, crash-looping with no recovery path.

This file exists SOLELY to make that impossible again, for Roost:

  1. ``pytest_configure`` repoints every test onto isolated, disposable
     ``ROOST_DATA_DIR`` / ``ROOST_DESKS_DIR`` dirs *before test collection*
     — earlier than an autouse fixture would run — and forces
     ``ROOST_MODEL=scripted`` + ``ROOST_DESK=fake`` so no test can ever
     reach a real LLM, a real Brave window, or a real workspace container.
  2. A hard tripwire then asserts the repoint actually took, two ways:
     (a) neither throwaway dir itself resolves inside a real data
     directory, and (b) ``load_config()`` — called AFTER the env
     override, exactly like production code would see it — actually
     resolves to those same throwaway dirs. (b) is the one that matters
     most: it is what catches ``load_config`` silently no longer honoring
     the override (a renamed env var, a wrong default order, a later
     refactor), which (a) alone cannot. On any violation the fixture exits
     the whole session LOUDLY (``pytest.exit``, returncode 3) instead of
     letting a single test run.

The decision logic itself lives in ``roost.dev_guards`` (not here) so it
can be exercised directly, including from an isolated ``pytester``
subprocess project — see ``tests/test_tripwire_exit.py`` for the
end-to-end proof that violating either check really exits with code 3,
and ``tests/test_dev_guards.py`` for unit tests of the pure logic.

See MEMORY.md → ``feedback_tests_hit_prod_db.md``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from roost.db.connection import close_pool
from roost.dev_guards import check_data_isolation, check_mac_home

# Makes the `pytester` fixture available to tests/test_tripwire_exit.py.
pytest_plugins = ["pytester"]

# Env vars that determine where Roost resolves its data/desks directories.
# Confirmed against roost/config.py::load_config — these are the only two
# knobs; everything else (server.secret, keeper.secret, roost.db) is
# derived from database_dir.
_DATA_DIR_ENV = "ROOST_DATA_DIR"
_DESKS_DIR_ENV = "ROOST_DESKS_DIR"

_ENV_OVERRIDE_VARS = (_DATA_DIR_ENV, _DESKS_DIR_ENV, "ROOST_MODEL", "ROOST_DESK", "ROOST_MAC_HOME", "ROOST_MAC_BACKUPS_DIR",
                      "ROOST_STEER_DEBOUNCE_SECONDS", "ROOST_MOBILE_DIR", "ROOST_VOICE", "ROOST_TIMEZONE")

# Populated by pytest_configure, read by the autouse fixture's teardown.
_data_dir: Path | None = None
_desks_dir: Path | None = None
_mac_dirs: list[Path] = []
_original_env: dict[str, str | None] = {}


def pytest_configure(config: pytest.Config) -> None:
    """Repoint the env onto throwaway dirs before collection, then verify it.

    Running this in ``pytest_configure`` (rather than only in an autouse
    fixture) means the override is in place before any test MODULE is
    even imported — so a future collection-time ``load_config()`` call
    would also see the throwaway dirs, not real ones.
    """
    global _data_dir, _desks_dir, _original_env

    _data_dir = Path(tempfile.mkdtemp(prefix="roost-test-data-"))
    _desks_dir = Path(tempfile.mkdtemp(prefix="roost-test-desks-"))

    mac_home = Path(tempfile.mkdtemp(prefix="roost-test-machome-"))
    mac_backups = Path(tempfile.mkdtemp(prefix="roost-test-macbackups-"))
    mobile_dir = Path(tempfile.mkdtemp(prefix="roost-test-mobile-"))
    _mac_dirs.extend([mac_home, mac_backups, mobile_dir])

    env_overrides = {
        "ROOST_MAC_HOME": str(mac_home),
        "ROOST_MAC_BACKUPS_DIR": str(mac_backups),
        "ROOST_MOBILE_DIR": str(mobile_dir),   # never the real ~/Roost/mobile
        _DATA_DIR_ENV: str(_data_dir),
        _DESKS_DIR_ENV: str(_desks_dir),
        "ROOST_MODEL": "scripted",
        "ROOST_DESK": "fake",
        "ROOST_VOICE": "fake",   # never the Mac's real voice service on 18804
        "ROOST_STEER_DEBOUNCE_SECONDS": "0",   # steer: no burst wait in tests (a test that wants one passes it)
        "ROOST_TIMEZONE": "Europe/Madrid",     # the zone the suite was written in (a test that wants another sets it)
    }
    _original_env = {var: os.environ.get(var) for var in _ENV_OVERRIDE_VARS}
    os.environ.update(env_overrides)

    # Imported here, not at module level: this call must happen AFTER the
    # env override above, exactly like the belt-and-suspenders check it
    # performs requires.
    from roost.config import load_config

    violation = check_data_isolation(_data_dir, _desks_dir, load_config=load_config)
    if violation is None:
        violation = check_mac_home(load_config(), Path.home())
    if violation is not None:
        pytest.exit(
            f"TRIPWIRE: {violation} Refusing to run any tests — this should "
            "be structurally impossible; investigate why the env override "
            "above was bypassed before running anything else.",
            returncode=3,
        )


@pytest.fixture(scope="session", autouse=True)
def _enforce_test_data_isolation():
    """Yield the throwaway dirs set up by ``pytest_configure``, then clean up.

    The actual repoint + tripwire check already ran in ``pytest_configure``
    (see above) before this fixture — or any test — ever executes; this
    fixture only provides the dirs to tests that want them and tears down
    afterward.
    """
    assert _data_dir is not None and _desks_dir is not None, (
        "pytest_configure should have set these before any fixture runs"
    )

    try:
        yield (_data_dir, _desks_dir)
    finally:
        # Release any pooled aiosqlite connections opened against the
        # throwaway dirs before pytest tears them down.
        try:
            import asyncio

            from roost.db.connection import close_pool

            asyncio.run(close_pool())
        except Exception:
            pass

        for var, value in _original_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

        shutil.rmtree(_data_dir, ignore_errors=True)
        shutil.rmtree(_desks_dir, ignore_errors=True)
        for mac_dir in _mac_dirs:
            shutil.rmtree(mac_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
async def _fresh_data_dir_per_test(tmp_path, monkeypatch):
    """Give every test FUNCTION its own throwaway data dir.

    The session-scoped tripwire above repoints ``ROOST_DATA_DIR`` /
    ``ROOST_DESKS_DIR`` once for the whole run — enough to guarantee tests
    never touch real data, but not enough for isolation BETWEEN tests:
    code that calls ``load_config()`` with no explicit override (the
    gateway app factory, and contract tests like ``test_auth_api.py`` /
    ``test_db.py`` that call it directly) would then all share ONE
    on-disk SQLite file for the entire session. Two tests in the same
    module both registering "the first user" would collide — the second
    would see a database the first one already populated.

    ``monkeypatch.setenv`` auto-reverts at teardown, so this only shadows
    the session-wide dirs for the duration of one test function.
    ``close_pool()`` after each test releases the pooled connection this
    test's config key opened, so a later test that happens to reuse a
    path (it won't, ``tmp_path`` is unique per test, but connection pool
    entries are keyed by path string and best released promptly) never
    inherits a stale handle.
    """
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ROOST_DESKS_DIR", str(tmp_path / "desks"))
    yield
    await close_pool()


@pytest.fixture(autouse=True)
def _no_account_time_zone():
    """The install's zone is process-wide: every test starts and ends with no account zone held (so ROOST_TIMEZONE,
    Madrid, rules), whatever an earlier test's ``PUT /api/auth/timezone`` or ``set_local_tz`` left behind."""
    from roost.timezones import set_local_tz

    set_local_tz(None)
    yield
    set_local_tz(None)


_REAL_POSIX_SPAWN = os.posix_spawn


def _no_real_brave(path, *args, **kwargs):
    """Tests must never open the real Brave app on the user's screen."""
    if "Brave Browser" in str(path):
        raise RuntimeError("A test tried to start the real Brave app; pass a fake spawner instead.")
    return _REAL_POSIX_SPAWN(path, *args, **kwargs)


@pytest.fixture(autouse=True)
def _never_spawn_real_brave(monkeypatch):
    """Tripwire: a keeper built without a fake spawner would open real Brave windows (seen 2026-10-21)."""
    monkeypatch.setattr(os, "posix_spawn", _no_real_brave)
