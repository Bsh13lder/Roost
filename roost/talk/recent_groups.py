"""The tool groups a thread's last runs used (keeping the cache warm, docs/plans/2026-11-09-roost-tool-groups.md §4).

A group loaded in the middle of a run changes the tool list, so that step reads no prompt cache. A bot that browsed
in its last run will most likely browse again, so the groups its thread's last ``RECENT_GROUP_RUNS`` runs actually
called tools from start loaded in the next run (``start_groups``). Nothing is stored: the map lives on the runner,
holds at most ``RECENT_GROUP_THREADS`` threads (the oldest touched is dropped first) and starts empty at boot."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from roost.constants import RECENT_GROUP_RUNS, RECENT_GROUP_THREADS

Runs = tuple[frozenset[str], ...]


@dataclass(frozen=True)
class RecentGroups:
    """Per thread, the groups of its newest runs (oldest first). ``noted`` returns a new map."""

    _threads: Mapping[str, Runs] = field(default_factory=lambda: MappingProxyType({}))

    def for_thread(self, thread_id: str) -> Runs:
        return self._threads.get(thread_id, ())

    def noted(self, thread_id: str, groups: frozenset[str]) -> "RecentGroups":
        """The map with ``groups`` as ``thread_id``'s newest run, that thread moved to the newest place."""
        runs = (*self.for_thread(thread_id), groups)[-RECENT_GROUP_RUNS:]
        others = tuple((k, v) for k, v in self._threads.items() if k != thread_id)
        kept = (*others, (thread_id, runs))[-RECENT_GROUP_THREADS:]
        return RecentGroups(MappingProxyType(dict(kept)))
