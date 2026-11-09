"""#project in a bot's chat (2026-10-26): the user's message names one of their projects as ``#Name``, and the
run is told, in one trusted line, which project they mean."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.config import load_config
from roost.constants import CHAT_PROJECTS_PER_MESSAGE_MAX, GENERAL_PROJECT_NAME
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.projects.chat_refs import chat_projects, project_mention_section
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _project(cfg, user_id, name, *, tainted=False):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name), created_by_bot=None, tainted=tainted)


async def _projects(cfg, user_id, *names):
    return tuple([await _project(cfg, user_id, name) for name in names])


async def test_a_hash_name_finds_the_project_exactly_case_insensitive_and_longest_first(cfg, user_id):
    casa, nueva = await _projects(cfg, user_id, "Casa", "Casa Nueva")
    assert chat_projects("tasks for #casa nueva please", (casa, nueva)) == (nueva,)
    assert chat_projects("#Casa, then #CASA NUEVA", (casa, nueva)) == (casa, nueva)
    assert chat_projects("what about #Casa?", (casa, nueva)) == (casa,)


async def test_no_project_is_read_from_a_word_mid_text_an_unknown_name_or_general(cfg, user_id):
    casa, = await _projects(cfg, user_id, "Casa")
    general = replace(casa, id="g", name=GENERAL_PROJECT_NAME)
    assert chat_projects("issue a#Casa", (casa,)) == ()
    assert chat_projects("#Casas are nice", (casa,)) == ()
    assert chat_projects("#Garden", (casa,)) == ()
    assert chat_projects(f"#{GENERAL_PROJECT_NAME}", (general,)) == ()
    assert chat_projects("#Casa", ()) == ()


async def test_one_project_named_twice_counts_once_and_at_most_the_cap_are_read(cfg, user_id):
    names = [f"P{i}" for i in range(CHAT_PROJECTS_PER_MESSAGE_MAX + 2)]
    found = await _projects(cfg, user_id, *names)
    text = "#P0 #P0 " + " ".join(f"#{name}" for name in names)
    assert chat_projects(text, found) == found[:CHAT_PROJECTS_PER_MESSAGE_MAX]


async def test_the_section_names_each_project_and_its_id_escaped(cfg, user_id):
    odd, = await _projects(cfg, user_id, "<b>Odd</b>")
    section = project_mention_section((odd,))
    assert section is not None
    assert "&lt;b&gt;Odd&lt;/b&gt;" in section and "<b>" not in section
    assert odd.id in section
    assert project_mention_section(()) is None


async def test_a_run_of_your_message_with_hash_project_is_told_which_project_you_mean(cfg, user_id):
    nueva, = await _projects(cfg, user_id, "Casa Nueva")
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [say("Sure.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "what is left in #Casa Nueva?")
    await wait_idle(rig.runner)
    system = rig.model.requests[-1].system
    assert f"The user means the project “Casa Nueva” (id {nueva.id})" in system


async def test_a_message_without_a_known_hash_project_adds_no_line(cfg, user_id):
    await _projects(cfg, user_id, "Casa Nueva")
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [say("Sure.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "what is left in #Garden?")
    await wait_idle(rig.runner)
    assert "The user means the project" not in rig.model.requests[-1].system


async def test_another_users_project_is_never_named(cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await _project(cfg, bob, "Casa Nueva")
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [say("Sure.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "#Casa Nueva")
    await wait_idle(rig.runner)
    assert "The user means the project" not in rig.model.requests[-1].system
