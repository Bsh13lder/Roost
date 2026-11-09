"""``CuOutcome``: what one screen call hands back to ``ToolRunner`` (``roost/computer_use/runner.py``)."""

from __future__ import annotations

from dataclasses import dataclass

from roost.approvals.models import PendingCall
from roost.desk.stuck import Block


@dataclass(frozen=True)
class CuOutcome:
    """What one screen call hands back to ``ToolRunner``."""

    text: str
    parked: PendingCall | None = None   # an act that asks: the run stops after this step
    block: Block | None = None          # a look that met a block, a second miss or a spent budget
    url: str = ""                       # the page address after this call, "" when unknown
    looked: bool = False                # the page's content reached the model (taints the run)
