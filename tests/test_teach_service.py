"""Teach a task, start to proposal: start takes control, steps are kept only while teaching, stop proposes."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import SKILL_PROPOSALS_OPEN_PER_BOT_MAX
from roost.db.connection import init_db
from roost.desk.control import ControlLock
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.skills.models import SkillProposalPayload
from roost.skills.proposals import ProposalRequest, SkillProposalService, SkillProposalStore
from roost.skills.service import SkillService
from roost.skills.store import SkillStore
from roost.talk.store import TalkStore
from roost.teach import texts
from roost.teach.models import TeachRefused, TeachStep
from roost.teach.service import NotTeaching, TeachService
from roost.teach.store import TeachStore
from team_helpers import make_bot
from test_teach_draft import FakeWorker

STEP = TeachStep(kind="click", host="shop.example", path="/", title="Shop", role="link", label="Orders")
REPLY = json.dumps({"name": "Open orders", "use_when": "the user asks about orders", "steps": ["Open Orders"]})


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = (await register_user(cfg, "alice", "pw-123456")).id
    bot = replace(await make_bot(cfg, user, "Scout"), computer="linux")
    talk, events = TalkStore(cfg), EventHub(cfg)
    skills = SkillService(SkillStore(cfg), events, BotStore(cfg))
    proposals = SkillProposalService(SkillProposalStore(cfg), skills, talk, events)
    control = ControlLock()
    worker = FakeWorker(REPLY)
    service = TeachService(TeachStore(cfg), proposals, talk, control, worker)
    return {"cfg": cfg, "user": user, "bot": bot, "talk": talk, "proposals": proposals, "control": control,
            "service": service, "worker": worker}


async def _cards(w):
    thread, _ = await w["talk"].ensure_main_thread(w["user"], w["bot"].id)
    return [m for m in await w["talk"].list_messages(w["user"], thread.id) if m.kind == "skill_proposal"]


async def test_start_takes_control_and_records_only_while_teaching(world):
    w, service = world, world["service"]
    assert not await service.record(w["bot"].id, STEP)            # not teaching: nothing kept
    status = await service.start(w["user"], w["bot"])
    assert status.teaching and status.steps == 0 and not status.capped
    assert w["control"].held(w["bot"].id) is not None
    assert service.recording(w["bot"].id)
    assert await service.record(w["bot"].id, STEP)
    assert (await service.status(w["user"], w["bot"].id)).steps == 1


async def test_a_mac_brave_bot_cannot_be_taught(world):
    w = world
    with pytest.raises(TeachRefused) as caught:
        await w["service"].start(w["user"], replace(w["bot"], computer="mac_brave"))
    assert caught.value.text == texts.LINUX_ONLY
    assert w["control"].held(w["bot"].id) is None


async def test_stop_proposes_a_tainted_skill_and_forgets_the_log(world):
    w, service = world, world["service"]
    await service.start(w["user"], w["bot"])
    await service.record(w["bot"].id, STEP)
    outcome = await service.stop(w["user"], w["bot"].id, "Check my orders", discard=False)
    assert outcome.proposal_id and outcome.steps == 1 and not outcome.discarded
    view = await w["proposals"].get(w["user"], outcome.proposal_id)
    assert view.proposal.tainted and view.proposal.action == "create" and not view.proposal.from_routine
    assert view.proposal.payload.name == "Open orders" and view.proposal.payload.body == "1. Open Orders"
    assert len(await _cards(w)) == 1
    assert w["control"].held(w["bot"].id) is None and not service.recording(w["bot"].id)
    assert not (await service.status(w["user"], w["bot"].id)).teaching
    assert "Check my orders" in w["worker"].requests[0].turns[-1].text


async def test_stop_with_nothing_recorded_keeps_teaching(world):
    w, service = world, world["service"]
    await service.start(w["user"], w["bot"])
    with pytest.raises(TeachRefused) as caught:
        await service.stop(w["user"], w["bot"].id, None, discard=False)
    assert caught.value.text == texts.NOTHING_RECORDED
    assert service.recording(w["bot"].id) and w["control"].held(w["bot"].id) is not None


async def test_discard_throws_the_recording_away(world):
    w, service = world, world["service"]
    await service.start(w["user"], w["bot"])
    await service.record(w["bot"].id, STEP)
    outcome = await service.stop(w["user"], w["bot"].id, None, discard=True)
    assert outcome.discarded and outcome.proposal_id is None
    assert await _cards(w) == [] and w["control"].held(w["bot"].id) is None
    assert not service.recording(w["bot"].id)


async def test_stop_without_a_session_and_for_another_user(world):
    w, service = world, world["service"]
    with pytest.raises(NotTeaching):
        await service.stop(w["user"], w["bot"].id, None, discard=False)
    await service.start(w["user"], w["bot"])
    bob = (await register_user(w["cfg"], "bob", "pw-123456")).id
    with pytest.raises(NotTeaching):
        await service.stop(bob, w["bot"].id, None, discard=True)
    assert not (await service.status(bob, w["bot"].id)).teaching
    assert service.recording(w["bot"].id)


async def test_a_refused_proposal_keeps_the_recording(world):
    w, service = world, world["service"]
    thread, _ = await w["talk"].ensure_main_thread(w["user"], w["bot"].id)
    for n in range(SKILL_PROPOSALS_OPEN_PER_BOT_MAX):
        await w["proposals"].propose(ProposalRequest(
            user_id=w["user"], bot_id=w["bot"].id, action="create", thread_id=thread.id, tainted=False,
            from_routine=False, payload=SkillProposalPayload(name=f"S{n}", use_when="w", body="b")))
    await service.start(w["user"], w["bot"])
    await service.record(w["bot"].id, STEP)
    with pytest.raises(TeachRefused):
        await service.stop(w["user"], w["bot"].id, None, discard=False)
    assert service.recording(w["bot"].id)
    assert (await service.status(w["user"], w["bot"].id)).steps == 1


async def test_giving_control_back_any_other_way_ends_the_recording(world):
    """Review FAIL 1: a plain hand-back (I'm done, the Stuck card) stops recording; a later ordinary Take
    control records nothing, and the leftover log is gone."""
    w, service, bot_id = world, world["service"], world["bot"].id
    await service.start(w["user"], w["bot"])
    assert await service.record(bot_id, STEP)
    w["control"].give_back(bot_id)
    assert not service.recording(bot_id)
    w["control"].take(bot_id)                                     # an ordinary Take control, e.g. a bank
    assert not service.recording(bot_id)
    assert not await service.record(bot_id, STEP.model_copy(update={"label": "Account"}))
    status = await service.status(w["user"], bot_id)
    assert not status.teaching and status.steps == 0
    assert await TeachStore(w["cfg"]).get(w["user"], bot_id) is None
    assert not service.recording(bot_id)


async def test_a_restart_never_arms_recording_again(world):
    w, bot_id = world, world["bot"].id
    await w["service"].start(w["user"], w["bot"])
    await w["service"].record(bot_id, STEP)
    control = ControlLock()                                       # a restart: holds are gone
    fresh = TeachService(TeachStore(w["cfg"]), w["proposals"], w["talk"], control, w["worker"])
    assert not (await fresh.status(w["user"], bot_id)).teaching
    control.take(bot_id)
    assert not fresh.recording(bot_id)
    assert not await fresh.record(bot_id, STEP)


async def test_end_discards_the_recording_and_is_harmless_when_not_teaching(world):
    w, service, bot_id = world, world["service"], world["bot"].id
    await service.end(w["user"], bot_id)                          # nothing to end
    await service.start(w["user"], w["bot"])
    await service.record(bot_id, STEP)
    await service.end(w["user"], bot_id)
    assert not service.recording(bot_id)
    assert not (await service.status(w["user"], bot_id)).teaching


async def test_the_draft_counts_its_tokens_as_the_bots_background_work(world):
    from roost.llm.scripted_worker import ScriptedWorker
    from roost.usage.store import TokenUsageStore

    w = world
    store = TokenUsageStore(w["cfg"])
    service = TeachService(TeachStore(w["cfg"]), w["proposals"], w["talk"], w["control"], ScriptedWorker(),
                           usage=store)
    await service.start(w["user"], w["bot"])
    await service.record(w["bot"].id, STEP)
    await service.stop(w["user"], w["bot"].id, None, discard=False)
    rows = await store.rows(w["user"], since_day="2000-01-01", bot_id=w["bot"].id)
    assert [r.kind for r in rows] == ["background"] and rows[0].totals.calls == 1
