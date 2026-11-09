"""The gate's verdict and the run context it judges by.

Kept apart from ``roost/talk/gate.py`` so the computer-use rules (``roost/computer_use/gate_rules.py``) can
build verdicts without importing the gate that calls them. ``roost.talk.gate`` re-exports every name here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from roost.approvals.models import ApprovalState
from roost.computer_use.fence import SiteFence
from roost.standing.models import StandingMatch
from roost.talk.link_scope import LinkScope

Decision = Literal["do", "never", "ask", "plan"]
Reason = Literal[
    "allowed", "tainted_create", "not_allowed", "link_not_trusted", "tainted_change", "tainted_create_cap",
    "tainted_refused", "approval_ask", "topic_asks", "hard_floor", "mac_read_asks", "planned", "auto_edit",
    "tainted_mac_edit", "needs_your_ok", "plan_full", "approved", "plan_accepted",
    "act_refused", "new_site",   # C3: a click or key the page side refuses; a link or form to a host off the fence
    "loop_refused",              # C3: the screen loop refused an act before the gate judged it (busy, look first…)
    "standing_ok",               # a routine's standing permission covers this hard-floor act (and the bot's model said fits)
    "owner_words",               # W2: your own message asked for this hard-floor act (and the bot's model said fits)
    "fresh_open",                # your own chat opens an address you didn't name (W6/W7, 2026-11-03)
    "owner_site",                # your own chat: a click or key goes to another site (the fence widens to it)
    "auto_review",               # Full auto: a button Roost can't read, in your own chat (and the bot's model said safe)
    "checked_create",            # a tainted create_bot in your own chat (and the bot's model said it fits your words)
    "owner_chat_change",         # a tainted change your own chat asked for: records, memories, routines, settings
    "owner_chat_act",            # your own chat: only paying asks (2026-11-05): sends, forms, your details, programs
]


@dataclass(frozen=True)
class GateContext:
    allowed: frozenset[str]
    tainted: bool = False
    creates: int = 0
    link_guard: LinkScope | None = None   # None: no link limit for this run
    approval: ApprovalState | None = None  # None: today's verdicts (every old rig)
    fence: SiteFence | None = None         # C3: the run's site fence; None: no Linux computer (acts are never)
    owner_chat: bool = False               # W6: a 1:1 run made only of your own messages (no routine, handoff, room)
    site_fresh: bool = False               # W7: that run has read no new outside content yet (opening sites only)
    check_model: str | None = None         # the bot's own model: a check that needs a model's judgement runs on it


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: Reason
    text: str | None = None
    url: str | None = None   # R3: the scope entry a guarded open_page opens instead of the model's string
    standing: StandingMatch | None = None   # standing_ok: the permission the gate re-checks and the model check judges
