"""The fixed values of "your words count" (W1–W4): one place, no magic numbers elsewhere."""

from __future__ import annotations

# W1: a whole message that is only one of these answers the one Ask card waiting in the chat (normalised: casefold,
# accents and punctuation stripped, apostrophes dropped, so "Sí!" is "si" and "don't" is "dont").
OWNER_YES_WORDS: tuple[str, ...] = (
    "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "go", "go ahead", "do it", "yes do it", "ok do it",
    "okay do it", "yes please", "ok go", "yes go ahead",
    "si", "vale", "dale", "hazlo", "adelante", "si hazlo", "vale hazlo", "si adelante",
)
OWNER_NO_WORDS: tuple[str, ...] = (
    "no", "nope", "dont", "do not", "stop", "cancel", "no thanks", "no thank you", "dont do it",
    "no gracias", "no lo hagas", "para", "cancela",
)
OWNER_ANSWER_MAX_WORDS = 4
OWNER_ANSWER_MAX_CHARS = 40            # longer messages are never read as a plain yes or no

# W2: the quote an act may carry, and where it must come from.
OWNER_WORDS_MAX_CHARS = 500            # the owner_words argument's limit
OWNER_WORDS_MESSAGES_MAX = 3           # your newest own, untainted messages in this chat a quote may come from
OWNER_WORDS_MIN_WORDS = 3              # a shorter quote must be a whole message or line of yours
# The commit classes your words may cover at the hard floor (W3: never spend; owner 2026-11-03: account steps such as
# sign up, register, save changes and log out too, but never a password or email change, OWNER_WORDS_NEVER_WORDS).
OWNER_WORDS_CLASSES: tuple[str, ...] = ("send", "submit", "accept", "delete", "account")
# A control whose words name one of these (normalised: lower case, no accents) is never covered by your words.
OWNER_WORDS_NEVER_WORDS: tuple[str, ...] = ("password", "contrasena", "email", "e-mail", "correo", "passkey")

# W2: the check, on the bot's own model (owner, 2026-11-03).
OWNER_CHECK_AGENT = "owner-words-check"
OWNER_CHECK_TIMEOUT_S = 30.0
OWNER_CHECK_FITS = "fits"
OWNER_CHECK_TYPED_CHARS = 400
OWNER_CHECK_LABEL_CHARS = 200

# W10 (owner, 2026-10-31): a control you said Yes to on a card clicks again with no card while the page has not moved.
OWNER_AGAIN_WINDOW_S = 15 * 60          # how long a Yes covers the same control again
OWNER_AGAIN_CARDS_MAX = 10              # the newest approved cards in the chat that are read
OWNER_AGAIN_CLASSES: tuple[str, ...] = ("submit", "accept")   # never send, spend or delete: twice is twice
