"""``NoteService`` — the notes store plus its live frame (M2 D1/D4) and the
rules both doors share: a new note's title and tags, tags kept in step with
the body, ``[[links]]`` resolved to notes. Tools and HTTP routes both go
through it, so the Board updates whoever changed a note."""

from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

from roost.constants import MAX_NOTE_CONTENT_LENGTH, NOTE_LINKS_MAX, NOTE_LIST_LIMIT
from roost.events.hub import EventHub
from roost.notes.models import Note, NoteDraft, NoteLink, NotePatch
from roost.notes.search import rank_notes
from roost.notes.store import NoteStore
from roost.notes.text import capped_tags, merge_tags, note_title
from roost.notes.wikilinks import extract_wikilinks_full

NoteChange = Literal["created", "updated", "deleted"]


def new_note_draft(title: str | None, content: str, tags: Iterable[str] = (), *,
                   project_id: str | None = None) -> NoteDraft:
    return NoteDraft(title=note_title(title, content), content=content,
                     tags=capped_tags(merge_tags(list(tags), content)), project_id=project_id)


def _with_tags(current: Note, changes: Mapping[str, Any]) -> dict[str, Any]:
    """A new body brings its #hashtags and front-matter tags along; the tags
    the note already had (or the caller set) stay — never dropped silently."""
    if "content" not in changes:
        return dict(changes)
    if len(changes["content"]) > MAX_NOTE_CONTENT_LENGTH:
        raise ValueError(f"a note can hold at most {MAX_NOTE_CONTENT_LENGTH} characters.")
    base = list(changes.get("tags", current.tags))
    return {**changes, "tags": capped_tags(merge_tags(base, changes["content"]))}


class NoteService:
    def __init__(self, store: NoteStore, events: EventHub) -> None:
        self._store = store
        self._events = events

    async def list(self, user_id: str, *, project_id: str | None = None) -> tuple[Note, ...]:
        return await self._store.list(user_id, limit=NOTE_LIST_LIMIT, project_id=project_id)

    async def all(self, user_id: str) -> tuple[Note, ...]:
        return await self._store.list(user_id)

    async def search(self, user_id: str, query: str, *, tag: str | None = None, limit: int = NOTE_LIST_LIMIT,
                     project_id: str | None = None) -> tuple[Note, ...]:
        """``project_id`` keeps the search inside one project (the store filters first, in SQL)."""
        return rank_notes(await self._store.list(user_id, project_id=project_id), query, tag=tag, limit=limit)

    async def get(self, user_id: str, note_id: str) -> Note | None:
        return await self._store.get(user_id, note_id)

    async def made_by(self, user_id: str, bot_id: str, limit: int) -> tuple[Note, ...]:
        return await self._store.made_by(user_id, bot_id, limit)

    async def for_project(self, user_id: str, project_id: str, limit: int) -> tuple[Note, ...]:
        return await self._store.for_project(user_id, project_id, limit)

    async def links(self, user_id: str, note: Note) -> tuple[NoteLink, ...]:
        """The note's ``[[links]]`` in order, each resolved to a note by exact title."""
        written: dict[str, str] = {}
        for link in extract_wikilinks_full(note.content):
            written.setdefault(link.target, link.raw_target)
        found = []
        for target, title in list(written.items())[:NOTE_LINKS_MAX]:
            hits = await self._store.with_title(user_id, title)
            found.append(NoteLink(target=target, title=title, note_id=hits[0].id if hits else None))
        return tuple(found)

    async def add(self, user_id: str, draft: NoteDraft, *, created_by_bot: str | None = None,
                  tainted: bool = False) -> Note:
        note = await self._store.create(user_id, draft, created_by_bot=created_by_bot, tainted=tainted)
        await self._changed(user_id, "created", note.id)
        return note

    async def save(self, user_id: str, note_id: str, changes: Mapping[str, Any], *,
                   base_revision: int | None = None) -> Note | None:
        current = await self._store.get(user_id, note_id)
        if current is None:
            return None
        note = await self._store.update(user_id, note_id, NotePatch(_with_tags(current, changes)),
                                        base_revision=base_revision)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def append(self, user_id: str, note: Note, text: str) -> Note | None:
        joined = note.content.rstrip("\n") + "\n\n" + text.strip()
        return await self.save(user_id, note.id, {"content": joined}, base_revision=note.revision)

    async def keep(self, user_id: str, note_id: str) -> Note | None:
        note = await self._store.keep(user_id, note_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def set_project(self, user_id: str, note_id: str, project_id: str | None) -> Note | None:
        """Link or unlink (``None``). The store's ``ValueError`` (not one of the
        user's projects) passes through, and then nothing is published."""
        note = await self._store.set_project(user_id, note_id, project_id)
        if note is not None:
            await self._changed(user_id, "updated", note.id)
        return note

    async def delete(self, user_id: str, note_id: str) -> bool:
        deleted = await self._store.delete(user_id, note_id)
        if deleted:
            await self._changed(user_id, "deleted", note_id)
        return deleted

    async def _changed(self, user_id: str, change: NoteChange, note_id: str) -> None:
        await self._events.publish(user_id, {"type": "notes_changed", "change": change, "note_id": note_id})
