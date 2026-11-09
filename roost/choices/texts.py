"""Every sentence the options card shows or tells a bot, in one place."""

from __future__ import annotations

from typing import Final

CHOICE_PARKED_TEXT: Final = (
    "Waiting for the user's choice. Stop here and say in one short line what you asked; "
    "you carry on after they answer."
)
ALREADY_DECIDED_TEXT: Final = "Already decided on {date}: {answer}. Go on with that."
CHOICE_NOT_HERE_TEXT: Final = (
    "Not asked: nobody can choose here. Go on with the safe option ({safe}) and say so"
)
NOTE_QUESTION_CLAUSE: Final = ", or note it with note_question"
BAD_CHOICE_ARGS_TEXT: Final = (
    "Not asked: give one question, 2 to 4 short options and the number of the safe one (starting at 0)."
)
PICK_LINE: Final = "{answer}"
OWN_LINE: Final = "{answer}"
DISMISS_LINE: Final = "No thanks: {question} Go on without it, and don't ask again."
DISMISSED_ANSWER: Final = "No (dismissed)"
CHOICE_OUT_OF_RANGE_TEXT: Final = "Pick one of the options shown."
OWN_NOT_OFFERED_TEXT: Final = "This card has no field for your own answer."
OWN_NEEDS_TEXT: Final = "Type your answer in 1 to 1000 characters."
