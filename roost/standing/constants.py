"""Standing permission limits and the model check's fixed values (one place, no magic numbers elsewhere)."""

from __future__ import annotations

# The actions a standing permission may name: from the hard floor's committing kinds. Never spend, delete,
# account, secret, contact, new site or password: those always ask.
STANDING_ACTIONS: tuple[str, ...] = ("post", "send", "submit")
STANDING_MAX_PER_DAY_MAX = 20
STANDING_UNTIL_MAX_DAYS = 30           # the end date is at most this many local days ahead
STANDING_PER_ROUTINE_MAX = 3           # live permissions on one routine
STANDING_HOST_MAX = 253
# Words of the commit lexicon's "send" class that put something up in public: those acts are "post"; the rest of
# the class (send, message, reply, invite…) is "send".
STANDING_POST_WORDS: tuple[str, ...] = (
    "post", "publish", "share", "tweet", "comment", "publicar", "compartir", "comentar",
)

# Step 3: the model check.
STANDING_CHECK_AGENT = "standing-check"
STANDING_CHECK_TIMEOUT_S = 30.0
STANDING_CHECK_TYPED_CHARS = 200       # how much of the typed text the check sees
STANDING_CHECK_INSTRUCTIONS_CHARS = 4000
STANDING_CHECK_LABEL_CHARS = 200
STANDING_CHECK_FITS = "fits"
