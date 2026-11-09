"""``RunCounter``: how many connector calls each run made, in memory (at most ``CONNECTOR_CALLS_PER_RUN``).

The newest ``CONNECTOR_RUNS_TRACKED`` runs are kept; older ones are forgotten. A call with no run id (an approved
card's step) is not counted: the user's Yes is its own limit."""

from __future__ import annotations

from roost.constants import CONNECTOR_CALLS_PER_RUN, CONNECTOR_RUNS_TRACKED


class RunCounter:
    def __init__(self, limit: int = CONNECTOR_CALLS_PER_RUN, tracked: int = CONNECTOR_RUNS_TRACKED) -> None:
        self._limit, self._tracked = limit, tracked
        self._counts: dict[str, int] = {}

    def take(self, run_id: str | None) -> bool:
        """Count one call for ``run_id``; False when the run already made ``limit`` calls."""
        if run_id is None:
            return True
        used = self._counts.get(run_id, 0)
        if used >= self._limit:
            return False
        kept = {k: v for k, v in self._counts.items() if k != run_id}
        if len(kept) >= self._tracked:
            kept = dict(list(kept.items())[len(kept) - self._tracked + 1:])
        self._counts = {**kept, run_id: used + 1}
        return True
