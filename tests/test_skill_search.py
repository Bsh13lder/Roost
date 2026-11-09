"""Skill search (owner, 2026-10-31: "like LazyClaw, load a few with a skill search"): ``search_skills`` scores the
user's skills on for this bot by name, Use when and steps, and each run's index puts the skills its request names
first, so a long list still shows the ones that fit. No real model."""

from __future__ import annotations

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import SKILL_SEARCH_RESULTS_MAX
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.skills.models import Skill, SkillDraft
from roost.skills.prompt import skills_section
from roost.skills.search import rank_skills
from roost.skills.service import SkillService
from roost.skills.store import SkillStore
from roost.skills.tools import SkillTools
from roost.talk.domain_tools import RecordContext
from roost.talk.plain_steps import FIXED_LINES
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot


def _skill(name: str, use_when: str = "", body: str = "", tainted: bool = False, n: int = 0) -> Skill:
    return Skill(id=f"s{n}-{name}", user_id="u1", name=name, use_when=use_when or f"use {name}", body=body or "1. do it",
                 tainted=tainted, origin="user", revision=1, created_at="2026-10-31T10:00:00+00:00",
                 updated_at="2026-10-31T10:00:00+00:00", created_by_bot=None)


SKILLS = (
    _skill("Book a table", "a restaurant booking", "1. Open the site", n=1),
    _skill("Upwork proposals", "applying to a job on Upwork", "1. Open the job\n2. Apply now opens the form", n=2),
    _skill("Pay a Tasa", "paying a Spanish fee", "1. Open the sede", n=3),
    _skill("Reply on WhatsApp", "answering a chat", "1. Open the chat\n2. Send a proposal link", n=4),
)


# -- ranking --------------------------------------------------------------------------------------------------

def test_the_name_beats_the_use_when_which_beats_the_steps():
    ranked = rank_skills(SKILLS, "send the upwork proposal")
    assert [s.name for s in ranked][:2] == ["Upwork proposals", "Reply on WhatsApp"]


def test_case_and_accents_are_folded_and_small_words_ignored():
    assert [s.name for s in rank_skills(SKILLS, "PAGAR la TASA")] == ["Pay a Tasa"]
    assert rank_skills(SKILLS, "the a to of") == ()


def test_nothing_matching_is_an_empty_result():
    assert rank_skills(SKILLS, "kayak rental") == ()
    assert rank_skills(SKILLS, "") == ()


# -- the index ------------------------------------------------------------------------------------------------

def test_the_index_puts_the_skills_your_request_names_first():
    section = skills_section(SKILLS, query="send my upwork proposal")
    assert section is not None
    assert section.shown[0] == "Upwork proposals"


def test_with_no_request_the_index_keeps_name_order():
    section = skills_section(SKILLS)
    assert section is not None and section.shown == ("Book a table", "Pay a Tasa", "Reply on WhatsApp",
                                                     "Upwork proposals")


def test_a_long_list_points_to_search_skills():
    many = tuple(_skill(f"Skill number {n}", body="1. step", n=n) for n in range(60))
    section = skills_section(many, query="number 59")
    assert section is not None and section.hidden_budget > 0
    assert section.shown[0] == "Skill number 59"
    assert "search_skills" in section.text


# -- the tool -------------------------------------------------------------------------------------------------

@pytest.fixture
async def world():
    config = load_config()
    await init_db(config)
    user_id = (await register_user(config, "alice", "pw-123456")).id
    bot = await make_bot(config, user_id, "Scout")
    service = SkillService(SkillStore(config), EventHub(config), BotStore(config))
    return user_id, bot, service, SkillTools(service)


def _ctx(user_id: str, bot_id: str) -> RecordContext:
    return RecordContext(user_id=user_id, bot_id=bot_id, tainted=False, run_id="run-1")


async def _add(service, user_id, name, use_when, body="1. step", tainted=False):
    draft = SkillDraft(name=name, use_when=use_when, body=body)
    return await service.add(user_id, draft, origin="file" if tainted else "user", tainted=tainted)


async def test_search_skills_returns_the_best_few_escaped(world):
    user_id, bot, service, tools = world
    await _add(service, user_id, "Upwork <proposals>", "applying on Upwork")
    await _add(service, user_id, "Book a table", "restaurants")
    out = await tools.run("search_skills", {"query": "upwork proposal"}, _ctx(user_id, bot.id))
    assert "Upwork &lt;proposals&gt;" in out.text and "Book a table" not in out.text
    assert "read_skill" in out.text and out.tainted is False


async def test_search_skills_caps_its_results(world):
    user_id, bot, service, tools = world
    for n in range(SKILL_SEARCH_RESULTS_MAX + 3):
        await _add(service, user_id, f"Invoice step {n}", "invoices")
    out = await tools.run("search_skills", {"query": "invoice"}, _ctx(user_id, bot.id))
    assert out.text.count("\n- ") == SKILL_SEARCH_RESULTS_MAX


async def test_a_marked_skill_is_flagged_and_taints_the_result(world):
    user_id, bot, service, tools = world
    await _add(service, user_id, "Upwork tricks", "from a file", tainted=True)
    out = await tools.run("search_skills", {"query": "upwork"}, _ctx(user_id, bot.id))
    assert "(from web content)" in out.text and out.tainted is True


async def test_no_match_and_a_skill_off_for_this_bot(world):
    user_id, bot, service, tools = world
    skill = await _add(service, user_id, "Upwork proposals", "applying on Upwork")
    await service.set_on(user_id, bot.id, skill.id, False)
    out = await tools.run("search_skills", {"query": "upwork"}, _ctx(user_id, bot.id))
    assert "No skill" in out.text


async def test_an_empty_query_is_refused(world):
    user_id, bot, _service, tools = world
    out = await tools.run("search_skills", {"query": "  "}, _ctx(user_id, bot.id))
    assert out.text.startswith("Refused")


def test_search_skills_is_a_read_every_bot_has_with_its_own_step_words():
    assert CATALOG["search_skills"].kind == "read"
    assert "Searched the skills" in FIXED_LINES
