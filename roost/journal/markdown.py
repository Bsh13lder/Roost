"""The Bot Journal's Markdown, pure: a day is an Obsidian daily note.

    ---
    tags: ["roost/journal", "bot/ana"]
    bot: "Ana"
    day: "2026-10-22"
    ---
    # Ana · 2026-10-22

    - 09:05 Added a task, saved a note
    - 14:19 Wrote the weekly report

Every entry is one line (``- HH:MM text``), so nothing an entry says can start front matter or a heading.
A run's line is built from its steps' activity words ("adding a task" -> "Added a task") with no model."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from typing import Iterable

from roost.constants import JOURNAL_ENTRY_MAX_CHARS, JOURNAL_RUN_LINE_MAX_STEPS
from roost.notes.text import fold
from roost.tags.rules import bot_tag, obsidian_tag

JOURNAL_TAG = "roost/journal"
EMPTY_ENTRY_TEXT = "A journal entry needs some text."
LONG_ENTRY_TEXT = f"A journal entry can be up to {JOURNAL_ENTRY_MAX_CHARS} characters."
_ENTRY = re.compile(r"^- \d{2}:\d{2} ")
_SPACE = re.compile(r"\s+")
# Every verb the gateway announces for a write step, in the past (web/src/lib/toolLines.ts keeps the same list).
PAST = {
    "adding": "added", "asking": "asked", "changing": "changed", "checking": "checked", "completing": "completed",
    "correcting": "corrected", "creating": "created", "deleting": "deleted", "editing": "edited", "filing": "filed",
    "forgetting": "forgot", "logging": "logged", "looking": "looked", "making": "made", "moving": "moved",
    "opening": "opened", "reading": "read", "renaming": "renamed", "saving": "saved", "searching": "searched",
    "sending": "sent", "setting": "set", "switching": "switched", "undoing": "undid", "updating": "updated",
    "waiting": "waited", "writing": "wrote",
}


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def new_day(bot_name: str, day: date) -> str:
    tags = [JOURNAL_TAG, obsidian_tag(bot_tag(bot_name, bot_name)) or "bot"]
    name = " ".join(bot_name.split()) or "Bot"
    return ("---\n"
            f"tags: [{', '.join(_quoted(tag) for tag in tags)}]\n"
            f"bot: {_quoted(name)}\n"
            f"day: {_quoted(day.isoformat())}\n"
            "---\n"
            f"# {name} · {day.isoformat()}\n")


def entry_text(text: str) -> str:
    """One trimmed line. ``ValueError`` (a plain sentence) when empty or too long."""
    line = _SPACE.sub(" ", text).strip()
    if not line:
        raise ValueError(EMPTY_ENTRY_TEXT)
    if len(line) > JOURNAL_ENTRY_MAX_CHARS:
        raise ValueError(LONG_ENTRY_TEXT)
    return line


def add_entry(content: str, time_label: str, text: str) -> str:
    """``content`` with one more entry line at the end."""
    head = content.rstrip("\n")
    gap = "\n" if entry_lines(content) else "\n\n"
    return f"{head}{gap}- {time_label} {entry_text(text)}\n"


def entry_lines(content: str) -> tuple[str, ...]:
    return tuple(line for line in content.splitlines() if _ENTRY.match(line))


def matching_lines(content: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    """Entry lines holding every term (case- and accent-blind)."""
    return tuple(line for line in entry_lines(content) if all(term in fold(line) for term in terms))


def _past(activity: str) -> str:
    verb, _, rest = activity.strip().partition(" ")
    return " ".join(part for part in (PAST.get(verb.lower(), verb), rest) if part)


def run_line(activities: Iterable[str]) -> str | None:
    """"Added a task ×2, saved a note" from a run's write steps, in first-seen order; ``None`` for none."""
    counts = Counter(_past(a) for a in activities if a.strip())
    if not counts:
        return None
    named = [f"{step} ×{n}" if n > 1 else step for step, n in counts.items()]
    shown, hidden = named[:JOURNAL_RUN_LINE_MAX_STEPS], len(named) - JOURNAL_RUN_LINE_MAX_STEPS
    line = ", ".join(shown) + (f" and {hidden} more" if hidden > 0 else "")
    return (line[:1].upper() + line[1:])[:JOURNAL_ENTRY_MAX_CHARS]
