"""Tests for ``roost.keeper.paths`` — desk directory resolution.

A bot id is attacker-reachable surface (it round-trips through a URL path
segment), so every helper here must refuse to resolve outside
``desks_dir`` no matter what string is handed in, not just reject-at-the-API
layer (see ``tests/test_keeper_auth.py`` for the HTTP-level 400).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from roost.keeper.paths import (
    BotIdOutsideDesksDir,
    browser_dir,
    desk_dir,
    downloads_dir,
    workspace_dir,
)


def test_desk_dir_for_a_normal_id_lands_inside_desks_dir(tmp_path: Path):
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()
    result = desk_dir(desks_dir, "11111111-1111-4111-8111-111111111111")
    assert result == (desks_dir / "11111111-1111-4111-8111-111111111111").resolve()


def test_desk_dir_rejects_traversal_outside_desks_dir(tmp_path: Path):
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()
    with pytest.raises(BotIdOutsideDesksDir):
        desk_dir(desks_dir, "../../etc")


def test_desk_dir_rejects_absolute_path_escape(tmp_path: Path):
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()
    with pytest.raises(BotIdOutsideDesksDir):
        desk_dir(desks_dir, "/etc/passwd")


def test_browser_downloads_workspace_dirs_are_subdirs_of_desk_dir(tmp_path: Path):
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()
    bot_id = "22222222-2222-4222-8222-222222222222"
    base = desk_dir(desks_dir, bot_id)
    assert browser_dir(desks_dir, bot_id) == base / "browser"
    assert downloads_dir(desks_dir, bot_id) == base / "downloads"
    assert workspace_dir(desks_dir, bot_id) == base / "workspace"


def test_browser_dir_also_rejects_traversal(tmp_path: Path):
    desks_dir = tmp_path / "desks"
    desks_dir.mkdir()
    with pytest.raises(BotIdOutsideDesksDir):
        browser_dir(desks_dir, "../../../tmp")
