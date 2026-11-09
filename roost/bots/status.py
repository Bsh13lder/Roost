"""``ActivityBoard`` — in-memory, per-process "what is this bot doing
right now" line.

Deliberately NOT persisted and NOT encrypted: it's a volatile status
string (e.g. "reading your inbox...") that later tasks' Talk runner sets
while a turn is in flight, surfaced as ``BotOut.activity``
(``roost/bots/service.py``). A gateway restart loses it the same way it
loses an in-flight turn — and ``BotStore.reset_on_boot`` already moves
every such bot back to ``resting`` on boot, so a stale activity line
never outlives the status that explained it.

One instance lives on ``app.state.activity_board`` per gateway app
(``roost/gateway/app.py``), same lifetime rule as ``BotStore`` and the
auth rate limiters: constructed fresh per ``create_app()`` call, never a
module-level global shared across app instances/tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Activity:
    text: str
    tainted: bool = False   # written by a run that had read outside content


class ActivityBoard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._activity: dict[str, Activity] = {}

    def set(self, bot_id: str, text: str | None, *, tainted: bool = False) -> None:
        """Set the bot's current activity line, or clear it with ``None``."""
        with self._lock:
            if text is None:
                self._activity.pop(bot_id, None)
            else:
                self._activity[bot_id] = Activity(text, tainted)

    def entry(self, bot_id: str) -> Activity | None:
        """The line and its taint, for another bot's ``list_bots``."""
        with self._lock:
            return self._activity.get(bot_id)

    def get(self, bot_id: str) -> str | None:
        """The bot's current activity line (the user's own UI shows it), or ``None``."""
        with self._lock:
            found = self._activity.get(bot_id)
            return found.text if found else None


# Spec §7.4's words for a bot's status, keyed by BotStatus value.
STATUS_LABELS: Mapping[str, str] = MappingProxyType({
    "resting": "Resting", "on_it": "On it", "asking_you": "Asking you", "stuck": "Stuck", "off_duty": "Off duty",
})
