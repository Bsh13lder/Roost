"""Tests for the desk keeper's launchd agent plist — ``roost/keeper/launchd.py``.

``make desk-keeper-install`` writes this plist to
``~/Library/LaunchAgents/app.roost.desk-keeper.plist`` and bootstraps it,
so the keeper runs all the time (RunAtLoad + KeepAlive) as the user, not
root. macOS TCC silently blocks launchd jobs from reading ``~/Desktop``,
so nothing the plist points at may live there, and launchd does no ``~``
expansion, so every path must already be absolute.

Every test passes a ``tmp_path``-based home (or points ``HOME`` at one) —
never the real home directory.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from roost.keeper import launchd


def _plist(home: Path) -> dict:
    return plistlib.loads(launchd.render_plist(home))


def _all_paths(plist: dict) -> list[str]:
    env = plist["EnvironmentVariables"]
    return [
        plist["ProgramArguments"][0],
        env["ROOST_DATA_DIR"],
        env["ROOST_DESKS_DIR"],
        plist["StandardOutPath"],
        plist["StandardErrorPath"],
    ]


def test_label_is_the_desk_keeper_label(tmp_path):
    assert launchd.LAUNCHD_LABEL == "app.roost.desk-keeper"
    assert _plist(tmp_path)["Label"] == "app.roost.desk-keeper"


def test_runs_the_keeper_module_from_the_roost_venv(tmp_path):
    args = _plist(tmp_path)["ProgramArguments"]
    assert args == [str(tmp_path / "Roost" / "venv" / "bin" / "python"), "-m", "roost.keeper"]


def test_environment_points_at_roost_data_and_desks(tmp_path):
    env = _plist(tmp_path)["EnvironmentVariables"]
    assert env["ROOST_DATA_DIR"] == str(tmp_path / "Roost" / "data")
    assert env["ROOST_DESKS_DIR"] == str(tmp_path / "Roost" / "desks")
    # docker (/usr/local/bin) must be reachable: the keeper shells out to it
    # for workspace containers, and launchd's own default PATH lacks it.
    assert env["PATH"] == "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"


def test_environment_never_sets_a_host_or_an_api_key(tmp_path):
    env = _plist(tmp_path)["EnvironmentVariables"]
    assert "ROOST_HOST" not in env
    assert "ROOST_IN_CONTAINER" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_starts_at_load_and_is_kept_alive(tmp_path):
    plist = _plist(tmp_path)
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True


def test_stdout_and_stderr_go_to_the_keeper_log(tmp_path):
    plist = _plist(tmp_path)
    log = str(tmp_path / "Roost" / "logs" / "keeper.log")
    assert plist["StandardOutPath"] == log
    assert plist["StandardErrorPath"] == log


def test_every_path_is_absolute_and_expanded(tmp_path):
    for p in _all_paths(_plist(tmp_path)):
        assert Path(p).is_absolute(), p
        assert "~" not in p, p


def test_nothing_points_under_desktop(tmp_path):
    for p in _all_paths(_plist(tmp_path)):
        assert "Desktop" not in Path(p).parts, p


def test_refuses_a_home_that_would_put_paths_under_desktop(tmp_path):
    with pytest.raises(ValueError, match="Desktop"):
        launchd.render_plist(tmp_path / "Desktop" / "someone")


def test_refuses_a_relative_home():
    with pytest.raises(ValueError, match="absolute"):
        launchd.render_plist(Path("relative/home"))


def test_write_plist_creates_a_readable_file(tmp_path):
    target = tmp_path / "LaunchAgents" / "app.roost.desk-keeper.plist"
    launchd.write_plist(target, tmp_path)
    assert plistlib.loads(target.read_bytes())["Label"] == "app.roost.desk-keeper"
    assert (target.stat().st_mode & 0o777) == 0o644


def test_write_plist_replaces_an_existing_file(tmp_path):
    target = tmp_path / "agent.plist"
    target.write_text("stale")
    launchd.write_plist(target, tmp_path)
    assert plistlib.loads(target.read_bytes())["Label"] == "app.roost.desk-keeper"


# ---------------------------------------------------------------------------
# CLI: python -m roost.keeper.launchd write <path>
# ---------------------------------------------------------------------------


def test_cli_write_uses_the_current_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "out.plist"
    assert launchd.main(["write", str(target)]) == 0
    plist = plistlib.loads(target.read_bytes())
    assert plist["ProgramArguments"][0] == str(tmp_path / "Roost" / "venv" / "bin" / "python")
    assert str(target) in capsys.readouterr().out


def test_cli_write_expands_a_tilde_target(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert launchd.main(["write", "~/agent.plist"]) == 0
    assert (tmp_path / "agent.plist").is_file()


@pytest.mark.parametrize("argv", [[], ["write"], ["write", "a", "b"], ["print", "x"]])
def test_cli_bad_usage_exits_2_with_usage(argv, capsys):
    assert launchd.main(argv) == 2
    assert "Usage" in capsys.readouterr().err


def test_cli_reports_a_desktop_home_as_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "Desktop"))
    assert launchd.main(["write", str(tmp_path / "out.plist")]) == 1
    assert "Desktop" in capsys.readouterr().err
    assert not (tmp_path / "out.plist").exists()
