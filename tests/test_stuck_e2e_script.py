"""The Porter script from the E2E (web/e2e/fixtures/team-script.json) against
the pages FakeDesk serves (design §5, R11): stuck on the sign-in wall, then done
after Take control and Give it back. A fast mirror of web/e2e/stuck.spec.ts, so a
change to the script, the fake pages or the card's words fails here before the E2E runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.control import ControlLock
from roost.desk.fake_pages import LOGIN_URL, SIGNED_IN
from roost.desk.main_browser import FakeMainBrowser
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.stuck.models import CardState
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.talk.runner import TurnRunner
from team_helpers import RecordingModel, Rig, make_bot, make_rig, send, wait_idle

E2E_SCRIPT = Path(__file__).resolve().parents[1] / "web" / "e2e" / "fixtures" / "team-script.json"
# The words web/e2e/stuck.spec.ts types and waits for.
E2E_REQUEST = "check my orders on https://login.example/"
E2E_CARD_LINE = "I'm stuck on login.example: a sign-in page."
E2E_CONTINUE_LINE = "I cleared the block on login.example."
E2E_REPLY = "Signed in and done."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _e2e_rig(cfg, lock: ControlLock, stuck: StuckStore) -> Rig:
    """The gateway's wiring: the E2E's script, and one control lock and card store shared with StuckService."""
    base = make_rig(cfg, RecordingModel(ScriptedTeamModel.from_file(E2E_SCRIPT)))
    runner = TurnRunner(cfg, base.bots, base.talk, base.events, base.desks, base.model, ActivityBoard(),
                        control=lock, stuck=stuck)
    return Rig(runner=runner, bots=base.bots, talk=base.talk, events=base.events, desks=base.desks, model=base.model)


async def test_the_e2e_script_gets_porter_stuck_on_the_sign_in_page_then_done_after_give_it_back(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Porter")
    lock, stuck = ControlLock(), StuckStore(cfg)
    rig = _e2e_rig(cfg, lock, stuck)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, E2E_REQUEST)
    await wait_idle(rig.runner, timeout=8)

    card = await stuck.open_for_bot(user_id, bot.id)
    assert card is not None
    assert (card.reason, card.host, card.request) == ("login", "login.example", E2E_REQUEST)
    assert len(rig.model.requests) == 2                # the run read the page, asked with request_sign_in, stopped
    assert (await BotStore(cfg).get(user_id, bot.id)).status == BotStatus.STUCK
    [card_message] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert json.loads(card_message.body)["line"].startswith(E2E_CARD_LINE)

    lock.take(bot.id)                                            # the card's Take control
    service = StuckService(stuck, rig.talk, rig.events, rig.runner, lock, FakeMainBrowser())
    assert (await service.clear(user_id, card.id)).state == CardState.CLEARED   # Give it back
    assert lock.held(bot.id) is None
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    [continue_line] = [m for m in messages if m.kind == "card_answer"]
    assert continue_line.role == "user" and continue_line.body.startswith(E2E_CONTINUE_LINE)
    assert [m.body for m in messages if m.role == "bot" and m.kind == "text"] == [E2E_REPLY]
    assert SIGNED_IN.text in [t.text for t in rig.model.requests[-1].turns if t.role == "tool"][-1]
    assert rig.desks.for_bot(bot.id).open_page_calls == [LOGIN_URL]   # read again, never reopened
    assert await stuck.open_for_bot(user_id, bot.id) is None
    assert (await BotStore(cfg).get(user_id, bot.id)).status == BotStatus.RESTING
