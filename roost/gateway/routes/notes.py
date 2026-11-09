"""Notes over HTTP — the Board's Notes tab (M2 D4). Same ``NoteService`` as the
tools, so every change publishes ``notes_changed``. A save carries the revision
it edited; a stale one is a 409 carrying the current note (never an overwrite).

Projects hub (H12): a note may belong to one of the user's projects.
``PUT /{id}/project`` links or unlinks it without a new revision, so an open
editor's next save still lands, and ``?project_id=`` lists one project's
notes. A project that isn't the user's is refused (422, "No such project.")."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from roost.constants import (
    MAX_NOTE_CONTENT_LENGTH, MAX_NOTE_QUERY_LENGTH, MAX_NOTE_TAG_LENGTH, MAX_NOTE_TAGS, MAX_NOTE_TITLE_LENGTH,
    MAX_RECORD_ID_LENGTH,
)
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.gateway.routes.projects import ProjectLinkIn, refuse_general
from roost.notes.format import note_out, note_summary_out
from roost.notes.models import Note
from roost.notes.service import NoteService, new_note_draft
from roost.records.revision import RevisionConflict

notes_router = APIRouter(prefix="/api/notes", tags=["notes"])
NOTE_CONFLICT_TEXT = "This note changed since you opened it."
NOTE_NOT_FOUND_TEXT = "Note not found"
Tag = Annotated[str, Field(min_length=1, max_length=MAX_NOTE_TAG_LENGTH)]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_NOTE_TAGS)
    project_id: str | None = Field(default=None, max_length=MAX_RECORD_ID_LENGTH)

    @model_validator(mode="after")
    def _title_or_text(self) -> "NoteIn":
        if not (self.title or "").strip() and not self.content.strip():
            raise ValueError("A note needs a title or some text.")
        return self


class NoteSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=MAX_NOTE_CONTENT_LENGTH)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_NOTE_TAGS)
    pinned: bool | None = None

    def changes(self) -> dict[str, Any]:
        fields = self.model_dump(exclude={"base_revision"}, exclude_none=True)
        if "tags" in fields:
            fields = {**fields, "tags": tuple(fields["tags"])}
        if "title" in fields:
            fields = {**fields, "title": fields["title"].strip()}
        return fields


def _service(request: Request) -> NoteService:
    return request.app.state.notes


async def _detail(service: NoteService, user_id: str, note: Note) -> dict:
    return note_out(note, await service.links(user_id, note))


async def _conflict(service: NoteService, user_id: str, exc: RevisionConflict) -> JSONResponse:
    """A stale write never overwrites: 409 with the note as it is now."""
    return JSONResponse(status_code=409, content={"detail": NOTE_CONFLICT_TEXT,
                                                  "current": await _detail(service, user_id, exc.current)})


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail=NOTE_NOT_FOUND_TEXT)


@notes_router.get("")
async def list_notes(request: Request, user: CurrentUser,
                     q: str = Query(default="", max_length=MAX_NOTE_QUERY_LENGTH),
                     tag: str | None = Query(default=None, max_length=MAX_NOTE_TAG_LENGTH),
                     project_id: str | None = Query(default=None, max_length=MAX_RECORD_ID_LENGTH)):
    """``project_id`` keeps one project's notes; an empty one is no filter, like ``tag``."""
    notes = await _service(request).search(user.id, q, tag=tag, project_id=project_id or None)
    return [note_summary_out(note, q) for note in notes]


@notes_router.get("/{note_id}")
async def get_note(note_id: str, request: Request, user: CurrentUser):
    note = await _service(request).get(user.id, note_id)
    if note is None:
        raise _missing()
    return await _detail(_service(request), user.id, note)


@notes_router.post("", status_code=201, dependencies=[RequireOrigin])
async def create_note(body: NoteIn, request: Request, user: CurrentUser):
    service = _service(request)
    draft = new_note_draft(body.title, body.content, body.tags, project_id=body.project_id)
    try:
        await refuse_general(request, user.id, body.project_id)
        note = await service.add(user.id, draft)
    except ValueError as exc:   # General, or not one of the user's projects
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _detail(service, user.id, note)


@notes_router.put("/{note_id}", dependencies=[RequireOrigin])
async def save_note(note_id: str, body: NoteSaveIn, request: Request, user: CurrentUser):
    service = _service(request)
    try:
        note = await service.save(user.id, note_id, body.changes(), base_revision=body.base_revision)
    except RevisionConflict as exc:
        return await _conflict(service, user.id, exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        raise _missing()
    return await _detail(service, user.id, note)


@notes_router.put("/{note_id}/project", dependencies=[RequireOrigin])
async def set_note_project(note_id: str, body: ProjectLinkIn, request: Request, user: CurrentUser):
    """Link the note to one of the user's projects, or unlink it (``null``).
    The revision stays, so an open editor's next save still lands (H12)."""
    service = _service(request)
    try:
        await refuse_general(request, user.id, body.project_id)
        note = await service.set_project(user.id, note_id, body.project_id)
    except RevisionConflict as exc:   # two saves landed during the link (rare)
        return await _conflict(service, user.id, exc)
    except ValueError as exc:         # General, or not one of the user's projects
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        raise _missing()
    return await _detail(service, user.id, note)


@notes_router.post("/{note_id}/keep", dependencies=[RequireOrigin])
async def keep_note(note_id: str, request: Request, user: CurrentUser):
    """Keep: the user vouches for a note marked "from web content" (no tool can)."""
    note = await _service(request).keep(user.id, note_id)
    if note is None:
        raise _missing()
    return await _detail(_service(request), user.id, note)


@notes_router.delete("/{note_id}", status_code=204, dependencies=[RequireOrigin])
async def delete_note(note_id: str, request: Request, user: CurrentUser) -> None:
    if not await _service(request).delete(user.id, note_id):
        raise _missing()
