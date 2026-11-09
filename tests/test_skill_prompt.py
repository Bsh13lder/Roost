"""The Skills index in a bot's instructions (Skills Task 4): clean skills only, escaped, within a budget."""

from __future__ import annotations

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.skills.models import Skill, SkillDraft
from roost.skills.prompt import skills_section
from roost.skills.service import SkillService
from roost.skills.store import SkillStore
from roost.skills.texts import INDEX_HEAD
from roost.talk.instructions import build_instructions
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from team_helpers import RecordingModel, Rig, make_bot, send, wait_idle


def _skill(name: str, use_when: str = "it fits", tainted: bool = False) -> Skill:
    return Skill(id=f"id-{name}", user_id="u", name=name, use_when=use_when, body="steps", origin="user",
                 tainted=tainted, created_by_bot=None, revision=1, created_at="t", updated_at="t")


def test_index_lists_clean_skills_within_budget():
    skills = [_skill(f"Skill {i:02d}", "x" * 40) for i in range(60)]
    section = skills_section(skills)
    assert section.text.startswith(INDEX_HEAD)
    assert len(section.text) <= 2000 + 60
    assert section.shown[0] == "Skill 00" and 0 < len(section.shown) < 60
    assert section.hidden_budget == 60 - len(section.shown)
    assert f"{section.hidden_budget} more skills: find them with search_skills" in section.text
    assert "- Skill 00 · Use when: " + "x" * 40 in section.text


def test_index_is_in_folded_name_order():
    section = skills_section([_skill("banana"), _skill("Apple"), _skill("Éclair")])
    assert section.shown == ("Apple", "banana", "Éclair")


def test_index_escapes_names():
    section = skills_section([_skill("<b>Post</b> & co", 'when "asked" <now>')])
    assert "&lt;b&gt;Post&lt;/b&gt; &amp; co" in section.text and "<b>" not in section.text
    assert "&quot;asked&quot; &lt;now&gt;" in section.text


def test_marked_skills_are_counted_not_shown():
    section = skills_section([_skill("Clean"), _skill("From the web", tainted=True), _skill("Also web", tainted=True)])
    assert section.shown == ("Clean",) and section.hidden_tainted == 2
    assert "From the web" not in section.text and "Also web" not in section.text
    assert "2 more came from outside content" in section.text
    only_marked = skills_section([_skill("From the web", tainted=True)])
    assert only_marked.shown == () and "From the web" not in only_marked.text


def test_no_skills_no_section():
    assert skills_section([]) is None


def test_build_instructions_places_the_index_before_the_plan():
    from test_instructions import _bot
    text = build_instructions(_bot(), skills="SKILLS-HERE", plan="PLAN-HERE", memory="MEMORY-HERE")
    assert text.index("SKILLS-HERE") < text.index("PLAN-HERE")
    assert "SKILLS-HERE" not in build_instructions(_bot())


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg, skills: SkillService) -> Rig:
    model = RecordingModel(ScriptedTeamModel({}))
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard(), skills=skills)
    return Rig(runner=runner, bots=bots, talk=talk, events=events, desks=desks, model=model)


async def _run_once(cfg, setup):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    service = SkillService(SkillStore(cfg), EventHub(cfg), BotStore(cfg))
    await setup(service, user_id, bot.id)
    rig = await _rig(cfg, service)
    thread = await rig.talk.create_thread(user_id, bot.id, "chat")
    await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    messages = await rig.talk.list_messages(user_id, thread.id)
    return rig.model.requests[0].system, messages


async def _add(service, user_id, name, tainted=False):
    draft = SkillDraft(name=name, use_when=f"use {name}", body="1. step")
    return await service.add(user_id, draft, origin="bot" if tainted else "user", tainted=tainted)


async def test_switched_off_skills_are_left_out(cfg):
    async def setup(service, user_id, bot_id):
        await _add(service, user_id, "Kept skill")
        gone = await _add(service, user_id, "Switched skill")
        await service.set_on(user_id, bot_id, gone.id, False)

    system, _ = await _run_once(cfg, setup)
    assert INDEX_HEAD in system and "- Kept skill · Use when: use Kept skill" in system
    assert "Switched skill" not in system


async def test_the_index_never_taints_the_run(cfg):
    async def setup(service, user_id, bot_id):
        await _add(service, user_id, "Clean skill")
        await _add(service, user_id, "Web skill", tainted=True)

    system, messages = await _run_once(cfg, setup)
    assert "Clean skill" in system and "Web skill" not in system and "1 more came from outside content" in system
    replies = [m for m in messages if m.role == "bot"]
    assert replies and not any(m.tainted for m in replies)


async def test_no_skill_no_index_in_the_run(cfg):
    async def setup(service, user_id, bot_id):
        return None

    system, _ = await _run_once(cfg, setup)
    assert INDEX_HEAD not in system
