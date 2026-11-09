"""``PlanDraft``: the steps a Review-first (plan mode) run has collected so far. Frozen: ``add`` returns a new draft."""

from __future__ import annotations

from dataclasses import dataclass

from roost.approvals.models import PendingCall


@dataclass(frozen=True)
class PlanDraft:
    steps: tuple[PendingCall, ...] = ()

    def add(self, step: PendingCall) -> "PlanDraft":
        return PlanDraft((*self.steps, step))
