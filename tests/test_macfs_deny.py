"""The keeper's deny list (Task 4; Review Focus b3): pure rules, judged on a fake home under tmp_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from roost.constants import MAC_DENY_ROOTS
from roost.keeper.macfs.deny import check_grant_root, is_denied_name, is_denied_path
from roost.keeper.macfs.errors import MacFsError


@pytest.fixture
def home(tmp_path: Path) -> str:
    folder = tmp_path.resolve() / "home"
    folder.mkdir()
    return str(folder)


def test_system_and_home_secrets_are_denied_at_any_depth(home: str) -> None:
    for root in MAC_DENY_ROOTS:
        assert is_denied_path(root, home)
        assert is_denied_path(f"{root}/deep/er/file.md", home)
    denied = [
        home,
        f"{home}/Library/Keychains/login.keychain-db",
        f"{home}/library/Preferences",                       # case-folded
        f"{home}/.ssh/id_rsa",
        f"{home}/.config/gh/hosts.yml",
        f"{home}/.Trash/old.md",
        f"{home}/Roost/data/roost.db",
        f"{home}/Roost/mac-backups/x",
        f"{home}/Desktop/Code_Projects/lazyclaw/data/x",
        f"{home}/Documents/../Library/x",                    # not normalised by the caller
        f"{home}/Documents/deep/er/prod.env/notes.md",
        "relative/path.md",
        "/somewhere/else/entirely.md",
        f"{home}/Documents/a\0b.md",
    ]
    for path in denied:
        assert is_denied_path(path, home), path
    for path in (f"{home}/Documents/notes.md", f"{home}/Desktop/Code_Projects/roost/README.md", f"{home}/Notes"):
        assert not is_denied_path(path, home), path


@pytest.mark.parametrize(
    "name",
    ["a.env", ".env", ".env.local", "k.pem", "k.KEY", "cert.p12", "id_rsa", "login.keychain-db",
     "Credentials.json", "credentials", "app.sqlite", "App.DB", ".ENV"],
)
def test_denied_names_anywhere(name: str) -> None:
    assert is_denied_name(name)


@pytest.mark.parametrize("name", ["notes.md", "environment.md", "idea.txt", "keys.md", "db.md"])
def test_ordinary_names_are_not_denied(name: str) -> None:
    assert not is_denied_name(name)


def test_a_grant_must_be_a_real_folder_under_home_not_home_itself(home: str) -> None:
    for bad in (home, f"{home}/Library", f"{home}/.ssh", "/tmp/elsewhere", "/etc", "relative", f"{home}/Roost"):
        with pytest.raises(MacFsError) as err:
            check_grant_root(bad, home)
        assert err.value.code == "off_limits"
    assert check_grant_root(f"{home}/Documents", home) is None


def test_a_grant_containing_a_denied_folder_is_allowed_and_hides_it(home: str) -> None:
    assert check_grant_root(f"{home}/Notes", home) is None
    assert is_denied_path(f"{home}/Notes/secrets.env", home)
    assert is_denied_path(f"{home}/Notes/sub/prod.env/x.md", home)
    assert not is_denied_path(f"{home}/Notes/sub/ok.md", home)


@pytest.mark.parametrize("folder", ["Roost-review", "roost-review", "ROOST-REVIEW", "Roost-Review"])
def test_roost_review_is_off_limits_in_any_case(home: str, folder: str) -> None:
    # list / read / find all judge the resolved path with is_denied_path; a grant is judged by check_grant_root.
    for path in (f"{home}/{folder}", f"{home}/{folder}/notes.md", f"{home}/{folder}/deep/er/x.md"):
        assert is_denied_path(path, home), path
    with pytest.raises(MacFsError) as err:
        check_grant_root(f"{home}/{folder}", home)
    assert err.value.code == "off_limits"
    assert not is_denied_path(f"{home}/Documents/{folder}-notes.md", home)


def test_the_stale_roost_data_path_is_gone_and_real_roost_data_is_still_denied(home: str) -> None:
    from roost.constants import MAC_DENY_HOME_PATHS

    assert "Desktop/Code_Projects/roost/data" not in MAC_DENY_HOME_PATHS
    assert is_denied_path(f"{home}/Roost/data/roost.db", home)
    assert is_denied_path(f"{home}/roost/DATA/roost.db", home)
