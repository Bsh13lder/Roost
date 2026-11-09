"""Everything a bot writes carries bot:<slug>, project:<slug> when linked, and its topic tags (obsidian, part 1)."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.memory.store import MemoryStore
from roost.money.expense_store import ExpenseStore
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.notes.store import NoteStore
from roost.plan.store import PlanStore
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, steps: list, text: str = "go"):
    rig = make_rig(cfg, team_model({bot.name: [*steps, say("Done.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig


def _tool_texts(rig) -> list[str]:
    return [turn.text for turn in rig.model.requests[-1].turns if turn.role == "tool"]


async def _garden(cfg, user_id):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name="Garden 2026"), created_by_bot=None,
                                          tainted=False)


async def test_a_bot_task_carries_the_bot_the_project_and_its_topics(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Penny Pincher")
    await _garden(cfg, user_id)
    await _talk(cfg, user_id, bot, [_tool("t", "add_task", title="Buy seeds", project="Garden 2026",
                                          tags=["#Seeds", "spring"])])
    [task] = await TaskStore(cfg).list(user_id)
    assert task.tags == ("bot:penny-pincher", "project:garden-2026", "seeds", "spring")


async def test_a_bad_topic_tag_is_refused_and_nothing_is_written(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    rig = await _talk(cfg, user_id, bot, [_tool("t", "add_task", title="Buy seeds", tags=["two words"])])
    assert await TaskStore(cfg).list(user_id) == ()
    assert any(text.startswith("Refused: A tag is one word") for text in _tool_texts(rig))


async def test_a_bot_note_keeps_its_hashtags_and_gains_the_bot(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, [_tool("n", "add_note", title="Ana", content="likes #orchids", tags=["people"])])
    [note] = await NoteStore(cfg).list(user_id)
    assert note.tags == ("bot:writer", "people", "orchids")


async def test_a_bot_note_update_with_new_tags_keeps_the_bot_tag(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, [_tool("n", "add_note", title="Ana", content="hi", tags=["people"]),
                                    _tool("u", "update_note", note="Ana", tags=["friends"])])
    [note] = await NoteStore(cfg).list(user_id)
    assert note.tags == ("bot:writer", "friends")


async def test_a_bot_expense_carries_its_tags_sealed(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Penny")
    project = await _garden(cfg, user_id)
    await _talk(cfg, user_id, bot, [_tool("e", "log_expense", amount="12", project="Garden 2026", tags=["seeds"])])
    [expense] = await ExpenseStore(cfg).list_project(user_id, project.id)
    assert expense.tags == ("bot:penny", "project:garden-2026", "seeds")


async def test_an_expense_in_general_has_no_project_tag(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Penny")
    await _talk(cfg, user_id, bot, [_tool("e", "log_expense", amount="3")])
    from roost.money.months import current_month
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert expense.tags == ("bot:penny",)


async def test_a_bot_document_carries_its_tags(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _garden(cfg, user_id)
    await _talk(cfg, user_id, bot, [_tool("d", "create_doc", title="Plan", markdown="# Plan", project="Garden 2026",
                                          tags=["plans"])])
    [document] = await DocumentStore(cfg).list(user_id)
    assert document.tags == ("bot:writer", "project:garden-2026", "plans")


async def test_a_bot_memory_carries_its_tags(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, [_tool("m", "remember", text="Ana likes orchids", kind="fact", tags=["people"])])
    memories = await MemoryStore(cfg).list_scopes(user_id, bot.id)
    [memory] = [m for m in memories if m.text == "Ana likes orchids"]
    assert memory.tags == ("bot:writer", "people")


async def test_a_plan_item_carries_the_bot_as_an_obsidian_tag(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, [_tool("p", "plan_add", text="Water the roses", tags=["#garden"])])
    plan = await PlanStore(cfg).get(user_id, bot.id)
    assert "#bot/writer" in plan.content and "#garden" in plan.content


async def test_the_users_own_writes_get_no_system_tags(cfg, user_id):
    from roost.notes.models import NoteDraft
    note = await NoteStore(cfg).create(user_id, NoteDraft(title="Mine", content="x", tags=("me",)),
                                       created_by_bot=None, tainted=False)
    assert note.tags == ("me",)
