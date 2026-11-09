"""The test suite can never open the real Brave app (it did once, from a keeper fixture)."""

from __future__ import annotations

import os

import pytest

from roost.keeper.browsers import BraveLauncher


def test_a_launcher_without_a_fake_spawner_cannot_open_real_brave(tmp_path):
    from roost.config import RoostConfig
    config = RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "d", desks_dir=tmp_path / "k",
                         keeper_secret="y" * 32)
    launcher = BraveLauncher(config)
    with pytest.raises(RuntimeError, match="real Brave"):
        launcher._spawn("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", [], os.environ)
