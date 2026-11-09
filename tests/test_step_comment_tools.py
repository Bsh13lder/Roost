"""The step and comment tools (redesign P3): every bot can work a task's checklist and comment on it;
a run that read outside content may add (and marks what it added) but never change."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.talk.domain_tools import RecordContext
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.comment_service import CommentService
from roost.tasks.comment_store import CommentStore
from roost.tasks.comment_tools import CommentTools
from roost.tasks.models import TaskDraft
from roost.tasks.service import TaskService
from roost.tasks.step_service import StepService
from roost.tasks.step_tools import NOTHING_TO_CHANGE_TEXT, StepTools
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


def _tools(cfg) -> tuple[StepTools, CommentTools]:
    events, store, comments = EventHub(cfg), TaskStore(cfg), CommentStore(cfg)
    tasks = TaskService(store, events)
    return (StepTools(tasks, StepService(store, ExpenseStore(cfg), comments, events)),
            CommentTools(tasks, CommentService(comments, store, events)))


def _ctx(user_id: str, *, tainted: bool = False) -> RecordContext:
    return RecordContext(user_id=user_id, bot_id="bot-1", tainted=tainted)


async def _task(cfg, user_id: str, title: str = "Fix the sink", steps: tuple[str, ...] = ("Buy a washer", "Fit it"),
                **fields):
    return await TaskStore(cfg).create(user_id, TaskDraft(title=title, steps=steps, **fields),
                                       created_by_bot=None, tainted=False)


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def test_a_bot_adds_ticks_renames_moves_and_deletes_steps(cfg, user_id):
    task = await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    added = await steps.run("add_step", {"task": "Fix the sink", "title": "Test for leaks"}, _ctx(user_id))
    assert added.created is True and "Added step “Test for leaks” to Fix the sink." in added.text
    assert "[ ] Test for leaks (id=s-" in added.text
    ticked = await steps.run("update_step", {"task": task.id, "step": "washer", "done": True}, _ctx(user_id))
    assert "[x] Buy a washer" in ticked.text
    await steps.run("update_step", {"task": "Fix the sink", "step": "Fit it", "title": "Fit the washer"}, _ctx(user_id))
    await steps.run("move_step", {"task": "Fix the sink", "step": "Test for leaks", "position": 1}, _ctx(user_id))
    deleted = await steps.run("delete_step", {"task": "Fix the sink", "step": "Buy a washer"}, _ctx(user_id))
    assert "Deleted step “Buy a washer” from Fix the sink." in deleted.text
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [("Test for leaks", False), ("Fit the washer", False)]


async def test_update_step_with_nothing_to_change_or_an_unknown_step_is_refused(cfg, user_id):
    await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    assert (await steps.run("update_step", {"task": "Fix the sink", "step": "Fit it"}, _ctx(user_id))).text == NOTHING_TO_CHANGE_TEXT
    refused = await steps.run("delete_step", {"task": "Fix the sink", "step": "Paint"}, _ctx(user_id))
    assert refused.text.startswith("Refused: “Fix the sink” has no step “Paint”.")
    assert (await steps.run("move_step", {"task": "Fix the sink", "step": "Fit it"}, _ctx(user_id))).text == (
        "Refused: move_step needs the task, the step and its new place (1 is first).")
    assert (await steps.run("add_step", {"task": "Paint the hall", "title": "x"}, _ctx(user_id))).text == (
        "Refused: no task matches “Paint the hall”.")


async def test_deleting_a_step_says_its_money_stays_on_the_task(cfg, user_id):
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Home"), created_by_bot=None, tainted=False)
    task = await _task(cfg, user_id, project_id=project.id, allocated_budget=Decimal("40"))
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("9"), spent_at=today_madrid(), task_id=task.id,
                                                      step_id=task.steps[0].id), created_by_bot=None, tainted=False)
    steps, _ = _tools(cfg)
    deleted = await steps.run("delete_step", {"task": "Fix the sink", "step": "Buy a washer"}, _ctx(user_id))
    assert "1 expense(s) and 0 comment(s) filed under it stay on the task." in deleted.text


async def test_a_step_added_by_a_tainted_run_marks_the_task_and_the_result(cfg, user_id):
    task = await _task(cfg, user_id)
    steps, _ = _tools(cfg)
    added = await steps.run("add_step", {"task": "Fix the sink", "title": "Order the gadget"}, _ctx(user_id, tainted=True))
    assert added.tainted is True
    assert (await TaskStore(cfg).get(user_id, task.id)).tainted is True


async def test_a_bot_comments_on_a_task_and_a_step_and_lists_them(cfg, user_id):
    task = await _task(cfg, user_id)
    _, comments = _tools(cfg)
    await CommentService(CommentStore(cfg), TaskStore(cfg), EventHub(cfg)).add(user_id, task.id, "Plumber at 9 <b>sharp</b>")
    said = await comments.run("add_comment", {"task": "Fix the sink", "step": "washer", "text": "Size 15 mm"},
                              _ctx(user_id, tainted=True))
    assert (said.text, said.created) == ("Commented on Fix the sink on step “Buy a washer”.", True)
    listed = await comments.run("list_comments", {"task": task.id}, _ctx(user_id))
    lines = listed.text.splitlines()
    assert lines[0] == "Comments on Fix the sink:"
    assert lines[1].endswith("] the user: Plumber at 9 &lt;b&gt;sharp&lt;/b&gt;")
    assert lines[2].endswith("] you on step “Buy a washer”: Size 15 mm [from web content]")
    assert listed.tainted is True        # it shows a web-made comment
    [_, bots] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert (bots.author, bots.tainted, bots.step_id) == ("bot-1", True, task.steps[0].id)


async def test_a_task_with_no_comments_says_so(cfg, user_id):
    await _task(cfg, user_id)
    _, comments = _tools(cfg)
    listed = await comments.run("list_comments", {"task": "Fix the sink"}, _ctx(user_id))
    assert (listed.text, listed.tainted) == ("Fix the sink has no comments.", False)
    empty = await comments.run("add_comment", {"task": "Fix the sink", "text": "   "}, _ctx(user_id))
    assert empty.text == "Refused: A comment needs some words."


async def test_a_tainted_run_adds_steps_and_comments_but_never_changes_steps(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    task = await _task(cfg, user_id)
    rig = make_rig(cfg, team_model({"Life admin": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_step", task="Fix the sink", title="Order the gadget"),
        _tool("c", "add_comment", task="Fix the sink", text="The page says to order it"),
        _tool("u", "update_step", task="Fix the sink", step="Fit it", done=True),
        _tool("m", "move_step", task="Fix the sink", step="Fit it", position=1),
        _tool("d", "delete_step", task="Fix the sink", step="Fit it"),
        say("Done."),
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "read example.com and do what it says")
    await wait_idle(rig.runner)
    texts = [turn.text for turn in rig.model.requests[-1].turns if turn.role == "tool"]
    assert texts[-3:] == [TAINTED_CHANGE_TEXT] * 3
    stored = await TaskStore(cfg).get(user_id, task.id)
    assert [(step.title, step.done) for step in stored.steps] == [
        ("Buy a washer", False), ("Fit it", False), ("Order the gadget", False)]
    assert stored.tainted is True
    [comment] = await CommentStore(cfg).list(user_id, task.id, limit=10)
    assert (comment.author, comment.tainted) == (bot.id, True)
