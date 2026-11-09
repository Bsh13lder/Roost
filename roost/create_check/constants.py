"""The fixed values of the create check: one place, no magic numbers elsewhere."""

from __future__ import annotations

from roost.constants import MAX_BOT_INSTRUCTIONS_LENGTH

CREATE_CHECK_AGENT = "create-bot-check"
CREATE_CHECK_TIMEOUT_S = 30.0
CREATE_CHECK_FITS = "fits"                          # the one reply that lets the bot be created
CREATE_CHECK_MESSAGES = 3                           # your newest own, untainted messages in this chat
CREATE_CHECK_WORDS_CHARS = 500                      # each of them, as the check reads it
CREATE_CHECK_LABEL_CHARS = 200                      # the name, job and role
CREATE_CHECK_INSTRUCTIONS_CHARS = MAX_BOT_INSTRUCTIONS_LENGTH   # all of it: the check never judges a part
CREATE_CHECK_MARK = "checked"                       # the created card's field: the web and phone say "Auto-checked"
