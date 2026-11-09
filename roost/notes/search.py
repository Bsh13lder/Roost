"""Note search (M2 D1): decrypt-then-match over the user's notes. Every query
word must appear — case- and accent-blind — in the title, tags or body; hits
rank by how often the words appear (title ×3, tags ×2, body ×1), then by the
store's order (pinned, then newest first)."""

from __future__ import annotations

from typing import Iterable

from roost.notes.models import Note
from roost.notes.text import fold

_TITLE_WEIGHT, _TAG_WEIGHT, _BODY_WEIGHT = 3, 2, 1


def query_terms(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fold(query).split()))


def score(note: Note, terms: tuple[str, ...]) -> int:
    """0 unless every term appears somewhere."""
    title, tags, body = fold(note.title), fold(" ".join(note.tags)), fold(note.content)
    counts = [(title.count(term), tags.count(term), body.count(term)) for term in terms]
    if any(sum(count) == 0 for count in counts):
        return 0
    return sum(_TITLE_WEIGHT * t + _TAG_WEIGHT * g + _BODY_WEIGHT * b for t, g, b in counts)


def _has_tag(note: Note, tag: str | None) -> bool:
    """A blank tag (``None``, ``""``, ``"#"`` or whitespace) is no filter at
    all — callers that always send the field (a model with an optional
    argument, a Board client that always sends ``?tag=``) must still see
    every note, not none."""
    wanted = fold((tag or "").lstrip("#").strip())
    return not wanted or wanted in {fold(t) for t in note.tags}


def rank_notes(notes: Iterable[Note], query: str, *, tag: str | None = None, limit: int) -> tuple[Note, ...]:
    """``notes`` arrive in the store's order; an empty query keeps it."""
    pool = [note for note in notes if _has_tag(note, tag)]
    terms = query_terms(query)
    if not terms:
        return tuple(pool[:limit])
    scored = [(score(note, terms), index, note) for index, note in enumerate(pool)]
    hits = sorted((entry for entry in scored if entry[0] > 0), key=lambda entry: (-entry[0], entry[1]))
    return tuple(note for _score, _index, note in hits[:limit])
