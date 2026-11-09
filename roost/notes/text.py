# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/lazybrain/store.py lines 201-216, 297-320 @ 21e1002, adapted for Roost

"""Note text helpers (M2 D1): accent-blind folding for search, the tag merge
(the caller's tags, the front matter's ``tags:`` and ``#hashtags``) and the
first-line title — LazyBrain's own rules, so M4's imported notes behave the same."""

from __future__ import annotations

import unicodedata
from typing import Iterable

from roost.constants import MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH
from roost.notes.frontmatter import parse_frontmatter
from roost.notes.wikilinks import extract_tags

UNTITLED_NOTE = "Untitled note"


def fold(s: str) -> str:
    """Lowercase + strip combining diacritics for substring search.

    Folds Latin accents ("Asistència" → "asistencia", "café" → "cafe")
    so multilingual search isn't case- or accent-sensitive. Non-Latin
    scripts (Georgian, Cyrillic, Arabic, CJK) carry no combining marks
    and pass through unchanged, so this is safe for the user's
    Latin-Georgian transliteration as well.
    """
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    ).lower()


def _front_matter_tags(markdown: str) -> list[str]:
    """Roost: a ``tags:`` key in the note's front matter counts as tags too."""
    props, _body, _has = parse_frontmatter(markdown)
    raw = props.get("tags")
    if isinstance(raw, list):
        return [str(tag) for tag in raw]
    return [raw] if isinstance(raw, str) and raw else []


def merge_tags(explicit: Iterable[str] | None, markdown: str) -> list[str]:
    """Tags from the caller plus #hashtags scraped from markdown body."""
    combined: list[str] = []
    seen: set[str] = set()
    for t in [*(explicit or []), *_front_matter_tags(markdown)]:
        norm = t.lstrip("#").strip().lower()
        if norm and norm not in seen:
            combined.append(norm)
            seen.add(norm)
    for t in extract_tags(markdown):
        if t not in seen:
            combined.append(t)
            seen.add(t)
    return combined


def capped_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Roost: at most MAX_NOTE_TAGS tags of at most MAX_NOTE_TAG_LENGTH characters."""
    return tuple(tag[:MAX_NOTE_TAG_LENGTH] for tag in list(tags)[:MAX_NOTE_TAGS])


def first_line(markdown: str) -> str | None:
    """Derive a title from the first non-empty line if caller didn't supply one."""
    for line in markdown.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:200]
    return None


def note_title(title: str | None, content: str) -> str:
    """Roost: the caller's title, else the body's first line after any front matter."""
    _props, body, _has = parse_frontmatter(content)
    chosen = (title or "").strip() or first_line(body) or UNTITLED_NOTE
    return chosen[:MAX_NOTE_TITLE_LENGTH]
