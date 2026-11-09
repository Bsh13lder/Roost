"""DocumentStore (M2 D2, D5): one encrypted blob per file under its kind's AAD,
revisioned, shared by every bot, scoped to the user."""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from roost.bots.store import BotStore
from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentChange, DocumentDraft
from roost.documents.render import snapshot_of
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
from roost.records.revision import RevisionConflict
from team_helpers import make_bot

# Spec §4.7 / LazyClaw's contexts — written out here, not imported, on purpose.
_PAYLOAD_AAD = {"doc": "docs:payload", "sheet": "sheets:payload", "pdf": "pdf:payload"}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _doc(title: str = "My tasks", markdown: str = "- eggs") -> DocumentDraft:
    return DocumentDraft(kind="doc", title=title, body=json.dumps(doc_from_markdown(title, markdown)))


def _sheet(title: str = "Sheet") -> DocumentDraft:
    return DocumentDraft(kind="sheet", title=title, body=json.dumps({"sheets": {}}))


def _raw(cfg, document_id: str) -> tuple[str, str]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT title, payload FROM documents WHERE id = ?", (document_id,)).fetchone()
    finally:
        con.close()


async def test_each_kind_is_encrypted_under_its_own_aad(cfg, user_id):
    store = DocumentStore(cfg)
    dek = await get_user_dek(cfg, user_id)
    pdf = DocumentDraft(kind="pdf", title="Lease", body=base64.b64encode(b"%PDF-1.4 x").decode("ascii"), pages=1)
    for draft in (_doc(), _sheet(), pdf):
        meta = await store.create(user_id, draft, created_by_bot=None, tainted=False)
        title, payload = _raw(cfg, meta.id)
        assert title.startswith("enc:v2:") and payload.startswith("enc:v2:") and draft.title not in title
        assert decrypt(payload, dek, user_aad(user_id, _PAYLOAD_AAD[draft.kind])) == draft.body
        with pytest.raises(InvalidTag):
            decrypt(payload, dek, user_aad(user_id, "documents:title"))
        assert (await store.get(user_id, meta.id)).body == draft.body


async def test_a_save_bumps_the_revision_and_a_stale_one_is_refused_with_the_current_copy(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=1, title="Renamed"))
    assert (saved.title, saved.revision) == ("Renamed", 2)
    with pytest.raises(RevisionConflict) as caught:
        await store.save(user_id, meta.id, DocumentChange(base_revision=1, title="Stale"))
    assert (caught.value.current.meta.title, caught.value.current.meta.revision) == ("Renamed", 2)
    assert (await store.get_meta(user_id, meta.id)).title == "Renamed"


async def test_a_save_returns_its_own_revision_even_if_another_write_lands_right_after(cfg, user_id, monkeypatch):
    """DocumentStore.save must build its result from what it just wrote, not a
    re-read after the commit: a second write landing in that window must
    never leak into the first save's own result (the Board would otherwise
    autosave on that borrowed base_revision and silently overwrite it)."""
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    real_get_meta = DocumentStore.get_meta
    calls = {"n": 0}

    async def racing_get_meta(self, uid, doc_id):
        calls["n"] += 1
        if calls["n"] == 2:
            # Simulate a second writer (another save, or a Board tab) landing
            # exactly between this save's commit and a post-commit re-read.
            monkeypatch.setattr(DocumentStore, "get_meta", real_get_meta)
            await store.save(uid, doc_id, DocumentChange(base_revision=2, title="Other writer"))
            monkeypatch.setattr(DocumentStore, "get_meta", racing_get_meta)
        return await real_get_meta(self, uid, doc_id)

    monkeypatch.setattr(DocumentStore, "get_meta", racing_get_meta)
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=1, title="Renamed"))
    assert (saved.title, saved.revision) == ("Renamed", 2)


async def test_a_save_to_an_empty_title_returns_the_empty_title_it_stored(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    saved = await store.save(user_id, meta.id, DocumentChange(base_revision=1, title=""))
    assert (saved.title, saved.revision) == ("", 2)
    assert (await store.get_meta(user_id, meta.id)).title == ""


async def test_a_save_with_nothing_to_change_is_refused(cfg, user_id):
    meta = await DocumentStore(cfg).create(user_id, _doc(), created_by_bot=None, tainted=False)
    with pytest.raises(ValueError):
        await DocumentStore(cfg).save(user_id, meta.id, DocumentChange(base_revision=1))


async def test_list_is_newest_first_and_filters_by_kind(cfg, user_id):
    store = DocumentStore(cfg)
    await store.create(user_id, _doc("First"), created_by_bot=None, tainted=False)
    await store.create(user_id, _sheet("Second"), created_by_bot=None, tainted=False)
    assert [meta.title for meta in await store.list(user_id)] == ["Second", "First"]
    assert [meta.title for meta in await store.list(user_id, kind="doc")] == ["First"]


async def test_another_user_sees_and_changes_nothing(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    assert await store.get(bob, meta.id) is None and await store.get_meta(bob, meta.id) is None
    assert await store.list(bob) == ()
    assert await store.save(bob, meta.id, DocumentChange(base_revision=1, title="x")) is None
    assert await store.keep(bob, meta.id) is None
    assert await store.delete(bob, meta.id) is False


async def test_keep_clears_the_taint_and_delete_is_soft(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=True)
    kept = await store.keep(user_id, meta.id)
    assert (kept.tainted, kept.revision) == (False, 1)
    assert await store.delete(user_id, meta.id) is True
    assert await store.get(user_id, meta.id) is None
    assert await store.delete(user_id, meta.id) is False


async def test_retiring_the_bot_keeps_the_users_documents(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    meta = await DocumentStore(cfg).create(user_id, _doc(), created_by_bot=bot.id, tainted=False)
    await BotStore(cfg).delete(user_id, bot.id)
    [kept] = await DocumentStore(cfg).list(user_id)
    assert (kept.id, kept.created_by_bot) == (meta.id, None)


async def test_a_damaged_blob_reads_as_a_plain_error(cfg, user_id):
    store = DocumentStore(cfg)
    meta = await store.create(user_id, _doc(), created_by_bot=None, tainted=False)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        con.execute("UPDATE documents SET payload = 'enc:v2:AAAA:BBBB' WHERE id = ?", (meta.id,))
        con.commit()
    finally:
        con.close()
    with pytest.raises(ValueError, match="could not be read"):
        snapshot_of(await store.get(user_id, meta.id))
