"""Notes and documents: the project link (projects hub, H12).

A note or a document may belong to one of the user's projects. Linking goes
through ``set_project`` and keeps the revision, so an open editor's next save
still lands. A project that isn't the user's (another user's, a deleted one,
an unknown id) is refused with "No such project." and nothing is written. The
lists filter by project in SQL, before their limit. The services publish
``*_changed "updated"``, and a PDF made from a doc lands in the doc's project."""

from __future__ import annotations

import json
import sqlite3

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentChange, DocumentDraft, DocumentMeta
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.project_store import ProjectStore
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.service import NoteService, new_note_draft
from roost.notes.store import NoteStore

# The contract's text, written out here on purpose (not imported).
_REFUSED = r"^No such project\.$"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _project(cfg, user_id: str, name: str = "Renovation") -> str:
    return (await ProjectStore(cfg).find_or_create(user_id, name, created_by_bot=None, tainted=False)).id


async def _note(cfg, user_id: str, title: str = "Paint", *, project_id: str | None = None) -> Note:
    draft = NoteDraft(title=title, content="white walls", project_id=project_id)
    return await NoteStore(cfg).create(user_id, draft, created_by_bot=None, tainted=False)


def _doc(title: str = "Quote", *, project_id: str | None = None) -> DocumentDraft:
    return DocumentDraft(kind="doc", title=title, body=json.dumps(doc_from_markdown(title, "- tiles")),
                         project_id=project_id)


def _sheet(title: str = "Costs", *, project_id: str | None = None) -> DocumentDraft:
    return DocumentDraft(kind="sheet", title=title, body=json.dumps({"sheets": {}}), project_id=project_id)


async def _create_doc(cfg, user_id: str, draft: DocumentDraft) -> DocumentMeta:
    return await DocumentStore(cfg).create(user_id, draft, created_by_bot=None, tainted=False)


def _stored_project_id(cfg, table: str, row_id: str) -> str | None:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(f"SELECT project_id FROM {table} WHERE id = ?", (row_id,)).fetchone()[0]
    finally:
        con.close()


async def _published(cfg, user_id: str, kind: str) -> list[dict]:
    return [event for event in await EventHub(cfg).since(user_id, 0) if event["type"] == kind]


# --- notes: the store -------------------------------------------------------


async def test_a_note_made_in_a_project_keeps_the_link_in_plaintext(cfg, user_id):
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=project_id)
    assert note.project_id == project_id
    assert _stored_project_id(cfg, "notes", note.id) == project_id
    assert await NoteStore(cfg).get(user_id, note.id) == note


async def test_linking_and_unlinking_a_note_keeps_its_revision(cfg, user_id):
    store = NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    linked = await store.set_project(user_id, note.id, project_id)
    assert (linked.project_id, linked.revision, linked.content) == (project_id, 1, "white walls")
    assert await store.get(user_id, note.id) == linked
    unlinked = await store.set_project(user_id, note.id, None)
    assert (unlinked.project_id, unlinked.revision) == (None, 1)
    assert _stored_project_id(cfg, "notes", note.id) is None


async def test_an_open_editor_still_saves_after_the_note_is_linked(cfg, user_id):
    store = NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    await store.set_project(user_id, note.id, project_id)
    saved = await store.update(user_id, note.id, NotePatch({"content": "grey walls"}), base_revision=note.revision)
    assert (saved.content, saved.revision, saved.project_id) == ("grey walls", 2, project_id)
    with pytest.raises(ValueError):
        NotePatch({"project_id": None})   # only set_project moves the link


async def test_linking_survives_a_save_landing_between_read_and_write(cfg, user_id, monkeypatch):
    store, other = NoteStore(cfg), NoteStore(cfg)
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id)
    real_get, raced = store.get, []

    async def get_then_race(uid: str, nid: str):
        found = await real_get(uid, nid)
        if not raced:
            raced.append(True)
            await other.update(uid, nid, NotePatch({"content": "theirs"}))
        return found

    monkeypatch.setattr(store, "get", get_then_race)
    linked = await store.set_project(user_id, note.id, project_id)
    assert (linked.content, linked.revision, linked.project_id) == ("theirs", 2, project_id)
    assert await other.get(user_id, note.id) == linked


async def test_another_users_project_is_refused_for_a_note_and_nothing_is_written(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project = await _project(cfg, bob, "Garage")
    store = NoteStore(cfg)
    with pytest.raises(ValueError, match=_REFUSED):
        await _note(cfg, user_id, project_id=bobs_project)
    assert await store.list(user_id) == ()
    note = await _note(cfg, user_id)
    for foreign in (bobs_project, "no-such-project"):
        with pytest.raises(ValueError, match=_REFUSED):
            await store.set_project(user_id, note.id, foreign)
    assert await store.get(user_id, note.id) == note


async def test_a_deleted_project_can_no_longer_be_linked(cfg, user_id):
    project_id = await _project(cfg, user_id)
    assert await ProjectStore(cfg).delete(user_id, project_id) is True
    note = await _note(cfg, user_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await NoteStore(cfg).set_project(user_id, note.id, project_id)
    with pytest.raises(ValueError, match=_REFUSED):
        await _create_doc(cfg, user_id, _doc(project_id=project_id))


async def test_deleting_a_project_unlinks_its_note_and_document_but_keeps_them(cfg, user_id):
    project_id = await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=project_id)
    meta = await _create_doc(cfg, user_id, _doc(project_id=project_id))
    assert await ProjectStore(cfg).delete(user_id, project_id) is True
    kept_note = await NoteStore(cfg).get(user_id, note.id)
    kept_doc = await DocumentStore(cfg).get_meta(user_id, meta.id)
    assert (kept_note.title, kept_note.project_id) == ("Paint", None)
    assert (kept_doc.title, kept_doc.project_id) == ("Quote", None)


async def test_another_user_can_neither_link_nor_list_alices_notes_and_documents(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project, alices_project = await _project(cfg, bob, "Garage"), await _project(cfg, user_id)
    note = await _note(cfg, user_id, project_id=alices_project)
    meta = await _create_doc(cfg, user_id, _doc(project_id=alices_project))
    assert await NoteStore(cfg).set_project(bob, note.id, bobs_project) is None
    assert await DocumentStore(cfg).set_project(bob, meta.id, bobs_project) is None
    assert await NoteStore(cfg).list(bob, project_id=alices_project) == ()
    assert await DocumentStore(cfg).list(bob, project_id=alices_project) == ()
    assert await DocumentStore(cfg).for_project(bob, alices_project, 10) == ()
    assert (await NoteStore(cfg).get(user_id, note.id)).project_id == alices_project
    assert (await DocumentStore(cfg).get_meta(user_id, meta.id)).project_id == alices_project


async def test_the_note_list_filters_by_project_before_its_limit(cfg, user_id):
    store = NoteStore(cfg)
    renovation, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    paint = await _note(cfg, user_id, "Paint", project_id=renovation)
    tiles = await _note(cfg, user_id, "Tiles", project_id=renovation)
    await _note(cfg, user_id, "Roses", project_id=garden)
    await _note(cfg, user_id, "Loose")
    assert [note.id for note in await store.list(user_id, project_id=renovation)] == [tiles.id, paint.id]
    assert [note.id for note in await store.list(user_id, project_id=renovation, limit=1)] == [tiles.id]
    assert [note.id for note in await store.for_project(user_id, renovation, 1)] == [tiles.id]
    assert len(await store.list(user_id)) == 4


# --- documents: the store ---------------------------------------------------


async def test_a_document_made_in_a_project_keeps_the_link_in_plaintext(cfg, user_id):
    project_id = await _project(cfg, user_id)
    meta = await _create_doc(cfg, user_id, _doc(project_id=project_id))
    assert meta.project_id == project_id
    assert _stored_project_id(cfg, "documents", meta.id) == project_id
    assert await DocumentStore(cfg).get_meta(user_id, meta.id) == meta
    assert (await DocumentStore(cfg).get(user_id, meta.id)).meta == meta


async def test_linking_a_document_keeps_its_revision_so_an_open_editor_still_saves(cfg, user_id):
    store = DocumentStore(cfg)
    project_id = await _project(cfg, user_id)
    meta = await _create_doc(cfg, user_id, _doc())
    linked = await store.set_project(user_id, meta.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await store.get_meta(user_id, meta.id) == linked
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=meta.revision, title="Quote v2"))
    assert (saved.title, saved.revision, saved.project_id) == ("Quote v2", 2, project_id)
    unlinked = await store.set_project(user_id, meta.id, None)
    assert (unlinked.project_id, unlinked.revision) == (None, 2)
    assert _stored_project_id(cfg, "documents", meta.id) is None


async def test_another_users_project_is_refused_for_a_document_and_nothing_is_written(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_project = await _project(cfg, bob, "Garage")
    store = DocumentStore(cfg)
    with pytest.raises(ValueError, match=_REFUSED):
        await _create_doc(cfg, user_id, _doc(project_id=bobs_project))
    assert await store.list(user_id) == ()
    meta = await _create_doc(cfg, user_id, _doc())
    for foreign in (bobs_project, "no-such-project"):
        with pytest.raises(ValueError, match=_REFUSED):
            await store.set_project(user_id, meta.id, foreign)
    assert await store.get_meta(user_id, meta.id) == meta


async def test_the_document_list_filters_by_project_and_kind_before_any_limit(cfg, user_id):
    store = DocumentStore(cfg)
    renovation, garden = await _project(cfg, user_id), await _project(cfg, user_id, "Garden")
    quote = await _create_doc(cfg, user_id, _doc("Quote", project_id=renovation))
    costs = await _create_doc(cfg, user_id, _sheet("Costs", project_id=renovation))
    await _create_doc(cfg, user_id, _doc("Roses", project_id=garden))
    await _create_doc(cfg, user_id, _doc("Loose"))
    assert [meta.id for meta in await store.list(user_id, project_id=renovation)] == [costs.id, quote.id]
    assert [meta.id for meta in await store.list(user_id, "doc", project_id=renovation)] == [quote.id]
    assert [meta.id for meta in await store.for_project(user_id, renovation, 1)] == [costs.id]
    assert len(await store.list(user_id)) == 4


# --- the services -----------------------------------------------------------


async def test_linking_a_note_publishes_notes_changed_updated(cfg, user_id):
    service = NoteService(NoteStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    note = await service.add(user_id, new_note_draft("Paint", "white walls"))
    linked = await service.set_project(user_id, note.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await service.set_project(user_id, "no-such-note", project_id) is None
    with pytest.raises(ValueError, match=_REFUSED):
        await service.set_project(user_id, note.id, "no-such-project")
    frames = [(frame["change"], frame["note_id"]) for frame in await _published(cfg, user_id, "notes_changed")]
    assert frames == [("created", note.id), ("updated", note.id)]


async def test_a_projects_notes_come_from_for_project_list_and_search(cfg, user_id):
    service = NoteService(NoteStore(cfg), EventHub(cfg))
    renovation = await _project(cfg, user_id)
    paint = await service.add(user_id, new_note_draft("Paint", "white walls", project_id=renovation))
    tiles = await service.add(user_id, new_note_draft("Tiles", "white tiles", project_id=renovation))
    await service.add(user_id, new_note_draft("Garden", "white roses"))
    assert [note.id for note in await service.for_project(user_id, renovation, 1)] == [tiles.id]
    assert [note.id for note in await service.list(user_id, project_id=renovation)] == [tiles.id, paint.id]
    found = await service.search(user_id, "white", project_id=renovation)
    assert {note.id for note in found} == {paint.id, tiles.id}
    assert len(await service.search(user_id, "white")) == 3


async def test_linking_a_document_publishes_documents_changed_updated(cfg, user_id):
    service = DocumentService(DocumentStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    meta = await service.create_doc(user_id, "Quote", "- tiles")
    linked = await service.set_project(user_id, meta.id, project_id)
    assert (linked.project_id, linked.revision) == (project_id, 1)
    assert await service.set_project(user_id, "no-such-document", project_id) is None
    with pytest.raises(ValueError, match=_REFUSED):
        await service.set_project(user_id, meta.id, "no-such-project")
    frames = [(frame["change"], frame["document_id"], frame["kind"])
              for frame in await _published(cfg, user_id, "documents_changed")]
    assert frames == [("created", meta.id, "doc"), ("updated", meta.id, "doc")]


async def test_new_documents_take_a_project_and_a_pdf_inherits_its_docs_project(cfg, user_id):
    service = DocumentService(DocumentStore(cfg), EventHub(cfg))
    project_id = await _project(cfg, user_id)
    letter = await service.create_doc(user_id, "Letter", "Happy birthday", project_id=project_id)
    costs = await service.create_sheet(user_id, "Costs", [["Tiles", "120"]], project_id=project_id)
    pdf = await service.make_pdf(user_id, await service.get(user_id, letter.id), "Letter", created_by_bot=None,
                                 tainted=False)
    assert (letter.project_id, costs.project_id, pdf.project_id) == (project_id, project_id, project_id)
    assert [meta.id for meta in await service.for_project(user_id, project_id, 10)] == [pdf.id, costs.id, letter.id]
    assert [meta.id for meta in await service.list(user_id, "sheet", project_id=project_id)] == [costs.id]
    loose = await service.create_doc(user_id, "Loose", "no project")
    loose_pdf = await service.make_pdf(user_id, await service.get(user_id, loose.id), "Loose", created_by_bot=None,
                                       tainted=False)
    assert (loose_pdf.kind, loose_pdf.project_id) == ("pdf", None)
