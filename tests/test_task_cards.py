"""Tasks shown as cards in the chat (2026-10-26): after add_task or list_tasks in a run of your own 1:1 chat, one
quiet ``task_cards`` line follows the bot's reply. Its body is task ids only (the clients fetch the tasks), it is
never replayed to a model, and the chat list previews it in words."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.constants import TASK_CARDS_MAX
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.chats import chat_preview
from roost.talk.domain_tools import RecordContext
from roost.talk.store import TalkStore
from roost.tasks.cards import TaskCards
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import ask, make_bot, make_rig, say, send, team_model, wait_idle

ORIGIN = {"Origin": "http://127.0.0.1:18800"}


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


async def _chat(cfg, user_id, bot, steps, text="show my tasks"):
    rig = make_rig(cfg, team_model({bot.name: steps}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig, thread, await rig.talk.list_messages(user_id, thread.id)


def _cards(messages):
    return [m for m in messages if m.kind == "task_cards"]


async def _add_tasks(cfg, user_id, count):
    store = TaskStore(cfg)
    return [await store.create(user_id, TaskDraft(title=f"Task {i}"), created_by_bot=None, tainted=False)
            for i in range(count)]


async def test_an_added_task_shows_as_a_card_line_after_the_bots_reply(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig, _, messages = await _chat(cfg, user_id, bot, [
        _tool("t", "add_task", title="Call the dentist"), say("Added it.")], "add call the dentist")
    [task] = await TaskStore(cfg).list(user_id)
    [line] = _cards(messages)
    assert json.loads(line.body) == {"task_ids": [task.id], "verb": "added", "more": 0}
    assert (line.role, line.author_bot_id, line.tainted) == ("activity", bot.id, False)
    reply = next(m for m in messages if m.role == "bot" and m.kind == "text")
    assert line.seq > reply.seq
    assert all(task.id not in turn.text for request in rig.model.requests for turn in request.turns
               if turn.role != "tool")


async def test_listed_tasks_show_at_most_the_cap_and_say_how_many_more(cfg, user_id):
    tasks = await _add_tasks(cfg, user_id, TASK_CARDS_MAX + 3)
    bot = await make_bot(cfg, user_id, "Helper")
    _, _, messages = await _chat(cfg, user_id, bot, [_tool("t", "list_tasks"), say("Here they are.")])
    [line] = _cards(messages)
    body = json.loads(line.body)
    assert body["verb"] == "listed" and body["more"] == 3
    assert len(body["task_ids"]) == TASK_CARDS_MAX
    assert set(body["task_ids"]) <= {task.id for task in tasks}


async def test_an_empty_list_posts_no_card_line(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    _, _, messages = await _chat(cfg, user_id, bot, [_tool("t", "list_tasks"), say("Nothing open.")])
    assert _cards(messages) == []


async def test_a_list_and_an_add_in_one_run_post_one_line_of_both(cfg, user_id):
    old, = await _add_tasks(cfg, user_id, 1)
    bot = await make_bot(cfg, user_id, "Helper")
    _, _, messages = await _chat(cfg, user_id, bot, [
        _tool("a", "list_tasks"), _tool("b", "add_task", title="New one"), _tool("c", "list_tasks"), say("Done.")])
    [line] = _cards(messages)
    body = json.loads(line.body)
    new = next(t for t in await TaskStore(cfg).list(user_id) if t.title == "New one")
    assert body["task_ids"] == [old.id, new.id] and body["verb"] == "tasks"


async def test_a_handoff_run_posts_no_card_line(cfg, user_id):
    lead = await make_bot(cfg, user_id, "Lead")
    helper = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({
        "Lead": [[ask("h", "Helper", "add a task"), TurnDone("tool_use")], say("Asked.")],
        "Helper": [_tool("t", "add_task", title="From a handoff"), say("Added.")],
    }))
    thread = await rig.talk.create_thread(user_id, lead.id)
    await send(rig, user_id, lead.id, thread.id, "ask Helper to add a task")
    await wait_idle(rig.runner)
    for t in await rig.talk.list_threads(user_id, helper.id):
        assert _cards(await rig.talk.list_messages(user_id, t.id)) == []
    assert _cards(await rig.talk.list_messages(user_id, thread.id)) == []


async def test_only_a_run_of_your_own_chat_collects_cards(cfg, user_id):
    talk = TalkStore(cfg)
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await talk.create_thread(user_id, bot.id)
    cards = TaskCards(talk, EventHub(cfg))
    for ctx in (RecordContext(user_id, bot.id, False, thread_id=thread.id, run_id="r1"),
                RecordContext(user_id, bot.id, False, thread_id=thread.id, run_id="r2", user_started=True,
                              from_routine=True),
                RecordContext(user_id, bot.id, False, thread_id=None, run_id="r3", user_started=True)):
        cards.note(ctx, ("t1",), "added")
        await cards.finish_run(user_id, bot.id, ctx.run_id)
    assert _cards(await talk.list_messages(user_id, thread.id)) == []


async def test_a_card_from_a_step_with_no_run_is_posted_at_once(cfg, user_id):
    talk = TalkStore(cfg)
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await talk.create_thread(user_id, bot.id)
    cards = TaskCards(talk, EventHub(cfg))
    await cards.note_now(RecordContext(user_id, bot.id, False, thread_id=thread.id, user_started=True), ("t1",),
                         "added")
    [line] = _cards(await talk.list_messages(user_id, thread.id))
    assert json.loads(line.body)["task_ids"] == ["t1"]


async def test_the_chat_list_previews_a_card_line_in_words(cfg, user_id):
    talk = TalkStore(cfg)
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await talk.create_thread(user_id, bot.id)
    for body, words in ((({"task_ids": ["a"], "verb": "added", "more": 0}), "Added a task"),
                        ({"task_ids": ["a", "b"], "verb": "listed", "more": 4}, "Showed 6 tasks"),
                        ({"task_ids": ["a", "b"], "verb": "tasks", "more": 0}, "Showed 2 tasks"),
                        ("not json", "Showed tasks")):
        message = await talk.add_message(user_id, thread.id, "activity",
                                         body if isinstance(body, str) else json.dumps(body), kind="task_cards")
        assert chat_preview(message) == (words, "notice")


def test_the_task_list_route_answers_the_ids_asked_in_their_order_and_only_yours():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN).status_code == 201
    first = c.post("/api/tasks", json={"title": "First"}, headers=ORIGIN).json()
    second = c.post("/api/tasks", json={"title": "Second"}, headers=ORIGIN).json()
    c.post(f"/api/tasks/{second['id']}/complete", headers=ORIGIN)
    rows = c.get(f"/api/tasks?ids={second['id']},nope,{first['id']}").json()
    assert [row["title"] for row in rows] == ["Second", "First"]
    assert rows[0]["status"] == "done" and "due_bucket" in rows[0]
    asyncio.run(register_user(load_config(), "bob", "pw-123456"))
    bob = TestClient(create_app())
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=ORIGIN).status_code == 200
    assert bob.get(f"/api/tasks?ids={first['id']}").json() == []


def test_too_many_ids_is_a_plain_422():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN)
    many = ",".join(f"id{i}" for i in range(TASK_CARDS_MAX * 10))
    r = c.get(f"/api/tasks?ids={many}")
    assert r.status_code == 422
