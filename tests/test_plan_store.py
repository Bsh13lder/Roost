"""The Plan store and service (design 4.2, 4.4): sealed, CAS, per-item taint."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.plan import grammar
from roost.plan.service import PlanService
from roost.plan.store import PlanStore
from roost.records.revision import RevisionConflict
from roost.talk.store import TalkStore
from team_helpers import make_bot

NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def bot(cfg, user_id):
    return await make_bot(cfg, user_id, "Scout")


@pytest.fixture
def service(cfg):
    return PlanService(PlanStore(cfg), EventHub(cfg), BotStore(cfg), TalkStore(cfg), clock=lambda: NOW)


async def test_the_plan_is_sealed_and_made_on_first_open(cfg, user_id, bot, service):
    plan = await service.read(user_id, bot.id)
    assert (plan.content, plan.revision, plan.item_taint) == ("", 1, frozenset())
    saved = await service.put_text(user_id, bot.id, "- [ ] secret-plan-word\n", base_revision=1)
    assert saved.revision == 2 and "🆔" in saved.content
    con = sqlite3.connect(get_db_path(cfg))
    try:
        rows = con.execute("SELECT content, item_taint FROM bot_plans").fetchall()
    finally:
        con.close()
    assert len(rows) == 1 and all(v.startswith("enc:v2") for v in rows[0])
    assert "secret-plan-word" not in rows[0][0]


async def test_a_stale_revision_is_409_with_the_current_copy(user_id, bot, service, cfg):
    await service.put_text(user_id, bot.id, "- [ ] one\n", base_revision=1)
    with pytest.raises(RevisionConflict) as caught:
        await service.put_text(user_id, bot.id, "- [ ] two\n", base_revision=1)
    assert "one" in caught.value.current.content and caught.value.current.revision == 2
    with pytest.raises(RevisionConflict):
        await PlanStore(cfg).save(user_id, bot.id, "x", frozenset(), 1)


async def test_a_bot_write_never_clobbers_the_users_other_lines(user_id, bot, service):
    mine = "# Mine\n\nfree text 🔁 stays\n- [ ] user line #home 📅 2026-10-23\n"
    await service.put_text(user_id, bot.id, mine, base_revision=1)
    item = await service.bot_add(user_id, bot.id, text="bot line", run_key="r1", tainted=False)
    plan = await service.read(user_id, bot.id)
    assert plan.content.startswith("# Mine\n\nfree text 🔁 stays\n- [ ] user line #home 📅 2026-10-23 🆔 ")
    assert f"bot line 🆔 {item.id}" in plan.content


async def test_bot_writes_from_a_tainted_run_mark_only_those_items(user_id, bot, service):
    clean = await service.bot_add(user_id, bot.id, text="clean", run_key="r1", tainted=False)
    dirty = await service.bot_add(user_id, bot.id, text="dirty", run_key="r2", tainted=True)
    assert (await service.read(user_id, bot.id)).item_taint == frozenset({dirty.id})
    await service.bot_complete(user_id, bot.id, clean.id, note=None, run_key="r3", tainted=True)
    assert (await service.read(user_id, bot.id)).item_taint == frozenset({dirty.id, clean.id})


async def test_a_user_edit_clears_that_items_taint(user_id, bot, service):
    a = await service.bot_add(user_id, bot.id, text="alpha", run_key="r1", tainted=True)
    b = await service.bot_add(user_id, bot.id, text="beta", run_key="r1", tainted=True)
    plan = await service.read(user_id, bot.id)
    # PUT with beta's line untouched and alpha's rewritten
    edited = plan.content.replace("alpha", "alpha reworded")
    saved = await service.put_text(user_id, bot.id, edited, base_revision=plan.revision)
    assert saved.item_taint == frozenset({b.id}) and a.id not in saved.item_taint
    # patching beta clears it too
    patched = await service.patch_item(user_id, bot.id, b.id, saved.revision, {"status": "on_it"})
    assert patched.item_taint == frozenset()


async def test_patch_an_item_by_id(user_id, bot, service):
    item = await service.bot_add(user_id, bot.id, text="a", run_key="r", tainted=False)
    plan = await service.read(user_id, bot.id)
    out = await service.patch_item(user_id, bot.id, item.id, plan.revision,
                                   {"status": "done", "date": "2026-10-30", "time": "09:15", "tags": ["#x"], "text": "b"})
    assert f"- [x] b ⏰ 09:15 #x 📅 2026-10-30 ✅ 2026-10-22 🆔 {item.id}" in out.content
    assert await service.patch_item(user_id, bot.id, "nope00", out.revision, {"status": "done"}) is None
    with pytest.raises(grammar.PlanRefused):
        await service.patch_item(user_id, bot.id, item.id, out.revision, {"date": "2026-99-99"})
    with pytest.raises(grammar.PlanRefused):
        await service.patch_item(user_id, bot.id, item.id, out.revision, {"text": "bad 📅 2026-01-01"})
    with pytest.raises(RevisionConflict):
        await service.patch_item(user_id, bot.id, item.id, 1, {"status": "planned"})
    cleared = await service.patch_item(user_id, bot.id, item.id, out.revision, {"date": None})
    assert "📅" not in cleared.content


async def test_another_users_plan_is_not_found(cfg, user_id, bot, service):
    other = (await register_user(cfg, "bob", "pw-123456")).id
    assert await service.read(other, bot.id) is None
    assert await service.put_text(other, bot.id, "- [ ] x\n", base_revision=1) is None
    assert await service.patch_item(other, bot.id, "abcdef", 1, {"status": "done"}) is None
    assert await service.items_for_prompt(other, bot.id) is None
