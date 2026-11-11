"""A routine's own model (owner, 2026-11-09, docs/plans/2026-11-09-roost-tool-groups.md §2): the run uses it, the
user or the bot sets it, and two failed runs in a row on it go back to the bot's model with a line in the chat."""

from __future__ import annotations

import json

import pytest

from roost.llm.registry import DEFAULT_BOT_MODEL, HAIKU, OPUS, resolve_routine_model
from roost.routines.models import RoutineDraft, RoutinePatch
from roost.routines.service import Refused, routine_model
from test_routine_trust import NOW, SCHEDULE, FakeClock, Rigged, _say  # noqa: F401 — the shared routine rig
from test_routine_trust import bot, cfg, clock, user_id  # noqa: F401 — fixtures


def test_routine_model_reads_ids_short_names_and_same():
    assert routine_model("haiku") == HAIKU.id
    assert routine_model(OPUS.id) == OPUS.id
    assert routine_model("Same") is None and routine_model(None) is None and routine_model("") is None
    with pytest.raises(Refused):
        routine_model("gpt-5")


def test_resolve_routine_model_prefers_the_routine_then_the_bot():
    assert resolve_routine_model(HAIKU.id, None) == HAIKU.id
    assert resolve_routine_model(None, OPUS.id) == OPUS.id
    assert resolve_routine_model(None, None) == DEFAULT_BOT_MODEL
    assert resolve_routine_model("not-a-model", OPUS.id) == OPUS.id


async def test_the_store_keeps_the_model_and_a_change_starts_the_count_over(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": []})
    routine = await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Prices", instructions="Check.", schedule=SCHEDULE, created_by="user", model=HAIKU.id))
    assert routine.model == HAIKU.id and routine.model_failures == 0
    counted = await rig.routines.note_model_run(user_id, routine.id, ok=False)
    assert counted.model_failures == 1
    changed = await rig.routines.update(user_id, routine.id, RoutinePatch({"model": OPUS.id}))
    assert changed.model == OPUS.id and changed.model_failures == 0
    assert (await rig.routines.update(user_id, routine.id, RoutinePatch({"model": None}))).model is None


async def test_a_routine_runs_on_its_own_model(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("Quiet day.")]})
    await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Prices", instructions="Check.", schedule=SCHEDULE, created_by="user", model=HAIKU.id))
    await rig.fire()
    assert rig.model.requests[-1].model == HAIKU.id


async def test_a_routine_with_no_model_runs_on_the_bot_model(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("Quiet day.")]})
    await rig.routine(user_id, bot)
    await rig.fire()
    assert rig.model.requests[-1].model == DEFAULT_BOT_MODEL


async def test_two_failures_in_a_row_go_back_to_the_bot_model_and_say_so(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": []}, fails=2)      # the run and its one retry both fail
    routine = await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Prices", instructions="Check.", schedule=SCHEDULE, created_by="user", model=HAIKU.id))
    await rig.fire()
    after = await rig.routines.get(user_id, routine.id)
    assert after.model is None and after.model_failures == 0
    thread, _ = await rig.talk.ensure_main_thread(user_id, bot.id)
    notes = [json.loads(m.body) for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "routine_note"]
    assert any(n["verb"] == "model_fallback" and "Haiku 5.5" in n["text"] for n in notes)


async def test_a_good_run_starts_the_count_over(cfg, clock, user_id, bot):
    rig = Rigged(cfg, clock, {"Scout": [_say("Quiet day.")]}, fails=1)   # fails once, the retry works
    routine = await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Prices", instructions="Check.", schedule=SCHEDULE, created_by="user", model=HAIKU.id))
    await rig.fire()
    after = await rig.routines.get(user_id, routine.id)
    assert after.model == HAIKU.id and after.model_failures == 0
