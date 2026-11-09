"""The bot sets a watch only through the routine tools: directly in a clean run of your own chat, and only on a page
your own messages named; anywhere else it proposes and your Approve writes it."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from roost.bots.store import BotStore
from roost.computer_use.text_source import your_messages
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.routines.direct_texts import TAINTED_TEXT, WATCH_NOT_NAMED_TEXT
from roost.routines.direct_tools import RoutineWrites
from roost.routines.models import RoutineDraft
from roost.routines.proposals import ProposalService, ProposalStore
from roost.routines.runs import RoutineRunStore
from roost.routines.schedule import parse_schedule
from roost.routines.service import RoutineService
from roost.routines.store import RoutineStore
from roost.routines.tool_specs import CREATE_ROUTINE_SPEC, PROPOSE_ROUTINE_SPEC, UPDATE_ROUTINE_SPEC
from roost.routines.tools import RoutineTools
from roost.routines.watch_models import Watch
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from team_helpers import make_bot

NOW = datetime(2026, 11, 4, 13, 0, tzinfo=timezone.utc)
DAILY = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["09:00"]}
WATCH = {"url": "https://web.whatsapp.com/", "part": "the physio chat", "every_min": 5}
ASK = "Watch my physio chat on WhatsApp and tell me when Ana writes."


class Rig:
    def __init__(self, cfg):
        self.talk, self.events, self.bots = TalkStore(cfg), EventHub(cfg), BotStore(cfg)
        self.routines = RoutineStore(cfg, self.talk, clock=lambda: NOW)
        self.service = RoutineService(self.routines, RoutineRunStore(cfg), self.bots, self.talk, self.events,
                                      None, None, clock=lambda: NOW)
        self.writes = RoutineWrites(self.routines, self.service,
                                    owner_texts=lambda u, t: your_messages(cfg, u, t))
        self.proposals = ProposalService(ProposalStore(cfg), self.routines, self.talk, self.events,
                                         writer=self.service, clock=lambda: NOW)
        self.tools = RoutineTools(self.routines, self.proposals)

    async def ctx(self, user_id, bot, said: str | None = ASK, **kw) -> RecordContext:
        thread, _ = await self.talk.ensure_main_thread(user_id, bot.id)
        if said:
            await self.talk.add_message(user_id, thread.id, "user", said)
        return RecordContext(user_id=user_id, bot_id=bot.id, thread_id=thread.id, user_started=True,
                             **{"tainted": False, **kw})


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
    return await make_bot(cfg, user_id, "Gela")


@pytest.fixture
def rig(cfg):
    return Rig(cfg)


def _create(**extra) -> dict:
    return {"name": "Watch physio chat", "instructions": "Tell me what Ana wrote.", "schedule": DAILY, **extra}


def test_the_tool_specs_offer_a_watch():
    for spec in (CREATE_ROUTINE_SPEC, UPDATE_ROUTINE_SPEC, PROPOSE_ROUTINE_SPEC):
        assert "watch" in spec.input_schema["properties"]


async def test_a_clean_run_of_your_chat_sets_a_watch_on_a_site_you_named(rig, user_id, bot):
    ctx = await rig.ctx(user_id, bot)
    done = await rig.writes.run("create_routine", _create(watch=WATCH), ctx)
    assert not done.failed, done.text
    assert "runs only when the page changes" in done.text
    routine = (await rig.routines.list_for_bot(user_id, bot.id))[0]
    assert routine.watch == Watch(url="https://web.whatsapp.com/", part="the physio chat", every_min=5)


async def test_a_page_you_never_named_is_refused(rig, user_id, bot):
    ctx = await rig.ctx(user_id, bot, said="Tell me when the price drops.")
    done = await rig.writes.run("create_routine", _create(watch={**WATCH, "url": "https://shop.evil/"}), ctx)
    assert done.failed and done.text == WATCH_NOT_NAMED_TEXT
    assert await rig.routines.list_for_bot(user_id, bot.id) == ()


async def test_a_bad_watch_is_refused_before_any_card(rig, user_id, bot):
    ctx = await rig.ctx(user_id, bot)
    pending = await rig.writes.prepare("create_routine", _create(watch={**WATCH, "every_min": 1}), ctx)
    assert isinstance(pending, str) and "minutes" in pending


async def test_the_card_shows_the_watched_page(rig, user_id, bot):
    ctx = await rig.ctx(user_id, bot)
    pending = await rig.writes.prepare("create_routine", _create(watch=WATCH), ctx)
    assert "https://web.whatsapp.com/" in pending.detail and "the physio chat" in pending.detail


async def test_update_routine_stops_and_starts_a_watch(rig, user_id, bot):
    routine = await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Physio", instructions="Read.", schedule=parse_schedule(DAILY), created_by="user"))
    ctx = await rig.ctx(user_id, bot)
    started = await rig.writes.run("update_routine", {"routine_id": routine.id, "watch": WATCH}, ctx)
    assert not started.failed and (await rig.routines.get(user_id, routine.id)).watch is not None
    stopped = await rig.writes.run("update_routine", {"routine_id": routine.id, "watch": {"off": True}}, ctx)
    assert not stopped.failed and (await rig.routines.get(user_id, routine.id)).watch is None


async def test_a_tainted_run_is_refused_and_proposes_instead(rig, user_id, bot):
    ctx = await rig.ctx(user_id, bot, tainted=True)
    refused = await rig.writes.run("create_routine", _create(watch=WATCH), ctx)
    assert refused.failed and refused.text == TAINTED_TEXT
    proposed = await rig.tools.run("propose_routine", _create(watch=WATCH), ctx)
    assert "approve" in proposed.text
    view = (await rig.proposals.list_open(user_id))[0]
    assert view.proposal.payload.watch.url == "https://web.whatsapp.com/"
    assert view.words.startswith("Only when https://web.whatsapp.com/ changes") and view.next == ()
    await rig.proposals.approve(user_id, view.proposal.id)
    made = (await rig.routines.list_for_bot(user_id, bot.id))[0]
    assert made.watch is not None and made.tainted


async def test_a_change_proposal_shows_the_watch_in_its_diff(rig, user_id, bot):
    routine = await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Physio", instructions="Read.", schedule=parse_schedule(DAILY), created_by="user"))
    ctx = await rig.ctx(user_id, bot, tainted=True)
    await rig.tools.run("propose_routine_change", {"routine_id": routine.id, "watch": WATCH}, ctx)
    view = (await rig.proposals.list_open(user_id))[0]
    assert [d["field"] for d in view.diff] == ["watch"]
    assert view.diff[0]["before"] == "Runs on its schedule"
    await rig.proposals.approve(user_id, view.proposal.id)
    assert (await rig.routines.get(user_id, routine.id)).watch is not None


async def test_list_routines_names_the_watch(rig, user_id, bot):
    await rig.routines.create(user_id, RoutineDraft(
        bot_id=bot.id, name="Physio", instructions="Read.", schedule=parse_schedule(DAILY), created_by="user",
        watch=Watch(url="https://web.whatsapp.com/", part="the physio chat", every_min=5)))
    listed = await rig.tools.run("list_routines", {}, await rig.ctx(user_id, bot, said=None))
    assert "Watching web.whatsapp.com · every 5 min" in listed.text and "the physio chat" in listed.text
