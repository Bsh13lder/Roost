"""End-to-end proof that violating the tripwire really exits with code 3.

``tests/conftest.py``'s ``pytest_configure`` calls
``roost.dev_guards.check_data_isolation`` and, on a violation, calls
``pytest.exit(..., returncode=3)``. Calling the real ``pytest.exit()``
inside THIS test process would kill the actual outer test run, so this
uses the ``pytester`` fixture to spin up an isolated, nested pytest
session (its own throwaway rootdir, no access to this repo's
``tests/conftest.py``) whose own tiny ``conftest.py`` forces each of the
two violation branches and then asserts the nested session's exit code.

This exercises the real ``check_data_isolation`` function (imported from
the installed ``roost`` package, not reimplemented here) so the two test
cases below are proof of the actual contract, not of a lookalike.
"""

from __future__ import annotations

import textwrap

import pytest


def test_forbidden_basetemp_exits_3(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        textwrap.dedent(
            """
            import pytest
            from pathlib import Path

            from roost.dev_guards import check_data_isolation

            def pytest_configure(config):
                # Simulated forbidden basetemp: the throwaway dir itself
                # resolves inside a "real" directory.
                forbidden = Path(config.rootpath) / "real"
                inside = forbidden / "data"
                inside.mkdir(parents=True)

                def _unreachable():
                    raise AssertionError("load_config must not be called here")

                violation = check_data_isolation(
                    inside, inside, load_config=_unreachable, real_dirs=(forbidden,)
                )
                if violation is not None:
                    pytest.exit(f"TRIPWIRE: {violation}", returncode=3)
            """
        )
    )
    pytester.makepyfile("def test_never_runs(): assert False")

    result = pytester.runpytest_subprocess()

    assert result.ret == 3


def test_ignored_override_exits_3(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        textwrap.dedent(
            """
            import pytest
            from pathlib import Path
            from types import SimpleNamespace

            from roost.dev_guards import check_data_isolation

            def pytest_configure(config):
                data_dir = Path(config.rootpath) / "throwaway-data"
                desks_dir = Path(config.rootpath) / "throwaway-desks"
                elsewhere = Path(config.rootpath) / "elsewhere"
                data_dir.mkdir()
                desks_dir.mkdir()
                elsewhere.mkdir()

                # Simulated ignored override: load_config() resolves
                # database_dir somewhere else entirely, as if a later
                # refactor stopped honoring ROOST_DATA_DIR.
                stale_cfg = SimpleNamespace(database_dir=elsewhere, desks_dir=desks_dir)

                violation = check_data_isolation(
                    data_dir,
                    desks_dir,
                    load_config=lambda: stale_cfg,
                    real_dirs=(Path(config.rootpath) / "unrelated-real-dir",),
                )
                if violation is not None:
                    pytest.exit(f"TRIPWIRE: {violation}", returncode=3)
            """
        )
    )
    pytester.makepyfile("def test_never_runs(): assert False")

    result = pytester.runpytest_subprocess()

    assert result.ret == 3
