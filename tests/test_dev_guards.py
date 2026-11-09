"""Unit tests for the pure data-isolation check used by the tripwire.

``roost.dev_guards`` holds logic shared by two things:
  - ``tests/conftest.py``'s real session tripwire (this is the production
    use — see ``tests/test_tripwire.py`` for the whole-session sanity
    check that it actually ran).
  - ``tests/test_tripwire_exit.py``'s end-to-end ``pytester`` proof that
    violating either check really exits a pytest session with code 3.

These tests exercise the pure decision function directly: given explicit
directories and an injected ``load_config``, does it correctly detect (a)
a forbidden basetemp and (b) an ignored env override, and correctly pass
when neither applies?
"""

from __future__ import annotations

from types import SimpleNamespace

from roost.dev_guards import check_data_isolation, is_inside_any


def test_is_inside_any_detects_nested_path(tmp_path):
    real = tmp_path / "real"
    nested = real / "nested" / "deep"
    nested.mkdir(parents=True)
    assert is_inside_any(nested, (real,))


def test_is_inside_any_detects_exact_match(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    assert is_inside_any(real, (real,))


def test_is_inside_any_rejects_unrelated_path(tmp_path):
    real = tmp_path / "real"
    other = tmp_path / "other"
    real.mkdir()
    other.mkdir()
    assert not is_inside_any(other, (real,))


def test_check_data_isolation_passes_when_cfg_matches(tmp_path):
    data_dir = tmp_path / "data"
    desks_dir = tmp_path / "desks"
    data_dir.mkdir()
    desks_dir.mkdir()

    cfg = SimpleNamespace(database_dir=data_dir, desks_dir=desks_dir)

    violation = check_data_isolation(
        data_dir,
        desks_dir,
        load_config=lambda: cfg,
        real_dirs=(tmp_path / "forbidden",),
    )
    assert violation is None


def test_check_data_isolation_flags_forbidden_basetemp(tmp_path):
    # The throwaway dir itself resolves inside a "real" directory — this
    # must be caught WITHOUT even needing to call load_config().
    forbidden = tmp_path / "forbidden"
    inside = forbidden / "data"
    inside.mkdir(parents=True)

    def _unreachable():
        raise AssertionError(
            "load_config should not be called when the basetemp itself "
            "is already inside a forbidden directory"
        )

    violation = check_data_isolation(
        inside, inside, load_config=_unreachable, real_dirs=(forbidden,)
    )
    assert violation is not None
    assert "real data directory" in violation


def test_check_data_isolation_flags_ignored_override(tmp_path):
    # The basetemp dirs are fine, but load_config() — called AFTER the env
    # override — resolves somewhere else entirely, as if a later refactor
    # stopped honoring ROOST_DATA_DIR/ROOST_DESKS_DIR.
    data_dir = tmp_path / "data"
    desks_dir = tmp_path / "desks"
    data_dir.mkdir()
    desks_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    stale_cfg = SimpleNamespace(database_dir=elsewhere, desks_dir=desks_dir)

    violation = check_data_isolation(
        data_dir,
        desks_dir,
        load_config=lambda: stale_cfg,
        real_dirs=(tmp_path / "forbidden",),
    )
    assert violation is not None
    assert "not honored" in violation


def test_check_data_isolation_flags_cfg_resolving_into_real_dir(tmp_path):
    # The basetemp dirs are fine and load_config() "honors" the override
    # literally, but the resolved cfg dir itself turns out to sit inside a
    # real data directory (e.g. a symlinked tmp root) — still a violation.
    forbidden = tmp_path / "forbidden"
    forbidden.mkdir()
    data_dir = forbidden / "data"
    data_dir.mkdir()
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()

    cfg = SimpleNamespace(database_dir=data_dir, desks_dir=desks_dir)

    violation = check_data_isolation(
        data_dir, desks_dir, load_config=lambda: cfg, real_dirs=(forbidden,)
    )
    assert violation is not None
