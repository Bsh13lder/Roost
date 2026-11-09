"""Grants held in the keeper's memory (Task 4; Review Focus b2, b6) and the tripwire for the real home."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from roost.config import RoostConfig
from roost.dev_guards import check_mac_home
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.grants import GrantRegistry, KeeperGrant

BOT_A = "11111111-1111-4111-8111-111111111111"
BOT_B = "22222222-2222-4222-8222-222222222222"


def _grant(folder: Path, grant_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", bot_id: str | None = None) -> KeeperGrant:
    st = folder.stat()
    return KeeperGrant(grant_id, str(folder), "read_write", bot_id, st.st_dev, st.st_ino)


def _code(call) -> str:
    with pytest.raises(MacFsError) as err:
        call()
    return err.value.code


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    one, two = tmp_path.resolve() / "one", tmp_path.resolve() / "two"
    one.mkdir()
    two.mkdir()
    return one, two


def test_no_grants_before_the_first_push_is_grants_unset() -> None:
    assert _code(lambda: GrantRegistry().lookup("x", BOT_A)) == "grants_unset"


def test_grants_swap_atomically_and_a_revoked_id_is_refused(folders) -> None:
    one, two = folders
    first, second = _grant(one, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), _grant(two, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    registry = GrantRegistry()
    generation = registry.generation
    registry.replace((first, second))
    assert registry.generation == generation + 1
    assert registry.lookup(first.grant_id, BOT_A) == first
    registry.replace((second,))
    assert registry.generation == generation + 2
    assert _code(lambda: registry.lookup(first.grant_id, BOT_A)) == "no_grant"
    assert registry.lookup(second.grant_id, BOT_B) == second
    assert _code(lambda: registry.lookup("not-a-grant", BOT_A)) == "no_grant"
    registry.replace(())
    assert _code(lambda: registry.lookup(second.grant_id, BOT_A)) == "no_grant"


def test_a_grant_for_one_bot_refuses_another(folders) -> None:
    one, _ = folders
    mine = _grant(one, bot_id=BOT_A)
    registry = GrantRegistry()
    registry.replace((mine,))
    assert registry.lookup(mine.grant_id, BOT_A) == mine
    assert _code(lambda: registry.lookup(mine.grant_id, BOT_B)) == "no_grant"


def test_the_grant_root_replaced_by_another_folder_is_refused(folders) -> None:
    one, _ = folders
    grant = _grant(one)
    registry = GrantRegistry(home=str(one.parent))
    registry.replace((grant,))
    fd = registry.open_root(grant)
    os.close(fd)
    one.rename(one.parent / "one-moved")
    one.mkdir()                                       # a different folder now stands at the same path
    assert _code(lambda: registry.open_root(grant)) == "no_grant"
    one.rmdir()
    assert _code(lambda: registry.open_root(grant)) == "not_found"
    (one.parent / "target").mkdir()
    one.symlink_to(one.parent / "target")             # a link in its place is not followed
    assert _code(lambda: registry.open_root(grant)) == "off_limits"


def test_the_tripwire_refuses_the_real_home(tmp_path: Path) -> None:
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    safe = tmp_path / "fake-home"
    safe.mkdir()
    base = dict(server_secret="s" * 32, database_dir=tmp_path / "d", desks_dir=tmp_path / "k", keeper_secret="k" * 32)
    assert check_mac_home(RoostConfig(**base, mac_home=real_home, mac_backups_dir=tmp_path / "b"), real_home)
    assert check_mac_home(RoostConfig(**base, mac_home=safe, mac_backups_dir=tmp_path / "b"), real_home) is None
    inside_real = (tmp_path / "Roost" / "mac-backups")
    assert check_mac_home(
        RoostConfig(**base, mac_home=safe, mac_backups_dir=inside_real), real_home, real_dirs=(tmp_path / "Roost",)
    )
