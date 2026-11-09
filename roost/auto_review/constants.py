"""The fixed values of auto-review: one place, no magic numbers elsewhere."""

from __future__ import annotations

AUTO_REVIEW_AGENT = "auto-review-check"
AUTO_REVIEW_TIMEOUT_S = 30.0
AUTO_REVIEW_SAFE = "safe"                     # the one reply that lets an act run
AUTO_REVIEW_REQUEST_CHARS = 800               # your request, as the reviewer reads it (its newest end)
AUTO_REVIEW_LABEL_CHARS = 200                 # every other field
AUTO_REVIEW_CLASS = "unknown"                 # a button Roost can't read
# Owner, 2026-11-05 ("buy me tickets: only one question, the payment"): in your own chat, Full auto also checks a
# send, submit or accept against what you asked. Paying, deleting and account changes always keep their card.
AUTO_REVIEW_ASKED_CLASSES: frozenset[str] = frozenset({"send", "submit", "accept"})
AUTO_REVIEW_REQUEST_MESSAGES = 3              # your newest own messages the reviewer reads
AUTO_REVIEW_TOOLS: tuple[str, ...] = ("click", "press_key")   # never typing
AUTO_REVIEW_MARK = "(auto-checked)"           # the chat's step line of an act the reviewer let run
AUTO_REVIEW_IMAGE_TYPE = "image/jpeg"
