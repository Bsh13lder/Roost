"""Why the screen loop refused an act before the gate judged it, as a short fixed key for the audit row.

Owner, 2026-11-04: every such row said ``loop_refused`` and nothing more, so a checkbox that failed ten times left
no trace of why. The key is read from Roost's own refusal sentence (its words before any ``{field}``), never from
anything the page or the model wrote, so no typed text or label can reach the audit through it."""

from __future__ import annotations

from roost.computer_use import session
from roost.computer_use import texts
from roost.computer_use.desktop import IN_BROWSER_TEXT

OTHER = "other"

_SENTENCES: tuple[tuple[str, str], ...] = (
    ("look_first", session.LOOK_FIRST_TEXT),
    ("taken", session.TAKEN_TEXT),
    ("one_action", session.ONE_ACTION_TEXT),
    ("budget", session.BUDGET_TEXT),
    ("busy", session.BUSY_TEXT),
    ("miss", texts.MISS_TEXT),
    ("covered", texts.COVERED_TEXT),
    ("miss_point", texts.POINT_MISS_TEXT),
    ("no_mark", texts.NO_MARK_TEXT),
    ("stale_mark", texts.STALE_MARK_TEXT),
    ("held", texts.HELD_TEXT),
    ("asleep", texts.ASLEEP_TEXT),
    ("woke", texts.WOKE_LOOK_FIRST_TEXT),
    ("no_screen", texts.NO_SCREEN_TEXT),
    ("guards", texts.GUARDS_TEXT),
    ("bad_args", texts.BAD_ARGS_TEXT),
    ("browser_silent", texts.BROWSER_SILENT_TEXT),
    ("in_browser", IN_BROWSER_TEXT),
)


def _lead(sentence: str) -> str:
    return sentence.split("{", 1)[0]


def refusal_key(text: str) -> str:
    """The key of the refusal sentence ``text`` starts with; ``other`` for one this table doesn't know."""
    return next((key for key, sentence in _SENTENCES if _lead(sentence) and text.startswith(_lead(sentence))),
                OTHER)
