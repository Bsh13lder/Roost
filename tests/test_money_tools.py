"""The finance role end to end (M1 D2, D3, D7)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft, ProjectPatch
from roost.money.months import current_month, today_madrid
from roost.money.project_store import ProjectStore
from roost.money.tool_specs import LOG_EXPENSE_SPEC, MONEY_TOOL_DEFS, SET_BUDGET_SPEC
from roost.money.tools import ListExpensesArgs, LogExpenseArgs, SetBudgetArgs, UpdateExpenseArgs
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from roost.tasks.tool_specs import ADD_TASK_SPEC, LIST_TASKS_SPEC
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


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def test_spent_12_50_on_lunch_food_logs_it_and_the_summary_shows_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount="12,50", project="food", note="lunch"),
        _tool("s", "money_summary"), say("Logged."),
    ]}, "spent 12.50 on lunch, food")
    logged, summary = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 12.50 EUR to food on " + today_madrid())
    assert "food: 12.50 EUR" in summary and "Total: 12.50 EUR" in summary
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert (expense.amount, expense.description, expense.created_by_bot, expense.tainted) == (
        Decimal("12.50"), "lunch", bot.id, False)


async def test_a_typo_lands_in_the_existing_project(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Groceries", created_by_bot=None, tainted=False)
    await _talk(cfg, user_id, bot, {"Life admin": [_tool("e", "log_expense", amount=4, project="groceris"), say("ok")]}, "4 on groceris")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Groceries"]


async def test_an_expense_logged_after_reading_a_page_is_stored_tainted(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("p", "open_page", url="https://example.com"), _tool("e", "log_expense", amount=99, project="gadgets"), say("ok"),
    ]}, "read example.com and log what it costs")
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert expense.tainted is True


async def test_a_tainted_run_cannot_change_delete_or_set_budgets(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await ProjectStore(cfg).find_or_create(user_id, "food", created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("u", "update_expense", expense=expense.id, amount=1), _tool("d", "delete_expense", expense=expense.id),
        _tool("b", "set_budget", project="food", amount=1), say("no"),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[1:] == [TAINTED_CHANGE_TEXT] * 3
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).amount == Decimal("10.00")


async def test_a_clean_log_into_a_web_made_project_taints_the_run(cfg, user_id):
    """D3: the reply echoes the project's name, and a name a tainted run
    made is web text — the run is tainted from there, and so is its reply."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Gadgets", created_by_bot=None, tainted=True)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount=5, project="gadgets"),
        _tool("b", "set_budget", project="gadgets", amount=50), say("ok"),
    ]}, "5 on gadgets, and a 50 budget for them")
    logged, budget = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 5.00 EUR to Gadgets") and budget == TAINTED_CHANGE_TEXT
    [thread] = await rig.talk.list_threads(user_id, bot.id)
    [reply] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert reply.tainted is True
    [expense] = await ExpenseStore(cfg).list_month(user_id, current_month())
    assert expense.tainted is False      # logged while the run was still clean


async def test_a_web_made_project_the_summary_does_not_show_leaves_it_clean(cfg, user_id):
    """R1: only what the summary prints taints it, so one web-made project
    doesn't block every later budget change in the conversation."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await ProjectStore(cfg).find_or_create(user_id, "Gadgets", created_by_bot=None, tainted=True)
    food = await ProjectStore(cfg).find_or_create(user_id, "food", created_by_bot=None, tainted=False)
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("10"), spent_at=today_madrid()),
                                created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("s", "money_summary"), _tool("b", "set_budget", project="food", amount=100), say("ok"),
    ]}, "how is my month? and budget 100 for food")
    summary, budget = _tool_texts(rig.model.requests[-1])
    assert "Gadgets" not in summary and budget.startswith("Budget for food: 100.00 EUR")


async def test_other_currencies_stay_out_of_the_eur_total(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount="10", project="travel"),
        _tool("e2", "log_expense", amount="20", project="travel", currency="USD"),
        _tool("s", "money_summary"), say("ok"),
    ]}, "log them")
    summary = _tool_texts(rig.model.requests[-1])[-1]
    assert "Total: 10.00 EUR" in summary and "Also 20.00 USD" in summary


async def test_a_second_bot_with_the_finance_role_sees_the_same_money(cfg, user_id):
    first = await make_bot(cfg, user_id, "Life admin")
    second = await make_bot(cfg, user_id, "Ledger")
    await _talk(cfg, user_id, first, {"Life admin": [_tool("e", "log_expense", amount=7, project="food"), say("ok")]}, "7 food")
    rig = await _talk(cfg, user_id, second, {"Ledger": [_tool("l", "list_expenses"), say("ok")]}, "what did I spend?")
    assert "7.00 EUR" in _tool_texts(rig.model.requests[-1])[0]


async def test_a_bad_amount_is_refused_plainly(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [_tool("e", "log_expense", amount="1.234,56"), say("?")]}, "log")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Refused:")
    assert await ExpenseStore(cfg).list_month(user_id, current_month()) == ()


async def test_log_expense_still_accepts_the_old_category_argument(cfg, user_id):
    """H1: the money tools call it `project`. A model that still sends
    `category` lands in that project, never in General by accident."""
    bot = await make_bot(cfg, user_id, "Life admin")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=4, category="food", note="bread"),
        _tool("e2", "log_expense", amount=9, project="travel", note="bus"),
        _tool("l", "list_expenses", category="food"),
        _tool("b", "set_budget", category="food", amount=50), say("ok"),
    ]}, "4 on food for bread, 9 on travel for the bus, show me food and budget 50 for it")
    logged, _, listed, budget = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 4.00 EUR to food on " + today_madrid())
    assert "bread" in listed and "bus" not in listed
    assert budget.startswith("Budget for food: 50.00 EUR")
    assert sorted(p.name for p in await ProjectStore(cfg).list(user_id)) == ["food", "travel"]


@pytest.mark.parametrize(("args_type", "required"), [
    (LogExpenseArgs, {"amount": 1}),
    (ListExpensesArgs, {}),
    (UpdateExpenseArgs, {"expense": "e1"}),
    (SetBudgetArgs, {"amount": 1}),
])
def test_every_money_tool_takes_project_and_still_category(args_type, required):
    assert args_type.model_validate({**required, "project": "food"}).project == "food"
    assert args_type.model_validate({**required, "category": "food"}).project == "food"
    assert args_type.model_validate({**required, "project": "food", "category": "travel"}).project == "food"


def test_money_tools_say_project_and_a_tasks_category_is_its_list():
    for tool in MONEY_TOOL_DEFS:
        text = tool.spec.description + json.dumps(tool.spec.input_schema)
        assert "categor" not in text.casefold(), tool.name
    assert "project" in LOG_EXPENSE_SPEC.input_schema["properties"]
    assert SET_BUDGET_SPEC.input_schema["required"] == ["project", "amount"]
    task_lists = (ADD_TASK_SPEC.input_schema["properties"]["category"]["description"],
                  LIST_TASKS_SPEC.input_schema["properties"]["category"]["description"])
    assert all("list" in text and "project" not in text for text in task_lists)


async def _new_project(cfg, user_id, name: str, **fields):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None,
                                          tainted=False)


async def test_an_expense_for_a_closed_task_and_its_step_goes_into_the_tasks_project(cfg, user_id):
    """H11: the task is found among tasks of every status, the step is one of
    its steps, and with no project named the money goes to the task's project."""
    bot = await make_bot(cfg, user_id, "Life admin")
    project = await _new_project(cfg, user_id, "Renovation")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint", "Paint"),
                                                          project_id=project.id), created_by_bot=None, tainted=False)
    await TaskStore(cfg).complete(user_id, task.id)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount="30", task="paint the hall", step="buy paint", starred=True, note="white"),
        say("Logged."),
    ]}, "30 on white paint for the hall, and star it")
    [logged] = _tool_texts(rig.model.requests[-1])
    assert logged.startswith(f"Logged 30.00 EUR to Renovation on {today_madrid()} for “Paint the hall”, "
                             "step “Buy paint”, starred (id=")
    [expense] = await ExpenseStore(cfg).list_project(user_id, project.id)
    [buy_paint] = [step for step in task.steps if step.title == "Buy paint"]
    assert (expense.task_id, expense.step_id, expense.is_favorite, expense.description) == (
        task.id, buy_paint.id, True, "white")


async def test_a_step_needs_its_task_and_must_be_one_of_its_steps(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", steps=("Buy paint",)),
                                       created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=5, step="Buy paint"),
        _tool("e2", "log_expense", amount=5, task="Paint the hall", step="Buy brushes"),
        _tool("e3", "log_expense", amount=5, task="Paint the hull"),
        say("Which?"),
    ]}, "5 on brushes for the hall")
    alone, wrong_step, near = _tool_texts(rig.model.requests[-1])
    assert alone == "Refused: A step needs its task: name the task too."
    assert wrong_step == "Refused: “Paint the hall” has no step “Buy brushes”. Its steps: “Buy paint”."
    assert near == (f"Refused: no task is called “Paint the hull”. Did you mean “Paint the hall” id={task.id}? "
                    "Say it exactly.")
    assert await ExpenseStore(cfg).list_month(user_id, current_month()) == ()


async def test_an_archived_project_takes_no_new_or_moved_expense(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    old = await _new_project(cfg, user_id, "Old flat")
    await ProjectStore(cfg).update(user_id, old.id, ProjectPatch({"status": "archived"}))
    food = await _new_project(cfg, user_id, "Food")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("4"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount=5, project="old flat"),
        _tool("u", "update_expense", expense=expense.id, project="Old flat"),
        say("It is archived."),
    ]}, "5 on the old flat, and move the 4 there too")
    assert _tool_texts(rig.model.requests[-1]) == ["Refused: “Old flat” is archived; unarchive it first."] * 2
    assert await ExpenseStore(cfg).list_project(user_id, old.id) == ()
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).project_id == food.id


async def test_update_expense_moves_stars_voids_and_unlinks(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await _new_project(cfg, user_id, "Food")
    trip = await _new_project(cfg, user_id, "Trip")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Book the hotel", project_id=trip.id),
                                       created_by_bot=None, tainted=False)
    expense = await ExpenseStore(cfg).add(
        user_id, ExpenseDraft(food.id, Decimal("80"), spent_at=today_madrid(), task_id=task.id),
        created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("u1", "update_expense", expense=expense.id, project="trip", starred=True, void=True),
        _tool("u2", "update_expense", expense=expense.id, task=""),
        _tool("u3", "update_expense", expense=expense.id, project="Tripp"),
        _tool("u4", "update_expense", expense=expense.id, void=False),
        say("ok"),
    ]}, "that 80 was the trip: star it, void it, unlink it, then count it again")
    moved, unlinked, near, posted = _tool_texts(rig.model.requests[-1])
    today = today_madrid()
    assert moved == unlinked == f"Updated: 80.00 EUR on {today} [void] [starred]."
    assert near == "Refused: No project is called “Tripp”. Did you mean “Trip”? Say it exactly."
    assert posted == f"Updated: 80.00 EUR on {today} [starred]."
    kept = await ExpenseStore(cfg).get(user_id, expense.id)
    assert (kept.project_id, kept.is_favorite, kept.status, kept.task_id, kept.step_id) == (
        trip.id, True, "posted", None, None)


async def test_set_budget_never_creates_a_project_and_can_clear_one(cfg, user_id):
    """H3: set_budget is exact-or-ask now; H5: '' clears the total budget."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await _new_project(cfg, user_id, "Food")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("b1", "set_budget", project="Garden", amount=100),
        _tool("b2", "set_budget", project="food", amount=300),
        _tool("b3", "set_budget", project="Food", amount=""),
        say("ok"),
    ]}, "budget 100 for the garden and 300 for food; no, no food budget")
    unknown, budget, cleared = _tool_texts(rig.model.requests[-1])
    assert unknown == "Refused: No project is called “Garden”. Use create_project first."
    assert budget == "Budget for Food: 300.00 EUR."
    assert cleared == "Budget for Food cleared."
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Food"]
    assert (await ProjectStore(cfg).find(user_id, "Food")).budget is None


async def test_an_expense_with_no_currency_takes_its_projects(cfg, user_id):
    """H7: a dollar project's expense is in dollars unless the bot says otherwise."""
    bot = await make_bot(cfg, user_id, "Life admin")
    await _new_project(cfg, user_id, "Trip", currency="USD")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e1", "log_expense", amount=20, project="Trip"),
        _tool("e2", "log_expense", amount=5, project="Trip", currency="EUR"),
        say("ok"),
    ]}, "20 on the trip, and 5 euros")
    dollars, euros = _tool_texts(rig.model.requests[-1])
    assert dollars.startswith("Logged 20.00 USD to Trip on ") and euros.startswith("Logged 5.00 EUR to Trip on ")


async def test_list_expenses_reads_a_near_miss_project_and_refuses_an_unknown_one(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    food = await _new_project(cfg, user_id, "Food")
    travel = await _new_project(cfg, user_id, "Travel")
    for project, amount, note in ((food, "6", "bread"), (travel, "9", "bus")):
        await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal(amount), spent_at=today_madrid(),
                                                          description=note), created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("l1", "list_expenses", project="Fod"), _tool("l2", "list_expenses", project="Garden"), say("ok"),
    ]}, "what did I spend on food? and on the garden?")
    near, unknown = _tool_texts(rig.model.requests[-1])
    assert "bread" in near and "bus" not in near
    assert unknown == "Refused: No project is called “Garden”. Use create_project first."


async def test_log_expense_takes_a_project_id_and_never_makes_a_project_of_it(cfg, user_id):
    """list_projects prints ids, so a model may hand one to log_expense: it files
    the money there instead of creating a project named after the id."""
    bot = await make_bot(cfg, user_id, "Life admin")
    trip = await _new_project(cfg, user_id, "Trip")
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("e", "log_expense", amount=8, project=trip.id), say("ok"),
    ]}, "8 on the trip")
    [logged] = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 8.00 EUR to Trip on ")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Trip"]


async def test_an_expense_tool_keeps_a_tasks_money_in_the_tasks_project(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Life admin")
    reno = await _new_project(cfg, user_id, "Renovation")
    food = await _new_project(cfg, user_id, "Food")
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", project_id=reno.id),
                                       created_by_bot=None, tainted=False)
    bare = await TaskStore(cfg).create(user_id, TaskDraft(title="Buy stamps"), created_by_bot=None, tainted=False)
    loose = await ExpenseStore(cfg).add(user_id, ExpenseDraft(food.id, Decimal("4"), spent_at=today_madrid()),
                                        created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Life admin": [
        _tool("a", "log_expense", amount=5, task="Paint the hall", project="Food"),
        _tool("b", "log_expense", amount=5, task="Buy stamps", project="Food"),
        _tool("c", "update_expense", expense=loose.id, task="Paint the hall"),
        _tool("d", "update_expense", expense=loose.id, project="Food"),
        say("ok"),
    ]}, "money for the hall")
    first, second, third, fourth = _tool_texts(rig.model.requests[-1])
    assert first == fourth == "Refused: That task is in Renovation."
    assert second == "Refused: That task has no project."
    assert third.startswith("Updated: 4.00 EUR")
    assert await ExpenseStore(cfg).list_project(user_id, food.id) == ()
    assert [e.id for e in await ExpenseStore(cfg).list_project(user_id, reno.id)] == [loose.id]
    assert bare.project_id is None
