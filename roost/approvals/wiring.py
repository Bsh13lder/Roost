"""What ``TurnRunner`` needs to run in approval modes, in one value (``approvals=None``: today's verdicts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore

if TYPE_CHECKING:
    from roost.mac.grant_service import GrantService
    from roost.mac.limits import MacLimits


@dataclass(frozen=True)
class ApprovalWiring:
    store: ApprovalStore
    sessions: SessionOks
    limits: "MacLimits | None" = None
    grants: "GrantService | None" = None   # the bot's Mac folders for its instructions
