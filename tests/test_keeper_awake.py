"""The keeper keeps the Mac from idle sleep while it runs (owner, 2026-10-23: Roost stays up)."""

from __future__ import annotations

from roost.keeper.awake import CAFFEINATE, awake_argv, keep_awake


def test_awake_argv_holds_idle_and_system_sleep_off_while_the_keeper_lives():
    assert awake_argv(4242) == [CAFFEINATE, "-i", "-s", "-w", "4242"]


def test_keep_awake_starts_caffeinate_detached_and_quiet():
    seen = {}

    def spawn(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return object()

    assert keep_awake(7, spawn=spawn) is not None
    assert seen["argv"] == awake_argv(7)
    assert seen["close_fds"] is True


def test_keep_awake_without_caffeinate_logs_and_carries_on(caplog):
    def spawn(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    assert keep_awake(7, spawn=spawn) is None
    assert "stay awake" in caplog.text
