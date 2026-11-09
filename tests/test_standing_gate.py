"""The gate's standing path (Steps 2 and 3): ``standing_ok`` from the pure judge is re-checked live (revoked, ended,
count used up) and by the Fable check before the act runs, so it can only stay ``do`` or become the hard-floor ask.
One audit row per decision, with the final reason; the count moves only for a committing act Fable said fits."""

from __future__ import annotations

from dataclasses import replace

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolSpec, TurnDone
from roost.routines.models import RoutineDraft
from roost.routines.schedule import parse_schedule
from roost.routines.store import RoutineStore
from roost.standing.guard import StandingGuard
from roost.standing.models import PermissionIn, StandingState
from roost.standing.store import PermissionStore
from roost.talk.gate import Gate, GateContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef
from roost.work.runs import madrid_today
from team_helpers import make_bot

_EMPTY = {"type": "object", "properties": {}}
_CATALOG = {**CATALOG, **{n: ToolDef(ToolSpec(n, n, _EMPTY), "act") for n in ("click", "type", "press_key")}}
_FENCE = SiteFence(frozenset({"x.com"}))
INSTRUCTIONS = "Every Monday post the weekly update on x.com."


class Saying:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        yield TextDelta(self.reply)
        yield TurnDone("end_turn")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _today() -> str:
    return madrid_today(datetime.now(timezone.utc))


async def _setup(cfg, max_per_day: int = 1):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Poster")
    routine = await RoutineStore(cfg, TalkStore(cfg)).create(user.id, RoutineDraft(
        bot_id=bot.id, name="Weekly post", instructions=INSTRUCTIONS,
        schedule=parse_schedule({"kind": "times", "days": [1], "times": ["10:00"]}), created_by="user"))
    store = PermissionStore(cfg)
    until = date.fromisoformat(_today()) + timedelta(days=7)
    made = await store.create(user.id, routine.id, PermissionIn(host="x.com", action="post", max_per_day=max_per_day,
                                                                until=until))
    return user.id, bot.id, routine.id, store, made


def _target(text: str, **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="button", text=text, tag="button", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False)
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(text: str = "Post") -> ActResolution:
    target = _target(text)
    return ActResolution(tool="click", url="https://x.com/home", host="x.com", target=target, point=(140, 215),
                         covered_by="", nav_host="", commit=commit_class(target))


def _typing() -> ActResolution:
    box = _target("What is happening?", kind="field", tag="textarea", editable=True)
    return ActResolution(tool="type", url="https://x.com/home", host="x.com", target=box, point=(140, 215),
                         covered_by="", nav_host="", commit="browsing", text_ok=False)


async def _ctx(store: PermissionStore, user_id: str, routine_id: str) -> GateContext:
    live = await store.live_for_routine(user_id, routine_id, _today())
    standing = StandingState(routine_id=routine_id, instructions=INSTRUCTIONS, permissions=live, today=_today())
    state = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True, standing=standing)
    return GateContext(allowed=frozenset(_CATALOG), tainted=True, approval=state, fence=_FENCE)


def _audit(cfg) -> list[tuple[str, str]]:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        return con.execute("SELECT decision, reason FROM audit ORDER BY id").fetchall()
    finally:
        con.close()


def _gate(cfg, worker) -> Gate:
    return Gate(cfg, catalog=_CATALOG, standing=StandingGuard(PermissionStore(cfg), worker))


async def test_a_fitting_post_runs_and_uses_one_of_the_days_count(cfg):
    user_id, bot_id, routine_id, store, made = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)
    worker = Saying("fits")
    verdict = await _gate(cfg, worker).decide(user_id, bot_id, "click", {"expect": "posted"}, ctx, act=_click())
    assert (verdict.decision, verdict.reason) == ("do", "standing_ok") and worker.calls == 1
    assert _audit(cfg) == [("do", "standing_ok")]
    again = await _gate(cfg, worker).decide(user_id, bot_id, "click", {"expect": "posted"}, ctx, act=_click())
    assert (again.decision, again.reason) == ("ask", "hard_floor")      # the day's one is used, though ctx said 1
    assert await store.is_live(user_id, made.id, _today()) is False


async def test_fable_saying_ask_turns_it_into_the_hard_floor_ask_and_keeps_the_count(cfg):
    user_id, bot_id, routine_id, store, made = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)
    verdict = await _gate(cfg, Saying("ask")).decide(user_id, bot_id, "click", {}, ctx, act=_click())
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")
    assert _audit(cfg) == [("ask", "hard_floor")]
    assert await store.is_live(user_id, made.id, _today()) is True


async def test_a_revoke_holds_at_once_mid_run(cfg):
    user_id, bot_id, routine_id, store, made = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)
    await store.revoke(user_id, routine_id, made.id)
    worker = Saying("fits")
    verdict = await _gate(cfg, worker).decide(user_id, bot_id, "click", {}, ctx, act=_click())
    assert verdict.decision == "ask" and worker.calls == 0


async def test_typing_needs_no_permission_and_uses_no_count(cfg):
    """Owner, 2026-11-03: typing never asks, so no standing permission is used for it."""
    user_id, bot_id, routine_id, store, made = await _setup(cfg)
    ctx = replace(await _ctx(store, user_id, routine_id), fence=SiteFence(frozenset()))   # off a trusted site
    gate = _gate(cfg, ScriptedWorker())
    verdict = await gate.decide(user_id, bot_id, "type", {"text": "This week: v2 shipped."}, ctx, act=_typing())
    assert (verdict.decision, verdict.reason) == ("do", "allowed")
    assert await store.is_live(user_id, made.id, _today()) is True


async def test_a_check_that_fails_to_run_asks(cfg, monkeypatch):
    user_id, bot_id, routine_id, store, _ = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)

    async def broken(*_args, **_kw):
        raise RuntimeError("db gone")

    guard = StandingGuard(PermissionStore(cfg), Saying("fits"))
    monkeypatch.setattr(guard, "confirm", broken)
    gate = Gate(cfg, catalog=_CATALOG, standing=guard)
    verdict = await gate.decide(user_id, bot_id, "click", {}, ctx, act=_click())
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


async def test_with_no_card_to_show_a_failed_check_is_never(cfg):
    user_id, bot_id, routine_id, store, _ = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)
    ctx = GateContext(allowed=ctx.allowed, tainted=True, fence=_FENCE,
                      approval=ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=False,
                                             standing=ctx.approval.standing))
    verdict = await _gate(cfg, Saying("ask")).decide(user_id, bot_id, "click", {}, ctx, act=_click())
    assert (verdict.decision, verdict.reason) == ("never", "needs_your_ok")


async def test_the_default_gate_uses_the_scripted_worker_in_tests(cfg):
    user_id, bot_id, routine_id, store, _ = await _setup(cfg)
    ctx = await _ctx(store, user_id, routine_id)
    verdict = await Gate(cfg, catalog=_CATALOG).decide(user_id, bot_id, "click", {}, ctx, act=_click())
    assert (verdict.decision, verdict.reason) == ("do", "standing_ok")
