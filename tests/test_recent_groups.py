"""Keeping the cache warm (docs/plans/2026-11-09-roost-tool-groups.md §4): the groups a thread's last few runs used
start loaded in its next run, from a bounded in-memory map on the runner."""

from __future__ import annotations

from roost.constants import RECENT_GROUP_RUNS, RECENT_GROUP_THREADS
from roost.talk.recent_groups import RecentGroups
from roost.talk.run_groups import start_groups


def test_a_thread_remembers_the_groups_of_its_last_runs_only():
    recent = RecentGroups()
    for i in range(RECENT_GROUP_RUNS + 2):
        recent = recent.noted("t1", frozenset({f"g{i}"}))
    kept = recent.for_thread("t1")
    assert len(kept) == RECENT_GROUP_RUNS
    assert kept[-1] == frozenset({f"g{RECENT_GROUP_RUNS + 1}"}) and frozenset({"g0"}) not in kept


def test_a_run_that_used_nothing_is_still_a_run():
    recent = RecentGroups().noted("t1", frozenset({"tasks"}))
    for _ in range(RECENT_GROUP_RUNS):
        recent = recent.noted("t1", frozenset())
    assert recent.for_thread("t1") == (frozenset(),) * RECENT_GROUP_RUNS


def test_noted_returns_a_new_map_and_leaves_the_old_one():
    first = RecentGroups()
    second = first.noted("t1", frozenset({"money"}))
    assert first.for_thread("t1") == () and second.for_thread("t1") == (frozenset({"money"}),)
    assert second.for_thread("t2") == ()


def test_the_map_is_bounded_by_threads_oldest_dropped():
    recent = RecentGroups()
    for i in range(RECENT_GROUP_THREADS + 5):
        recent = recent.noted(f"t{i}", frozenset({"tasks"}))
    assert recent.for_thread("t0") == () and recent.for_thread("t4") == ()
    assert recent.for_thread("t5") == (frozenset({"tasks"}),)
    assert recent.for_thread(f"t{RECENT_GROUP_THREADS + 4}") == (frozenset({"tasks"}),)


def test_a_touched_thread_becomes_the_newest_again():
    recent = RecentGroups()
    for i in range(RECENT_GROUP_THREADS):
        recent = recent.noted(f"t{i}", frozenset())
    recent = recent.noted("t0", frozenset({"notes"})).noted("tx", frozenset())
    assert recent.for_thread("t0") == ((frozenset(), frozenset({"notes"}))) and recent.for_thread("t1") == ()


def test_start_groups_adds_the_recent_groups_to_the_words():
    groups = start_groups((), ("hello",), stuck_reply=False,
                          recent_groups=(frozenset({"computer"}), frozenset({"tasks"})))
    assert groups == frozenset({"computer", "tasks"})


def test_start_groups_with_groups_off_ignores_the_recent_ones(monkeypatch):
    monkeypatch.setenv("ROOST_TOOL_GROUPS", "off")
    assert start_groups((), (), stuck_reply=False, recent_groups=(frozenset({"tasks"}),)) is None
