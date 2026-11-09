"""SkillStore (Skills Task 2): sealed, scoped, unique folded names, revisions and per-bot switches."""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from roost.config import load_config
from roost.constants import SKILL_NAME_MAX, SKILLS_PER_USER_MAX
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.records.revision import RevisionConflict
from roost.skills.models import SkillDraft, SkillPatch
from roost.skills.names import fold_name
from roost.skills.store import SkillNameTaken, SkillsFull, SkillStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _raw(cfg, sql, params=()):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _draft(name="Post on X", use_when="the user wants a post on X", body="1. Open X\n2. Write it"):
    return SkillDraft(name=name, use_when=use_when, body=body)


async def _user(cfg, name="alice"):
    return (await register_user(cfg, name, "pw-123456")).id


async def _add(store, user_id, draft=None, **kw):
    options = {"origin": "user", "tainted": False, "created_by_bot": None} | kw
    return await store.create(user_id, draft or _draft(), **options)


async def test_create_seals_every_text_column(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    skill = await _add(store, uid)
    assert skill.name == "Post on X" and skill.revision == 1 and skill.origin == "user"
    name, use_when, body, key = _raw(cfg, "SELECT name, use_when, body, name_key FROM skills")[0]
    for value in (name, use_when, body):
        assert value.startswith("enc:v2:")
    assert key != "Post on X" and "post" not in key.lower()


async def test_names_fold_case_and_accents(cfg):
    assert fold_name("Post on X") == fold_name("post on x") == fold_name("Pöst  on X")
    store = SkillStore(cfg)
    uid = await _user(cfg)
    await _add(store, uid)
    for clash in ("post on x", "Pöst on X"):
        with pytest.raises(SkillNameTaken):
            await _add(store, uid, _draft(name=clash))


async def test_name_taken_is_refused(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    first = await _add(store, uid)
    with pytest.raises(SkillNameTaken) as caught:
        await _add(store, uid)
    assert caught.value.existing.id == first.id
    other = await _add(store, uid, _draft(name="Weekly SEO check"))
    with pytest.raises(SkillNameTaken):
        await store.update(uid, other.id, SkillPatch(name="post on X"), base_revision=1, tainted=False)


async def test_the_per_user_cap(cfg, monkeypatch):
    monkeypatch.setattr("roost.skills.store.SKILLS_PER_USER_MAX", 2)
    store = SkillStore(cfg)
    uid, bob = await _user(cfg), await _user(cfg, "bob")
    await _add(store, uid, _draft(name="One"))
    await _add(store, uid, _draft(name="Two"))
    with pytest.raises(SkillsFull):
        await _add(store, uid, _draft(name="Three"))
    assert (await _add(store, bob, _draft(name="Three"))).name == "Three"
    assert SKILLS_PER_USER_MAX == 100


async def test_update_is_compare_and_swap(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    skill = await _add(store, uid, tainted=True)
    saved = await store.update(uid, skill.id, SkillPatch(body="New steps"), base_revision=1, tainted=False)
    assert saved.revision == 2 and saved.body == "New steps" and saved.name == "Post on X" and not saved.tainted
    with pytest.raises(RevisionConflict) as caught:
        await store.update(uid, skill.id, SkillPatch(body="Stale"), base_revision=1, tainted=False)
    assert caught.value.current.body == "New steps"
    assert await store.update(uid, "missing", SkillPatch(body="x"), base_revision=1, tainted=False) is None


async def test_another_users_skill_is_invisible(cfg):
    store = SkillStore(cfg)
    alice, bob = await _user(cfg), await _user(cfg, "bob")
    skill = await _add(store, alice)
    bob_bot = await make_bot(cfg, bob, "Scout")
    assert await store.get(bob, skill.id) is None
    assert await store.get_by_name(bob, "Post on X") is None
    assert await store.list(bob) == ()
    assert await store.update(bob, skill.id, SkillPatch(body="x"), base_revision=1, tainted=False) is None
    assert await store.delete(bob, skill.id) is False
    assert await store.set_on(bob, bob_bot.id, skill.id, False) is False
    assert (await store.get(alice, skill.id)).body == skill.body


async def test_off_switch_round_trip(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    bot, other = await make_bot(cfg, uid, "Scout"), await make_bot(cfg, uid, "Ledger")
    skill = await _add(store, uid)
    assert await store.off_ids(uid, bot.id) == frozenset()
    assert await store.set_on(uid, bot.id, skill.id, False) is True
    assert await store.set_on(uid, bot.id, skill.id, False) is True
    assert await store.off_ids(uid, bot.id) == frozenset({skill.id})
    assert await store.off_ids(uid, other.id) == frozenset()
    assert await store.set_on(uid, bot.id, skill.id, True) is True
    assert await store.off_ids(uid, bot.id) == frozenset()
    assert await store.set_on(uid, "no-bot", skill.id, False) is False


async def test_get_by_name_uses_the_key(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    skill = await _add(store, uid)
    assert (await store.get_by_name(uid, "  POST ON x ")).id == skill.id
    assert await store.get_by_name(uid, "Post on Y") is None


async def test_list_is_in_folded_name_order_and_delete_works(cfg):
    store = SkillStore(cfg)
    uid = await _user(cfg)
    for name in ("banana", "Apple", "cherry"):
        await _add(store, uid, _draft(name=name))
    names = [s.name for s in await store.list(uid)]
    assert names == ["Apple", "banana", "cherry"]
    first = (await store.list(uid))[0]
    assert await store.delete(uid, first.id) is True
    assert await store.delete(uid, first.id) is False


def test_the_draft_checks_its_fields():
    assert _draft(name="  Spaced  ").name == "Spaced"
    for bad in ({"name": "two\nlines"}, {"use_when": "a\nb"}, {"name": ""}, {"name": "x" * (SKILL_NAME_MAX + 1)},
                {"body": ""}):
        with pytest.raises(ValidationError):
            _draft(**bad)
    with pytest.raises(ValidationError) as caught:
        _draft(body="use token=sk-abcdefghijklmnop1234")
    assert "sk-abcdef" not in str(caught.value) and "Not saved" in str(caught.value)
    with pytest.raises(ValidationError):
        SkillPatch(name="a\nb")
    assert SkillPatch(body="x").name is None
