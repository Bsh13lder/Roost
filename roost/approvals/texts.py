"""Every sentence and name the approval modes show or tell a bot, in one place.

Renaming a mode or the Plan card touches only
the user-facing names below; the wire values ("ask", "auto_edit", "plan") stay.
"""

from __future__ import annotations

from typing import Final

from roost.constants import APPROVAL_PLAN_MAX_STEPS

# User-facing names. The web reads the same three from web/src/components/approvals/constants.ts.
MODE_LABELS: Final = {"ask": "Ask every time", "auto_edit": "Auto-edit", "plan": "Review first"}
PLAN_CARD_NAME: Final = "Proposal"

PARKED_TEXT: Final = (
    "Waiting for the user's OK on this. Stop here and say in one short line what you asked; "
    "you carry on after they answer."
)
NOT_PERFORMED_TEXT: Final = "Not done: you are waiting for the user's OK on an earlier step."
PLANNED_TEXT: Final = (
    "Added to your plan as step {n}. Nothing changes until the user accepts the plan. "
    "When the plan is complete, say so in one short line."
)
PLAN_FULL_TEXT: Final = (
    f"Your plan already has {APPROVAL_PLAN_MAX_STEPS} steps. Finish it here; do the rest after the user accepts."
)
NEEDS_YOUR_OK_TEXT: Final = "Not done: this needs the user's OK, and I can ask only in my own chat with them."
EXPIRED_LINE: Final = "Replaced by a newer question."
YES_LINE: Final = "Yes: {title}"
YES_SESSION_LINE: Final = "Yes, for this session: {title}"
# Owner, 2026-10-31: a No is for that one time ("Don't do it" read as a standing rule to Gigs).
NO_LINE: Final = "No: {title}. Not this time; carry on without it."
# Owner, 2026-11-03: a Send card's Don't send stops the bot until you say what to change (Change it… says it at once).
SEND_NO_LINE: Final = "Don't send: {title}. Not sent. Wait for me to say what to change."
ACCEPT_LINE: Final = "I accepted your plan ({n} steps)."
DECLINE_LINE: Final = "I declined your plan. Nothing changed."
PLAN_WAITS_LINE: Final = "The plan waits until you answer."
EDIT_NEEDS_TEXT: Final = "Say what to change in 1 to 4000 characters."
STEP_FAILED_LINE: Final = "Step {n} didn't run: {reason} The steps after it didn't run either."
OUTSIDE_CONTENT_MARK: Final = "Based on outside content"
CANT_SHOW_TEXT: Final = "Not done: I can't show you everything this would do, so I won't ask. Make it simpler."
CARD_TOO_BIG_TEXT: Final = "Not done: that change is too big to show in one card. Make it smaller."
NOTHING_TO_DO_TEXT: Final = "Nothing was run."
APPROVED_FAILED_TEXT: Final = "It didn't run: {reason}"
BAD_ANSWER_TEXT: Final = "That answer doesn't fit this card."
SESSION_NOT_OFFERED_TEXT: Final = "Yes for this session is only for reads that offer it."
CARD_CLOSED_TEXT: Final = "Already answered."
CARD_NOT_FOUND_TEXT: Final = "Card not found"
NOT_ASKABLE_TEXT: Final = "Not done: this one can't wait on a card yet. Tell the user it needs them to do it themselves."
