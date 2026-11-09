"""The note tools over the user's shared notes (M2 D1; projects hub H12).
Pydantic arguments, provenance (bot + taint) on every new note, escaped
results, and exact-or-ask names: a change needs the note's id, exact title or
a unique part of it — a near miss is a "did you mean" refusal, never a change
to the wrong note. A note may belong to one of the user's projects, named the
same exact-or-ask way (never General); moving it never bumps its revision."""

from __future__ import annotations

import html
from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    MAX_CATEGORY_NAME_LENGTH, MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS,
    MAX_NOTE_TITLE_LENGTH, NOTE_FIND_LIMIT, NOTE_SCAN_LIMIT,
)
from roost.journal.service import JournalService
from roost.notes.format import note_line, note_list_text, note_text
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.projects.refs import id_of, project_ref, project_suffix, project_taint
from roost.projects.service import ProjectService
from roost.records.resolver import NamedRef, resolve
from roost.records.revision import RevisionConflict
from roost.records.tool_text import ToolText
from roost.tags.record import bot_record_tags
from roost.tags.rules import keep_system_tags, topic_tags
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome

JOURNAL_FIND_LIMIT = 5
CHANGED_WHILE_WRITING_TEXT = "Refused: that note changed while I was writing. Read it again first."
NOTHING_TO_UPDATE_TEXT = "Refused: update_note needs a new title, content, tags or project."
_ACTIVITY = {
    "add_note": "saving a note", "find_notes": "searching your notes", "read_note": "reading a note",
    "append_to_note": "adding to a note", "update_note": "updating a note", "delete_note": "deleting a note",
}
_NEEDS = {
    "add_note": "the note's text (content), and optionally a title, tags and a project",
    "find_notes": "an optional query, tag and project",
    "read_note": "the note (its id or title)",
    "append_to_note": "the note (its id or title) and the text to add",
    "update_note": "the note (its id or title) and a new title, content, tags or project",
    "delete_note": "the note (its id or title)",
}
Tag = Annotated[ToolText, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


class AddNoteArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: ToolText = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    title: ToolText | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


class FindNotesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: ToolText = Field(default="", max_length=MAX_NOTE_QUERY_LENGTH)
    tag: ToolText | None = Field(default=None, max_length=MAX_NOTE_TAG_LENGTH)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)


_CHANGES = frozenset({"append_to_note", "update_note", "delete_note"})


class NoteRefArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note: ToolText = Field(min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)


class AppendNoteArgs(NoteRefArgs):
    text: ToolText = Field(min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)


class UpdateNoteArgs(NoteRefArgs):
    title: ToolText | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: ToolText | None = Field(default=None, min_length=1, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)
    project: ToolText | None = Field(default=None, max_length=MAX_CATEGORY_NAME_LENGTH)   # '' unlinks

    def changes(self) -> dict[str, Any]:
        """The note's own text fields; the project goes through ``set_project``."""
        found = {"title": self.title.strip() if self.title else None, "content": self.content,
                 "tags": tuple(self.tags) if self.tags is not None else None}
        return {key: value for key, value in found.items() if value is not None}


def _titles(notes: tuple[Note, ...]) -> str:
    """Escaped titles with ids for a refusal, each web-made one marked."""
    return "; ".join(f"“{_escape(n.title)}” id={n.id}" + (" [from web content]" if n.tainted else "") for n in notes)


def _kept_tags(found: Note, changes: Mapping[str, Any]) -> dict[str, Any]:
    """A bot's new tags are checked topic tags; the note's ``bot:`` and ``project:`` tags stay."""
    if "tags" not in changes:
        return dict(changes)
    return {**changes, "tags": keep_system_tags(found.tags, topic_tags(changes["tags"]))}


class NoteTools:
    names = frozenset(_ACTIVITY)

    def __init__(self, service: NoteService, projects: ProjectService, *, journal: JournalService | None = None) -> None:
        self._service = service
        self._projects = projects
        self._journal = journal   # find_notes also lists the bot's own journal days that match

    def activity(self, name: str) -> str:
        return _ACTIVITY[name]

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        handlers = {"add_note": self._add, "find_notes": self._find, "read_note": self._read,
                    "append_to_note": self._append, "update_note": self._update, "delete_note": self._delete}
        try:
            return await handlers[name](arguments, ctx)
        except ValidationError:
            return ToolOutcome(f"Refused: {name} needs {_NEEDS[name]}.")
        except RevisionConflict:
            return ToolOutcome(CHANGED_WHILE_WRITING_TEXT)
        except ValueError as exc:
            return ToolOutcome(f"Refused: {_escape(str(exc))}")

    async def _add(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AddNoteArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        tags = bot_record_tags(ctx, None if project is None else project.name, args.tags)
        draft = new_note_draft(args.title, args.content.strip(), tags, project_id=id_of(project))
        note = await self._service.add(ctx.user_id, draft, created_by_bot=ctx.bot_id, tainted=ctx.tainted)
        return ToolOutcome(f"Saved: {note_line(note)}{project_suffix(project)}", created=True,
                           tainted=project_taint(project))

    async def _find(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = FindNotesArgs.model_validate(arguments)
        project = await project_ref(self._projects, ctx.user_id, args.project, change=False)
        if isinstance(project, ToolOutcome):
            return project
        matching = await self._service.search(ctx.user_id, args.query, tag=args.tag, limit=NOTE_SCAN_LIMIT,
                                              project_id=id_of(project))
        shown = matching[:NOTE_FIND_LIMIT]
        journal, journal_tainted = await self._journal_days(ctx, args.query)
        return ToolOutcome(note_list_text(shown, len(matching), args.query) + journal,
                           tainted=any(n.tainted for n in shown) or journal_tainted)

    async def _journal_days(self, ctx: RecordContext, query: str) -> tuple[str, bool]:
        """The bot's own journal days that match, as one more paragraph (read one with journal_read)."""
        if self._journal is None or not query.strip():
            return "", False
        hits = await self._journal.search(ctx.user_id, query, bot_id=ctx.bot_id, limit=JOURNAL_FIND_LIMIT)
        if not hits:
            return "", False
        lines = "\n".join(f"- {hit.day.isoformat()}: {_escape(' / '.join(hit.lines))}" for hit in hits)
        return f"\n\nIn your journal (journal_read opens a day):\n{lines}", any(hit.tainted for hit in hits)

    async def _read(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=False)
        if isinstance(found, ToolOutcome):
            return found
        return ToolOutcome(note_text(found, await self._service.links(ctx.user_id, found)), tainted=found.tainted)

    async def _append(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = AppendNoteArgs.model_validate(arguments)
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        note = await self._service.append(ctx.user_id, found, args.text)
        text = f"Added to “{_escape(found.title)}” (revision {note.revision})." if note else "Refused: that note is gone."
        return ToolOutcome(text, tainted=found.tainted)

    async def _update(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        args = UpdateNoteArgs.model_validate(arguments)
        moving = args.project is not None
        if not args.changes() and not moving:
            return ToolOutcome(NOTHING_TO_UPDATE_TEXT)
        found = await self._find_one(ctx.user_id, args.note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        project = await project_ref(self._projects, ctx.user_id, args.project, change=True)
        if isinstance(project, ToolOutcome):
            return project
        note = await self._save(ctx.user_id, found, _kept_tags(found, args.changes()))
        if note is not None and moving:
            note = await self._service.set_project(ctx.user_id, found.id, id_of(project))
        if note is None:
            return ToolOutcome("Refused: that note is gone.", tainted=found.tainted)
        return ToolOutcome(f"Updated: {note_line(note)}{project_suffix(project, unlinked=moving)}",
                           tainted=found.tainted or project_taint(project))

    async def _save(self, user_id: str, found: Note, changes: Mapping[str, Any]) -> Note | None:
        """The text change first (at the revision read); a move alone writes nothing here."""
        if not changes:
            return found
        return await self._service.save(user_id, found.id, changes, base_revision=found.revision)

    async def _delete(self, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=True)
        if isinstance(found, ToolOutcome):
            return found
        await self._service.delete(ctx.user_id, found.id)
        return ToolOutcome(f"Deleted: “{_escape(found.title)}”.", tainted=found.tainted)

    async def target_title(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> str | None:
        """The change check: the stored title of the note a change names, or ``None``."""
        if name not in _CHANGES:
            return None
        try:
            found = await self._find_one(ctx.user_id, NoteRefArgs.model_validate(arguments).note, change=True)
        except ValidationError:
            return None
        return None if isinstance(found, ToolOutcome) else found.title

    async def _find_one(self, user_id: str, ref: str, *, change: bool) -> Note | ToolOutcome:
        """The note a call targets: its id, exact title or a unique part of it
        (the harvested resolver). A lone near miss is fine to read but never to
        change. A refusal that shows titles carries those notes' taint (M1 D3)."""
        notes = await self._service.all(user_id)
        by_id = next((note for note in notes if note.id == ref.strip()), None)
        if by_id is not None:
            return by_id
        by_key = {note.id: note for note in notes}
        hit = resolve(ref, [NamedRef(note.id, note.title) for note in notes])
        if hit.resolved is not None and (hit.reason != "fuzzy" or not change):
            return by_key[hit.resolved.id]
        shown = tuple(by_key[c.id] for c in hit.candidates[:5])
        tainted = any(note.tainted for note in shown)
        if hit.reason == "fuzzy":
            return ToolOutcome(f"Refused: no note is called “{_escape(ref)}”. Did you mean {_titles(shown)}? "
                               "Say it exactly.", tainted=tainted)
        if hit.reason == "multi":
            return ToolOutcome(f"Refused: several notes match “{_escape(ref)}”: {_titles(shown)}. "
                               "Say which one (its id).", tainted=tainted)
        return ToolOutcome(f"Refused: no note matches “{_escape(ref)}”.")
