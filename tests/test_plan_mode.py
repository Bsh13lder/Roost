"""Review first / Plan mode (approval plan Task 11): changes become steps of one Proposal card; Accept runs
exactly those steps, re-checking each; Edit and Decline change nothing."""

from __future__ import annotations

import json

import pytest

from plan_helpers import NEW, call, direct_runner, mac_setup, mode_rig, step
from roost.approvals.models import ApprovalDraft, ApprovalState, BadAnswer, CardClosed, CardState
from roost.approvals.plan import PlanDraft
from roost.approvals.texts import (
    ACCEPT_LINE, DECLINE_LINE, PLAN_FULL_TEXT, PLAN_WAITS_LINE, PLANNED_TEXT, STEP_FAILED_LINE,
)
from roost.config import load_config
from roost.constants import APPROVAL_PLAN_MAX_STEPS
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.mac.models import FileRef
from roost.talk.domain_tools import RecordContext
from roost.talk.gate import TAINTED_CHANGE_TEXT, GateContext, judge
from roost.talk.tool_catalog import CATALOG
from team_helpers import make_bot, say, send, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _count(cfg, sql: str, *params) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute(sql, params)).fetchone())[0]


async def _tasks(cfg, user_id) -> int:
    return await _count(cfg, "SELECT COUNT(*) FROM tasks WHERE user_id = ?", user_id)


async def _kinds(rig, user_id, thread_id, kind):
    return [m for m in await rig.talk.list_messages(user_id, thread_id) if m.kind == kind]


async def _planned(cfg, user_id, script, *, files=None, grants=None):
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "plan", script, files=files, grants=grants)
    await send(rig, user_id, bot.id, thread.id, "plan it")
    await wait_idle(rig.runner)
    return rig, bot, thread


TWO_TASKS = [step(call("add_task", "a", title="Call bank"), call("add_task", "b", title="Pay rent")),
             say("The plan is ready."), say("Carrying on.")]


def test_a_plan_draft_adds_steps_without_changing_itself():
    from roost.approvals.models import PendingCall
    one = PendingCall("add_task", {}, "tasks", "Add a task")
    draft = PlanDraft()
    longer = draft.add(one).add(one)
    assert draft.steps == () and len(longer.steps) == 2


async def test_plan_mode_collects_steps_and_posts_one_plan_card_at_the_end(cfg, user_id):
    rig, bot, thread = await _planned(cfg, user_id, TWO_TASKS)
    cards = await rig.store.list_open(user_id)
    assert len(cards) == 1 and cards[0].kind == "plan" and cards[0].state is CardState.OPEN
    assert [s.tool for s in cards[0].steps] == ["add_task", "add_task"]
    assert await _tasks(cfg, user_id) == 0
    messages = await _kinds(rig, user_id, thread.id, "approval")
    assert len(messages) == 1 and json.loads(messages[0].body)["kind"] == "plan"
    tool_texts = [t.text for t in rig.model.requests[1].turns if t.role == "tool"]
    assert tool_texts == [PLANNED_TEXT.format(n=1), PLANNED_TEXT.format(n=2)]


async def test_accept_runs_every_step_without_asking_and_carries_on(cfg, user_id):
    rig, bot, thread = await _planned(cfg, user_id, TWO_TASKS)
    card = (await rig.store.list_open(user_id))[0]
    answered = await rig.service.answer(user_id, card.id, "accept")
    await wait_idle(rig.runner)
    assert answered.state is CardState.APPROVED
    assert await _tasks(cfg, user_id) == 2
    assert await rig.store.list_open(user_id) == ()
    lines = [m.body for m in await _kinds(rig, user_id, thread.id, "card_answer")]
    assert lines == [ACCEPT_LINE.format(n=2)]
    assert len(await _kinds(rig, user_id, thread.id, "approval_result")) == 1
    assert len(rig.model.requests) == 3                      # the card_answer item woke the bot once more
    with pytest.raises(CardClosed):
        await rig.service.answer(user_id, card.id, "accept")


async def test_a_failed_step_stops_the_plan_and_says_which(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    rig, thread = await mode_rig(cfg, user_id, bot, "plan", [
        step(call("add_task", "a", title="First"),
             call("mac_edit", "b", folder="MySpace", path="Tasks.md", base_hash=sha, text=NEW),
             call("add_task", "c", title="Third")),
        say("ready"), say("ok")], files=files, grants=grants)
    await send(rig, user_id, bot.id, thread.id, "plan it")
    await wait_idle(rig.runner)
    card = (await rig.store.list_open(user_id))[0]
    assert len(card.steps) == 3
    files.replace_tree({"MySpace/Tasks.md": "someone else changed this\n"})
    answered = await rig.service.answer(user_id, card.id, "accept")
    await wait_idle(rig.runner)
    assert answered.state is CardState.FAILED
    assert await _tasks(cfg, user_id) == 1                    # only the first step ran
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text == "someone else changed this\n"
    result = (await _kinds(rig, user_id, thread.id, "approval_result"))[0].body
    assert STEP_FAILED_LINE.format(n=2, reason="The file changed since you read it. Read it again first.") in result


async def test_decline_changes_nothing(cfg, user_id):
    rig, bot, thread = await _planned(cfg, user_id, TWO_TASKS)
    card = (await rig.store.list_open(user_id))[0]
    answered = await rig.service.answer(user_id, card.id, "decline")
    await wait_idle(rig.runner)
    assert answered.state is CardState.DECLINED and await _tasks(cfg, user_id) == 0
    assert [m.body for m in await _kinds(rig, user_id, thread.id, "card_answer")] == [DECLINE_LINE]
    assert len(rig.model.requests) == 2                       # nothing was queued


async def test_edit_posts_your_words_as_a_new_message(cfg, user_id):
    rig, bot, thread = await _planned(cfg, user_id, TWO_TASKS)
    card = (await rig.store.list_open(user_id))[0]
    for bad in (None, "", "x" * 4001):
        with pytest.raises(BadAnswer):
            await rig.service.answer(user_id, card.id, "edit", bad)
    assert (await rig.store.get(user_id, card.id)).state is CardState.OPEN
    answered = await rig.service.answer(user_id, card.id, "edit", "Only the first one, please")
    await wait_idle(rig.runner)
    assert answered.state is CardState.EDITED and await _tasks(cfg, user_id) == 0
    mine = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "user"]
    assert [(m.kind, m.body) for m in mine][-1] == ("text", "Only the first one, please")
    assert len(rig.model.requests) == 3                       # queued as a normal message


async def test_a_floor_step_in_plan_mode_parks_with_its_own_ask_card(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    rig, bot, thread = await _planned(cfg, user_id, [
        step(call("add_task", "a", title="Call bank"),
             call("mac_write_new", "b", folder="MySpace", path="n.md", text="my password is hunter22!\n")),
        say("asked")], files=files, grants=grants)
    cards = await rig.store.list_open(user_id)
    assert [(c.kind, c.steps[0].floor) for c in cards] == [("ask", "secret")]
    assert PLAN_WAITS_LINE == "The plan waits until you answer."
    notices = [m.body for m in await rig.talk.list_messages(user_id, thread.id) if m.body == PLAN_WAITS_LINE]
    assert len(notices) == 1 and await _tasks(cfg, user_id) == 0


async def test_an_accepted_plan_runs_a_tainted_mac_edit_but_not_a_tainted_rename(cfg, user_id):
    files, grants, grant = await mac_setup(cfg, user_id)
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "plan", [say("ok")], files=files, grants=grants)
    sha = (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).sha256
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=True, thread_id=thread.id)
    edit = await rig.runner.domain.prepare(
        "mac_edit", {"folder": "MySpace", "path": "Tasks.md", "base_hash": sha, "text": NEW}, ctx)
    rename = await rig.runner.domain.prepare(
        "mac_rename", {"folder": "MySpace", "path": "notes/ideas.md", "new_path": "notes/moved.md"}, ctx)
    card = await rig.store.open(user_id, ApprovalDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, kind="plan", steps=(edit, rename),
        request="r", tainted=True))
    answered = await rig.service.answer(user_id, card.id, "accept")
    await wait_idle(rig.runner)
    assert answered.state is CardState.FAILED
    assert (await files.read(FileRef(grant.id, bot.id, "Tasks.md"))).text == NEW
    assert (await files.read(FileRef(grant.id, bot.id, "notes/ideas.md"))).text == "kettle idea\n"
    result = (await _kinds(rig, user_id, thread.id, "approval_result"))[0].body
    assert TAINTED_CHANGE_TEXT in result


async def test_a_plan_over_the_step_cap_is_refused(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout")
    rig, thread = await mode_rig(cfg, user_id, bot, "plan", [])
    runner = direct_runner(cfg, user_id, bot, rig, "plan", thread_id=thread.id)
    for n in range(APPROVAL_PLAN_MAX_STEPS):
        assert await runner.run(call("add_task", f"t{n}", title=f"Task {n}")) == PLANNED_TEXT.format(n=n + 1)
    assert await runner.run(call("add_task", "over", title="One too many")) == PLAN_FULL_TEXT
    assert len(runner.plan.steps) == APPROVAL_PLAN_MAX_STEPS and runner.parked is None
    assert await _tasks(cfg, user_id) == 0


def test_reads_in_plan_mode_still_follow_the_grants_read_policy():
    plan = ApprovalState("plan", frozenset(), True)
    ctx = GateContext(allowed=frozenset(CATALOG), approval=plan)
    assert judge(CATALOG["list_tasks"], "list_tasks", {}, ctx).decision == "do"
    asks = judge(CATALOG["mac_read"], "mac_read", {"folder": "MySpace", "path": "a.md"}, ctx)
    assert (asks.decision, asks.reason) == ("ask", "mac_read_asks")
    ok = GateContext(allowed=frozenset(CATALOG), approval=ApprovalState("plan", frozenset(), True,
                                                                        session_folders=frozenset({"myspace"})))
    assert judge(CATALOG["mac_read"], "mac_read", {"folder": "MySpace", "path": "a.md"}, ok).decision == "do"
    tainted = GateContext(allowed=frozenset(CATALOG), tainted=True, approval=ok.approval)
    assert judge(CATALOG["mac_read"], "mac_read", {"folder": "MySpace", "path": "a.md"}, tainted).decision == "ask"
