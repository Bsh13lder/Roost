"""Every sentence the instructions card says, to a bot or to the user, in one place."""

from __future__ import annotations

from roost.constants import INSTRUCTION_SECTIONS, INSTRUCTION_WHY_MAX, MAX_BOT_INSTRUCTIONS_LENGTH

ASKED = ("Asked the user to update your instructions. They change only after the user presses Accept; until then "
         "keep working with the ones you have.")
NO_CHANGE = "Those are already your instructions."
TOO_MANY_OPEN = "Your last instructions card is still waiting for the user."
STALE = "Your bot's instructions changed since this card was made, so it no longer fits."
NOT_OPEN = "Try again: that card was already decided."
NO_CHAT = "There is no chat to show the card in."
NO_SUCH_BOT = "No such bot."
SECRET = "New instructions can't hold {kinds}."
BAD_ARGS = (f"Refused: propose_instructions_update needs new_text (your full new instructions, up to "
            f"{MAX_BOT_INSTRUCTIONS_LENGTH} characters) and why (one line, up to {INSTRUCTION_WHY_MAX}).")
ACTIVITY = "offering new instructions"
PROPOSAL_NOT_FOUND = "Instructions card not found"

# update_my_instructions (A2): a direct change in your own chat, with an Undo line.
CHANGE_NOT_HERE = ("you change your own instructions directly only in the user's own chat, in a run their own "
                   "message started. Use propose_instructions_update to offer the change on a card instead.")
CHANGE_TAINTED = f"Refused: {CHANGE_NOT_HERE}"
CHANGE_BAD_ARGS = (f"Refused: update_my_instructions needs section (one of: {', '.join(INSTRUCTION_SECTIONS)}), "
                   f"new_text (that section's full new text, up to {MAX_BOT_INSTRUCTIONS_LENGTH} characters) and "
                   f"why (one line, up to {INSTRUCTION_WHY_MAX}).")
CHANGE_TOO_LONG = f"Your instructions can't be longer than {MAX_BOT_INSTRUCTIONS_LENGTH} characters."
CHANGE_ACTIVITY = "updating my instructions"
UNDO_SPENT = "That change was already undone."
CHANGED_SINCE = "Your bot's instructions changed since, so nothing was undone."
CHANGE_NOT_FOUND = "Change not found"


def change_line(section: str) -> str:
    """The chat line (and its preview): "Updated my instructions: Tone"."""
    return f"Updated my instructions: {section}"


def change_done(section: str) -> str:
    """The tool's result for the model."""
    return (f"Updated your instructions: {section}. The user sees it in the chat and can Undo it; the new text "
            "applies from your next run.")
