"""NoteStore (M2 D1, D5): the user's notes, encrypted, revisioned, shared by every bot."""

from __future__ import annotations

import sqlite3

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.notes.models import Note, NoteDraft, NotePatch
from roost.notes.search import rank_notes
from roost.notes.store import NoteStore
from roost.records.revision import RevisionConflict
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _add(cfg, user_id, title="Ana", content="likes orchids", *, tainted=False, bot=None) -> Note:
    return await NoteStore(cfg).create(user_id, NoteDraft(title=title, content=content, tags=("people",)),
                                       created_by_bot=bot, tainted=tainted)


async def test_a_note_is_stored_encrypted_with_an_hmac_title_key(cfg, user_id):
    note = await _add(cfg, user_id)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        title, key, content, tags, revision = con.execute(
            "SELECT title, title_key, content, tags, revision FROM notes WHERE id = ?", (note.id,)).fetchone()
    finally:
        con.close()
    assert all(value.startswith("enc:v2:") for value in (title, content, tags))
    assert "ana" not in key.lower() and len(key) == 64 and revision == 1
    assert await NoteStore(cfg).get(user_id, note.id) == note


async def test_an_exact_title_finds_the_note_whatever_its_case_and_spacing(cfg, user_id):
    note = await _add(cfg, user_id, title="Ana García")
    assert [n.id for n in await NoteStore(cfg).with_title(user_id, "  ana   garcía ")] == [note.id]
    assert await NoteStore(cfg).with_title(user_id, "Ana") == ()


async def test_a_stale_revision_is_refused_with_the_current_note(cfg, user_id):
    store = NoteStore(cfg)
    note = await _add(cfg, user_id, content="v1")
    saved = await store.update(user_id, note.id, NotePatch({"content": "v2"}), base_revision=1)
    assert (saved.content, saved.revision) == ("v2", 2)
    with pytest.raises(RevisionConflict) as caught:
        await store.update(user_id, note.id, NotePatch({"content": "stale"}), base_revision=1)
    assert caught.value.current.content == "v2"
    assert (await store.get(user_id, note.id)).content == "v2"


async def test_a_write_landing_between_read_and_write_is_a_conflict_not_a_clobber(cfg, user_id, monkeypatch):
    store, other = NoteStore(cfg), NoteStore(cfg)
    note = await _add(cfg, user_id, content="v1")
    real_get, raced = store.get, []

    async def get_then_race(uid: str, nid: str):
        found = await real_get(uid, nid)
        if not raced:
            raced.append(True)
            await other.update(uid, nid, NotePatch({"content": "theirs"}))
        return found

    monkeypatch.setattr(store, "get", get_then_race)
    with pytest.raises(RevisionConflict) as caught:
        await store.update(user_id, note.id, NotePatch({"content": "mine"}))
    assert caught.value.current.content == "theirs"


async def test_another_user_sees_and_changes_nothing(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = NoteStore(cfg)
    note = await _add(cfg, user_id)
    assert await store.get(bob, note.id) is None
    assert await store.list(bob) == ()
    assert await store.update(bob, note.id, NotePatch({"content": "x"})) is None
    assert await store.delete(bob, note.id) is False
    assert (await store.get(user_id, note.id)).content == "likes orchids"


async def test_keep_clears_the_taint_without_a_new_revision_and_delete_is_soft(cfg, user_id):
    store = NoteStore(cfg)
    note = await _add(cfg, user_id, tainted=True)
    kept = await store.keep(user_id, note.id)
    assert (kept.tainted, kept.revision) == (False, 1)
    assert await store.delete(user_id, note.id) is True
    assert await store.get(user_id, note.id) is None
    assert await store.delete(user_id, note.id) is False


async def test_retiring_the_bot_keeps_the_users_notes(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    note = await _add(cfg, user_id, bot=bot.id)
    await BotStore(cfg).delete(user_id, bot.id)
    [kept] = await NoteStore(cfg).list(user_id)
    assert (kept.id, kept.created_by_bot) == (note.id, None)


def _note(note_id: str, title: str, content: str, *, tags=(), updated="2026-10-01T00:00:00+00:00") -> Note:
    return Note(id=note_id, user_id="u", title=title, content=content, tags=tuple(tags), pinned=False, revision=1,
                created_at=updated, updated_at=updated, created_by_bot=None, tainted=False)


def test_search_ignores_case_and_accents():
    ana = _note("n1", "Ana", "Cumpleaños el 3 de mayo; le gustan las orquídeas.")
    assert rank_notes((ana,), "cumpleanos ORQUIDEAS", limit=10) == (ana,)


def test_every_query_word_must_match():
    assert rank_notes((_note("n1", "Ana", "likes orchids"),), "orchids roses", limit=10) == ()


def test_more_matches_rank_first_then_the_newest():
    newer = _note("n1", "Shopping", "orchids", updated="2026-10-10T00:00:00+00:00")
    older = _note("n2", "Shopping again", "orchids", updated="2026-10-01T00:00:00+00:00")
    titled = _note("n3", "Orchids", "how to water them", updated="2026-09-01T00:00:00+00:00")
    assert [n.id for n in rank_notes((newer, older, titled), "orchids", limit=10)] == ["n3", "n1", "n2"]


def test_an_empty_query_lists_newest_first_and_a_tag_filters():
    tagged, plain = _note("n1", "A", "x", tags=("people",)), _note("n2", "B", "y")
    assert rank_notes((tagged, plain), "", limit=10) == (tagged, plain)
    assert rank_notes((tagged, plain), "  ", tag="#People", limit=10) == (tagged,)
    assert rank_notes((tagged, plain), "", limit=1) == (tagged,)


def test_a_blank_tag_is_not_a_filter():
    """A model or an always-sends-the-field HTTP client can pass tag="" or
    tag="#"; neither should hide every note (M2 Task 1 review, finding #1)."""
    tagged, plain = _note("n1", "A", "x", tags=("people",)), _note("n2", "B", "y")
    assert rank_notes((tagged, plain), "orchids", tag="", limit=10) == ()  # query still has to match
    assert rank_notes((tagged, plain), "", tag="", limit=10) == (tagged, plain)
    assert rank_notes((tagged, plain), "", tag="#", limit=10) == (tagged, plain)
    assert rank_notes((tagged, plain), "", tag="  ", limit=10) == (tagged, plain)
