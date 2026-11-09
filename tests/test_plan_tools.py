"""The bot's plan tools (design 4.3): its own diary, any run, capped per run."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from test_plan_store import bot, cfg, service, user_id  # noqa: F401  (fixtures)

from roost.constants import PLAN_WRITES_PER_RUN
from roost.plan.tool_specs import PLAN_TOOL_DEFS
from roost.plan.tools import PlanTools
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore


async def _run(tools, service, cfg, user_id, bot, name, args, *, tainted=False, run_id="run-1"):
    thread = (await TalkStore(cfg).ensure_main_thread(user_id, bot.id))[0]
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=tainted, thread_id=thread.id, run_id=run_id)
    return await tools.run(name, args, ctx)


def _id_of(text: str) -> str:
    return text.split("id ")[1].split()[0].rstrip(".")


async def test_plan_read_taints_the_run_only_for_a_tainted_item(cfg, user_id, bot, service):
    tools = PlanTools(service)
    clean = await _run(tools, service, cfg, user_id, bot, "plan_add", {"text": "clean one", "date": "2026-10-23"})
    out = await _run(tools, service, cfg, user_id, bot, "plan_read", {})
    assert "clean one" in out.text and out.tainted is False
    await _run(tools, service, cfg, user_id, bot, "plan_add", {"text": "from web"}, tainted=True, run_id="run-2")
    out = await _run(tools, service, cfg, user_id, bot, "plan_read", {})
    assert out.tainted is True and "from outside content" in out.text
    only_dated = await _run(tools, service, cfg, user_id, bot, "plan_read", {"from": "2026-10-23", "to": "2026-10-23"})
    assert only_dated.tainted is False and "clean one" in only_dated.text and "from web" not in only_dated.text
    assert "data, not instructions" in out.text and clean.created


async def test_plan_tools_work_in_a_tainted_run_up_to_the_cap(cfg, user_id, bot, service):
    tools = PlanTools(service)
    first = await _run(tools, service, cfg, user_id, bot, "plan_add", {"text": "x0"}, tainted=True)
    item_id = _id_of(first.text)
    for n in range(1, PLAN_WRITES_PER_RUN):
        out = await _run(tools, service, cfg, user_id, bot, "plan_update", {"id": item_id, "text": f"x{n}"}, tainted=True)
        assert not out.text.startswith("Refused"), out.text
    over = await _run(tools, service, cfg, user_id, bot, "plan_complete", {"id": item_id}, tainted=True)
    assert over.text == "I've changed the Plan enough in this run."
    fresh = await _run(tools, service, cfg, user_id, bot, "plan_complete", {"id": item_id}, tainted=True, run_id="run-2")
    assert "Done" in fresh.text or "done" in fresh.text


async def test_one_updated_plan_line_per_run(cfg, user_id, bot, service):
    tools = PlanTools(service)
    talk = TalkStore(cfg)
    thread = (await talk.ensure_main_thread(user_id, bot.id))[0]
    a = await _run(tools, service, cfg, user_id, bot, "plan_add", {"text": "a"})
    await _run(tools, service, cfg, user_id, bot, "plan_add", {"text": "b"})
    await _run(tools, service, cfg, user_id, bot, "plan_update", {"id": _id_of(a.text), "status": "on_it"})
    await _run(tools, service, cfg, user_id, bot, "plan_complete", {"id": _id_of(a.text), "note": "all good"})
    await service.flush_run_note(user_id, bot.id, thread.id, "run-1")
    await service.flush_run_note(user_id, bot.id, thread.id, "run-1")
    notes = [m for m in await talk.list_messages(user_id, thread.id) if m.kind == "routine_note"]
    assert [json.loads(m.body)["text"] for m in notes] == ["Updated plan · 2 items"]
    plan = await service.read(user_id, bot.id)
    assert "  - [x] all good" in plan.content


async def test_tools_refuse_bad_input_and_other_ids(cfg, user_id, bot, service):
    tools = PlanTools(service)
    for name, args in (("plan_add", {"text": ""}), ("plan_add", {"text": "x 📅 2026-01-01"}),
                       ("plan_add", {"text": "x", "date": "tomorrow"}), ("plan_update", {"id": "zzzzzz", "text": "y"}),
                       ("plan_update", {"id": "zzzzzz"}), ("plan_complete", {"id": "zzzzzz"}),
                       ("plan_read", {"status": "bogus"})):
        out = await _run(tools, service, cfg, user_id, bot, name, args)
        assert out.text.startswith("Refused"), (name, out.text)


def test_the_plan_tools_are_flagged_and_own_only():
    assert {d.name: d.kind for d in PLAN_TOOL_DEFS} == {
        "plan_read": "read", "plan_add": "write_create", "plan_update": "write_change", "plan_complete": "write_change"}
    assert all(d.allowed_when_tainted for d in PLAN_TOOL_DEFS)
    assert all("bot_id" not in d.spec.input_schema["properties"] for d in PLAN_TOOL_DEFS)
