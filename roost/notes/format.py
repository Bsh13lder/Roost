"""Rendering a note for a tool result or the Board (M2 D1). Note text is the
user's — or a page's — data: escaped here, by its producer, before any prompt."""

from __future__ import annotations

import html
from typing import Any

from roost.constants import NOTE_READ_MAX_CHARS, NOTE_SNIPPET_CHARS
from roost.notes.frontmatter import parse_frontmatter
from roost.notes.models import Note, NoteLink
from roost.notes.search import query_terms
from roost.notes.text import fold

WEB_MARK = " [from web content]"


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def snippet(note: Note, query: str = "") -> str:
    """One line of plain text around the first query word (or the body's start)."""
    _props, body, _has = parse_frontmatter(note.content)
    flat = " ".join(body.split())
    folded = fold(flat)
    hits = [folded.find(term) for term in query_terms(query) if term in folded]
    start = max(0, min(hits, default=0) - NOTE_SNIPPET_CHARS // 4)
    end = start + NOTE_SNIPPET_CHARS
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def note_line(note: Note, query: str = "") -> str:
    tags = f" [{', '.join(_escape(tag) for tag in note.tags)}]" if note.tags else ""
    web = WEB_MARK if note.tainted else ""
    return (f"- “{_escape(note.title)}”{tags} (updated {note.updated_at[:10]}){web} id={note.id}: "
            f"{_escape(snippet(note, query))}")


def note_list_text(notes: tuple[Note, ...], total: int, query: str = "") -> str:
    if not notes:
        return "No notes match." if query.strip() else "No notes yet."
    more = f"\n…and {total - len(notes)} more." if total > len(notes) else ""
    return "\n".join(note_line(note, query) for note in notes) + more


def _capped(text: str) -> str:
    if len(text) <= NOTE_READ_MAX_CHARS:
        return text
    return text[:NOTE_READ_MAX_CHARS] + f"\n…(showing {NOTE_READ_MAX_CHARS} of {len(text)} characters)"


def note_text(note: Note, links: tuple[NoteLink, ...]) -> str:
    """What read_note hands the model: the header, tags, links and the body."""
    lines = [f"“{_escape(note.title)}”{WEB_MARK if note.tainted else ''} id={note.id} revision={note.revision}"]
    if note.tags:
        lines.append("Tags: " + ", ".join(_escape(tag) for tag in note.tags))
    if links:
        lines.append("Links: " + ", ".join(_escape(link.title) + ("" if link.note_id else " (no note yet)")
                                           for link in links))
    return "\n".join([*lines, "", _escape(_capped(note.content))])


def note_summary_out(note: Note, query: str = "") -> dict[str, Any]:
    return {
        "id": note.id, "title": note.title, "tags": list(note.tags), "snippet": snippet(note, query),
        "pinned": note.pinned, "revision": note.revision, "created_at": note.created_at,
        "updated_at": note.updated_at, "created_by_bot": note.created_by_bot, "tainted": note.tainted,
        "project_id": note.project_id,
    }


def note_out(note: Note, links: tuple[NoteLink, ...]) -> dict[str, Any]:
    return {**note_summary_out(note), "content": note.content,
            "links": [{"target": link.target, "title": link.title, "note_id": link.note_id} for link in links]}
