"""Stuck always says why and what next (chat-feel Task 7).

Audit. A status turns Stuck in two places only (``grep -rn "BotStatus.STUCK" roost``):
  1. ``TurnRunner._idle_status``: an open Stuck card (also reached by a boot restore and a ``settle``).
  2. ``RoutineHooks._go_stuck``: an unattended routine run that met a wall or errored twice (no card).
Both now build their words with ``roost.stuck.texts``: ``stuck_status_line(card)`` for a card, and
``routine_stuck_line`` (the same shape) for a routine.
Card lines audited: every ``REASON_WORDS`` key x host present / empty x ``suggest_main_browser`` x blocked.
Frames audited: a stay begins, a bot already Stuck before its run, a settle while Stuck, a boot restore.
A reload (``GET /api/bots``) reads the open card, not the empty ``ActivityBoard``.
"""

from __future__ import annotations

import itertools
import pathlib
import re
from dataclasses import replace

import httpx
import pytest

from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.stuck.models import CardDraft, CardState, StuckCard
from roost.stuck.store import StuckStore
from roost.stuck.texts import (
    NEXT_STEP_BLOCKED, NEXT_STEP_TAKE_CONTROL, REASON_WORDS, blocked_line, routine_stuck_line, stuck_status_line,
)
from team_helpers import frames_so_far, make_bot, make_rig, say, send, team_model, wait_idle

SHOP = "https://shop.example/"
CHALLENGE = PageText(url=SHOP, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)
O = {"Origin": "http://127.0.0.1:18800"}
NEXT_STEPS = (NEXT_STEP_TAKE_CONTROL, NEXT_STEP_BLOCKED)
ROOST_DIR = pathlib.Path(__file__).resolve().parent.parent / "roost"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture(autouse=True)
def _no_challenge_wait(monkeypatch):
    import roost.talk.tool_runner as tool_runner_module
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _card(reason: str, url: str, state: CardState = CardState.OPEN) -> StuckCard:
    return StuckCard(
        id="c", user_id="u", bot_id="b", thread_id="t", work_item_id=None, reason=reason, url=url,
        note="approve the payment" if reason == "asked" else "", request="pay", suggest_main_browser=False,
        tainted=False, main_opened=False, state=state, answer_item_id=None, created_at="", closed_at=None)


def test_every_stuck_line_has_a_reason_and_a_next_step():
    for reason, url, main, state in itertools.product(
            REASON_WORDS, (SHOP, ""), (False, True), (CardState.OPEN, CardState.BLOCKED)):
        card = replace(_card(reason, url, state), suggest_main_browser=main)
        line = stuck_status_line(card)
        words = card.note if reason == "asked" else REASON_WORDS[reason]
        assert words in line, line
        assert line.endswith(NEXT_STEPS), line
        assert line.startswith(("Stuck", "Needs your help")), line
        if url:
            assert "shop.example" in line
    assert stuck_status_line(_card("login", SHOP)) == "Stuck on shop.example: a sign-in page. Take control to clear it."
    assert stuck_status_line(_card("asked", "")) == "Needs your help: approve the payment. Take control to clear it."
    assert stuck_status_line(_card("code", "")) == "Stuck: a code check. Take control to clear it."


def test_a_blocked_line_names_the_next_step():
    assert blocked_line("shop.example", "pay").startswith("Blocked: shop.example keeps stopping me.")
    assert blocked_line("shop.example", "pay").endswith(NEXT_STEP_BLOCKED)


def test_a_routine_stuck_line_has_a_reason_and_a_next_step():
    assert routine_stuck_line("shop.example", "Morning news").startswith("Stuck on shop.example: ")
    line = routine_stuck_line("", "Morning news")
    assert "Morning news" in line and line.startswith("Stuck: ") and line.endswith("happened.")


async def _blocked(cfg, user_id, script):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": script}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    return rig, bot, thread


def _open_shop():
    return [ToolCallRequested(id="p", name="open_page", arguments={"url": SHOP}), TurnDone("tool_use")]


def _stuck_frames(frames):
    return [f for f in frames if f["type"] == "bot_status" and f["status"] == "stuck"]


async def test_the_status_frame_always_carries_the_line(cfg, user_id):
    rig, bot, thread = await _blocked(cfg, user_id, [_open_shop(), say("Still waiting.")])
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")       # a stay begins
    await wait_idle(rig.runner, timeout=8)
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    line = stuck_status_line(card)
    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [line]

    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, "still there?")                       # already Stuck before the run
    await wait_idle(rig.runner, timeout=8)
    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [line]

    sub = rig.events.subscribe(user_id)
    await rig.runner.settle(user_id, bot.id)                                          # a settle while Stuck
    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [line]


async def test_a_reload_shows_the_reason(cfg, user_id):
    app = create_app()
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await app.state.talk.create_thread(user_id, bot.id)
    block = Block(reason="login", url=SHOP, host=host_of_url(SHOP))
    card = await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, block=block, request="pay", tainted=False))
    await app.state.bots.set_status(user_id, bot.id, BotStatus.STUCK)
    app.state.activity_board.set(bot.id, None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"},
                                  headers=O)).status_code == 200
        listed = (await client.get("/api/bots")).json()
        one = (await client.get(f"/api/bots/{bot.id}")).json()
    assert [b["activity"] for b in listed if b["id"] == bot.id] == [stuck_status_line(card)]
    assert one["activity"] == stuck_status_line(card)


async def test_a_restart_republishes_the_line(cfg, user_id):
    rig, bot, thread = await _blocked(cfg, user_id, [_open_shop()])
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    assert (await rig.bots.get(user_id, bot.id)).status is BotStatus.STUCK       # the database already says Stuck
    sub = rig.events.subscribe(user_id)

    await rig.runner.restore_stuck_on_boot()

    assert [f["activity"] for f in _stuck_frames(await frames_so_far(sub))] == [stuck_status_line(card)]


def test_only_idle_status_sets_stuck():
    """Source scan: ``BotStatus.STUCK`` is set or returned only by ``_idle_status`` (and the routine hook's
    ``_go_stuck``, which has no card); the rest is the model and the label tables."""
    allowed = {"roost/talk/runner.py", "roost/routines/hooks.py", "roost/bots/models.py"}
    hits = []
    for path in ROOST_DIR.rglob("*.py"):
        rel = str(path.relative_to(ROOST_DIR.parent))
        for number, text in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"set_status\(.*STUCK|return BotStatus\.STUCK", text) and rel not in allowed:
                hits.append(f"{rel}:{number}")
    assert hits == []
    runner = (ROOST_DIR / "talk/runner.py").read_text()
    assert len(re.findall(r"return BotStatus\.STUCK, card", runner)) == 1


async def test_the_live_snapshot_shows_the_reason_too(cfg, user_id):
    """A page that connects (or reconnects) while a bot is Stuck must not wipe the reason from its header."""
    from roost.gateway.routes.events import _FrameSender

    class _Socket:
        sent: list = []

        async def send_json(self, frame):
            self.sent = [*self.sent, frame]

    app = create_app()
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await app.state.talk.create_thread(user_id, bot.id)
    card = await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None,
        block=Block(reason="login", url=SHOP, host=host_of_url(SHOP)), request="pay", tainted=False))
    await app.state.bots.set_status(user_id, bot.id, BotStatus.STUCK)
    socket = _Socket()
    await _FrameSender(socket).send_snapshot(app.state.events, app.state, user_id)
    assert [b["activity"] for b in socket.sent[0]["bots"] if b["id"] == bot.id] == [stuck_status_line(card)]
