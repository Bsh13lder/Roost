"""Skill proposals (Skills Task 6): a bot offers a skill on a card; only the user's Save skill writes one."""

from __future__ import annotations

import json
import sqlite3

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import SKILL_PROPOSALS_OPEN_PER_BOT_MAX
from roost.db.connection import get_db_path, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.skills.models import SkillDraft, SkillPatch
from roost.skills.proposals import SkillProposalClosed, SkillProposalRefused, SkillProposalService, SkillProposalStore
from roost.skills.service import SkillService
from roost.skills.store import SkillStore
from roost.skills.tools import SkillTools
from roost.talk.chats import chat_preview
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.turn import _MODEL_KINDS
from team_helpers import make_bot

STEPS = "1. Open X\n2. Write the post"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def world(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    talk = TalkStore(cfg)
    thread, _ = await talk.ensure_main_thread(user_id, bot.id)
    skills = SkillService(SkillStore(cfg), EventHub(cfg), BotStore(cfg))
    proposals = SkillProposalService(SkillProposalStore(cfg), skills, talk, EventHub(cfg))
    return {"user": user_id, "bot": bot, "thread": thread, "talk": talk, "skills": skills, "proposals": proposals,
            "tools": SkillTools(skills, proposals)}


def _ctx(w, *, tainted=False, from_routine=False, thread_id=None):
    return RecordContext(user_id=w["user"], bot_id=w["bot"].id, tainted=tainted, from_routine=from_routine,
                         thread_id=thread_id or w["thread"].id, run_id="run-1")


async def _propose(w, name="Post on X", **kw):
    args = {"name": name, "use_when": "the user wants a post on X", "steps": STEPS}
    return await w["tools"].run("propose_skill", args, _ctx(w, **kw))


async def _cards(w, thread_id=None):
    messages = await w["talk"].list_messages(w["user"], thread_id or w["thread"].id)
    return [m for m in messages if m.kind == "skill_proposal"]


def test_no_tool_writes_a_skill():
    import inspect
    from roost.skills import tools as tools_module
    source = inspect.getsource(tools_module)
    assert ".add(" not in source and ".save(" not in source and ".set_on(" not in source
    assert CATALOG["propose_skill"].no_ask and CATALOG["propose_skill_change"].no_ask
    assert CATALOG["propose_skill"].allowed_when_tainted and CATALOG["propose_skill_change"].allowed_when_tainted


async def test_propose_posts_a_card_and_save_creates_the_skill(world):
    w = world
    out = await _propose(w)
    assert out.text == "Asked the user to save the skill “Post on X”. It exists only after they press Save skill."
    assert await w["skills"].list(w["user"]) == ()
    [card] = await _cards(w)
    body = json.loads(card.body)
    assert body["name"] == "Post on X"
    [view] = await w["proposals"].list_open(w["user"])
    assert view.proposal.id == body["proposal_id"] and view.proposal.payload.body == STEPS
    saved = await w["proposals"].save(w["user"], view.proposal.id)
    assert saved.proposal.state == "saved"
    [skill] = await w["skills"].list(w["user"])
    assert (skill.name, skill.body, skill.origin, skill.created_by_bot, skill.tainted) == (
        "Post on X", STEPS, "bot", w["bot"].id, False)
    assert await w["proposals"].list_open(w["user"]) == ()


async def test_a_change_card_shows_the_diff(world):
    w = world
    skill = await w["skills"].add(w["user"], SkillDraft(name="Post on X", use_when="posting", body="old steps"))
    args = {"skill": "post on x", "steps": "new steps"}
    out = await w["tools"].run("propose_skill_change", args, _ctx(w))
    assert out.text.startswith("Asked the user to save the change to “Post on X”.")
    [view] = await w["proposals"].list_open(w["user"])
    assert view.proposal.base_revision == skill.revision and view.skill_name == "Post on X"
    assert view.diff == ({"field": "body", "before": "old steps", "after": "new steps"},)
    nothing = await w["tools"].run("propose_skill_change", {"skill": "Post on X"}, _ctx(w))
    assert nothing.text.startswith("Refused: Say what to change")
    missing = await w["tools"].run("propose_skill_change", {"skill": "Nope", "steps": "x"}, _ctx(w))
    assert missing.text.startswith("There is no skill called")
    await w["proposals"].save(w["user"], view.proposal.id)
    assert (await w["skills"].get(w["user"], skill.id)).body == "new steps"


async def test_save_after_the_user_edited_is_stale(world):
    w = world
    skill = await w["skills"].add(w["user"], SkillDraft(name="Post on X", use_when="posting", body="old"))
    await w["tools"].run("propose_skill_change", {"skill": "Post on X", "steps": "bot's"}, _ctx(w))
    [view] = await w["proposals"].list_open(w["user"])
    await w["skills"].save(w["user"], skill.id, SkillPatch(body="mine"), base_revision=1)
    with pytest.raises(SkillProposalRefused) as caught:
        await w["proposals"].save(w["user"], view.proposal.id)
    assert caught.value.text == "That skill changed or is gone, so this proposal no longer fits."
    assert (await w["proposals"].get(w["user"], view.proposal.id)).proposal.state == "open"
    assert (await w["skills"].get(w["user"], skill.id)).body == "mine"


async def test_a_tainted_proposal_is_marked_and_saved_marked(world):
    w = world
    await _propose(w, tainted=True)
    [card] = await _cards(w)
    assert card.tainted is True
    [view] = await w["proposals"].list_open(w["user"])
    assert view.proposal.tainted is True
    await w["proposals"].save(w["user"], view.proposal.id)
    [skill] = await w["skills"].list(w["user"])
    assert skill.tainted is True
    await w["tools"].run("propose_skill_change", {"skill": "Post on X", "steps": "clean"}, _ctx(w))
    [change] = await w["proposals"].list_open(w["user"])
    await w["proposals"].save(w["user"], change.proposal.id)
    assert (await w["skills"].get(w["user"], skill.id)).tainted is True   # a proposal's Save never clears it


async def test_a_routine_run_proposal_is_marked(world):
    w = world
    log = await w["talk"].create_thread(w["user"], w["bot"].id, "Morning", kind="routine")
    await _propose(w, from_routine=True, thread_id=log.id)
    [view] = await w["proposals"].list_open(w["user"])
    assert view.proposal.from_routine is True and view.proposal.thread_id == log.id
    assert len(await _cards(w, log.id)) == 1 and len(await _cards(w)) == 1   # also in the bot's own chat


async def test_secret_in_a_proposal_is_refused(world):
    w = world
    secret = "sk-ant-abcdefghijklmnopqrstuv0123"
    out = await w["tools"].run("propose_skill", {"name": "Keys", "use_when": "always", "steps": f"use {secret}"},
                               _ctx(w))
    assert out.text.startswith("Refused: Not saved: an API key or token seems to be in the steps.")
    assert secret not in out.text and await w["proposals"].list_open(w["user"]) == ()


async def test_a_taken_name_is_refused(world):
    w = world
    await w["skills"].add(w["user"], SkillDraft(name="Post on X", use_when="posting", body="old"))
    out = await _propose(w, name="POST ON X")
    assert out.text == "Refused: There is already a skill called “Post on X”."


async def test_open_cap_per_bot(world):
    w = world
    for i in range(SKILL_PROPOSALS_OPEN_PER_BOT_MAX):
        assert (await _propose(w, name=f"Skill {i}")).text.startswith("Asked")
    over = await _propose(w, name="One too many")
    assert over.text == f"Refused: There are already {SKILL_PROPOSALS_OPEN_PER_BOT_MAX} skill proposals waiting for the user."


async def test_saving_twice_is_409(world):
    w = world
    await _propose(w)
    [view] = await w["proposals"].list_open(w["user"])
    await w["proposals"].save(w["user"], view.proposal.id)
    with pytest.raises(SkillProposalClosed):
        await w["proposals"].save(w["user"], view.proposal.id)
    with pytest.raises(SkillProposalClosed):
        await w["proposals"].decline(w["user"], view.proposal.id)


async def test_decline_writes_nothing(world):
    w = world
    await _propose(w)
    [view] = await w["proposals"].list_open(w["user"])
    declined = await w["proposals"].decline(w["user"], view.proposal.id)
    assert declined.proposal.state == "declined" and await w["skills"].list(w["user"]) == ()


async def test_the_payload_is_sealed(world, cfg):
    w = world
    await _propose(w)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        [(payload,)] = con.execute("SELECT payload FROM skill_proposals").fetchall()
    finally:
        con.close()
    assert payload.startswith("enc:v2:") and "Post on X" not in payload


def test_skill_proposal_messages_are_never_replayed():
    assert "skill_proposal" not in _MODEL_KINDS


async def test_chat_list_preview_is_words(world):
    w = world
    await _propose(w)
    [card] = await _cards(w)
    assert chat_preview(card) == ("Skill proposal · Post on X", "card")
