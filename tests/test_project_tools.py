"""Bots learn projects (projects hub Task 7): the project tools over the user's
projects, exact-or-ask project names on every record tool (H3), top-ups as
changes (H4), the lead bot (H15), and the tainted-write rule over all of it
(M1 D3)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.constants import PROJECT_COLORS
from roost.db.connection import init_db
from roost.documents.service import DocumentService
from roost.documents.store import DocumentStore
from roost.documents.tool_specs import DOCUMENT_TOOL_DEFS
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.projects.tool_specs import PROJECT_TOOL_DEFS
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

NEAR_MISS = "Refused: No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
NO_GARDEN = "Refused: No project is called “Garden”. Use create_project first."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, /, **arguments):
    """Positional-only: create_project and update_project take a ``name`` argument of their own."""
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _project(cfg, user_id, name: str, *, tainted: bool = False, **fields):
    return await ProjectStore(cfg).create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None,
                                          tainted=tainted)


def _documents(cfg) -> DocumentService:
    return DocumentService(DocumentStore(cfg), EventHub(cfg))


def test_the_project_tools_and_their_gate_kinds():
    """Design §3 with H4: a top-up changes an existing budget, so it is a change.
    Deleting a project is the Board's alone, never a tool."""
    assert [(tool.name, tool.kind) for tool in PROJECT_TOOL_DEFS] == [
        ("list_projects", "read"), ("get_project", "read"), ("create_project", "write_create"),
        ("update_project", "write_change"), ("add_topup", "write_change"), ("edit_topup", "write_change"),
        ("undo_topup", "write_change"),
    ]
    assert {tool.name: tool.kind for tool in DOCUMENT_TOOL_DEFS}["set_document_project"] == "write_change"
    names = list(CATALOG)
    assert names.index("list_projects") == names.index("set_document_project") + 1
    assert "delete_project" not in CATALOG
    for tool in PROJECT_TOOL_DEFS:
        text = tool.spec.description + json.dumps(tool.spec.input_schema)
        assert " role" not in tool.spec.description and "control" not in tool.name
        assert "categor" not in text.casefold(), tool.name


async def test_a_near_miss_project_name_never_changes_anything(cfg, user_id):
    """Review Focus 1 (H3): "Renovaton" for "Renovation". A read may answer with
    the near project; every change and every new record is refused with "Did
    you mean …?"; only log_expense (find-or-create) files money there."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "Renovation")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall"), created_by_bot=None, tainted=False)
    await NoteStore(cfg).create(user_id, NoteDraft(title="Ideas", content="green tiles"), created_by_bot=None,
                                tainted=False)
    await _documents(cfg).create_doc(user_id, "Plan", "- tiles")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    near = "Renovaton"
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("g", "get_project", project=near),
        _tool("l", "list_tasks", project=near),
        _tool("u", "update_project", project=near, name="Kitchen"),
        _tool("a", "add_topup", project=near, amount=50),
        _tool("b", "set_budget", project=near, amount=500),
        _tool("t", "add_task", title="Buy tiles", project=near),
        _tool("ut", "update_task", task="Paint the hall", project=near),
        _tool("n", "add_note", content="Green tiles", project=near),
        _tool("un", "update_note", note="Ideas", project=near),
        _tool("d", "create_doc", title="Tiles", markdown="- green", project=near),
        _tool("sd", "set_document_project", document="Plan", project=near),
        _tool("ue", "update_expense", expense=expense.id, project=near),
        _tool("e", "log_expense", amount=12, project=near),
        say("Which project did you mean?"),
    ]}, "put everything in Renovaton")
    texts = _tool_texts(rig.model.requests[-1])
    assert texts[0].startswith("“Renovation” in EUR") and texts[1] == "No tasks match."
    assert texts[2:12] == [NEAR_MISS] * 10
    assert texts[12].startswith(f"Logged 12.00 EUR to Renovation on {today_madrid()}")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Renovation"]
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.budget) == ("Renovation", None)
    assert await ProjectStore(cfg).topups(user_id, project.id) == ()
    assert [(t.title, t.project_id) for t in await TaskStore(cfg).list(user_id, status="all")] == [
        ("Paint the hall", None)]
    assert [(n.title, n.project_id) for n in await NoteStore(cfg).list(user_id)] == [("Ideas", None)]
    assert [(m.title, m.project_id) for m in await DocumentStore(cfg).list(user_id)] == [("Plan", None)]
    assert sorted(e.amount for e in await ExpenseStore(cfg).list_project(user_id, project.id)) == [
        Decimal("10.00"), Decimal("12.00")]


async def test_a_tainted_run_cannot_change_projects_or_their_money(cfg, user_id):
    """Review Focus 5 (H4, M1 D3): after a page read, add_topup, undo_topup,
    update_project and set_document_project are all changes, each refused with
    the tainted-change text, and nothing moves."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    topup = await ProjectStore(cfg).add_topup(user_id, project.id, Decimal("50"), "gift", created_by_bot=None,
                                              tainted=False)
    plan = await _documents(cfg).create_doc(user_id, "Plan", "- tiles")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_topup", project="House", amount=1000, source="the page"),
        _tool("u", "undo_topup", topup=topup.id),
        _tool("r", "update_project", project="House", name="Ours now", archived=True),
        _tool("s", "set_document_project", document="Plan", project="House"),
        say("No."),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[1:] == [TAINTED_CHANGE_TEXT] * 4
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.status, kept.budget) == ("House", "active", Decimal("50.00"))
    assert [row.undone for row in await ProjectStore(cfg).topups(user_id, project.id)] == [False]
    assert (await DocumentStore(cfg).get_meta(user_id, plan.id)).project_id is None


async def test_a_bot_creates_a_project_then_lists_and_reads_it(cfg, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("c", "create_project", name="Renovation", budget="500", monthly_budget=100, color=PROJECT_COLORS[6],
              due_date="2026-12-31", lead_bot="fixer"),
        _tool("e", "log_expense", amount=80, project="Renovation", note="paint"),
        _tool("t", "add_task", title="Paint the hall", project="renovation"),
        _tool("l", "list_projects"),
        _tool("g", "get_project", project="renovation"),
        say("Done."),
    ]}, "start a Renovation project: 500 in total, 100 a month, due at the end of the year, led by Fixer")
    created, logged, added, listed, page = _tool_texts(rig.model.requests[-1])
    assert created.startswith("Created project “Renovation” in EUR, budget 500.00 EUR, monthly limit 100.00 EUR, "
                              "due 2026-12-31 id=")
    assert logged.startswith("Logged 80.00 EUR to Renovation on ")
    assert added.startswith("Added: ") and added.endswith(" Project: “Renovation”.")
    assert ("- “Renovation” · total: 80.00 EUR of 500.00 EUR, 420.00 EUR left (16%) · "
            "this month: 80.00 EUR of 100.00 EUR, 20.00 EUR left (80%) · tasks: 0 done of 1 id=") in listed
    assert "Lead bot: Fixer · due 2026-12-31" in page
    assert "Paint the hall" in page and "· paint" in page
    project = await ProjectStore(cfg).find(user_id, "Renovation")
    assert (project.color, project.lead_bot_id, project.due_date, project.created_by_bot, project.tainted) == (
        PROJECT_COLORS[6], lead.id, "2026-12-31", bot.id, False)
    [task] = await TaskStore(cfg).list(user_id)
    assert task.project_id == project.id


async def test_get_project_shows_each_tasks_planned_spent_and_left(cfg, user_id):
    """Design §2 and P6: a task's budget slice against the counted expenses
    linked to it (Task 6's ProjectDetail.task_money)."""
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "Renovation")
    paint = await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall", project_id=project.id,
                                                           allocated_budget=Decimal("100")),
                                        created_by_bot=None, tainted=False)
    tiles = await TaskStore(cfg).create(user_id, TaskDraft(title="Tiles", project_id=project.id),
                                        created_by_bot=None, tainted=False)
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(project.id, Decimal("130"), spent_at=today_madrid(),
                                                      task_id=paint.id), created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Helper": [_tool("g", "get_project", project="Renovation"), say("ok")]},
                      "how is the hall going?")
    [page] = _tool_texts(rig.model.requests[-1])
    assert f"Paint the hall id={paint.id} · budget 100.00 EUR, spent 130.00 EUR, over by 30.00 EUR" in page
    assert page.count(f"Tiles id={tiles.id}") == 1 and f"Tiles id={tiles.id} ·" not in page


async def test_update_project_renames_archives_and_clears_the_monthly_limit(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House", monthly_budget=Decimal("50"))
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("u1", "update_project", project="house", name="Home", color=PROJECT_COLORS[2], start_date="2026-10-01",
              monthly_budget=""),
        _tool("u2", "update_project", project="Home", archived=True),
        _tool("l1", "list_projects"),
        _tool("l2", "list_projects", include_archived=True),
        _tool("u3", "update_project", project="Home", archived=False, color="pink"),
        _tool("u4", "update_project", project="Home"),
        say("ok"),
    ]}, "rename House to Home from 1 October, drop its monthly limit, then archive it")
    renamed, archived, hidden, shown, bad_colour, nothing = _tool_texts(rig.model.requests[-1])
    assert renamed.startswith("Updated: “Home” in EUR, starts 2026-10-01 id=") and "monthly limit" not in renamed
    assert archived.startswith("Updated: “Home” [archived] in EUR")
    assert hidden == "No active projects."
    assert shown.startswith("- “Home” [archived] · total: 0.00 EUR spent")
    assert bad_colour.startswith("Refused: A project colour is one of #64748b, ")
    assert nothing == "Refused: update_project needs something to change."
    kept = await ProjectStore(cfg).get(user_id, project.id)
    assert (kept.name, kept.color, kept.start_date, kept.monthly_budget, kept.status) == (
        "Home", PROJECT_COLORS[2], "2026-10-01", None, "archived")


async def test_the_lead_bot_is_one_of_the_users_own_bots(cfg, user_id):
    """H15: another user's bot is not found; '' clears the lead."""
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await make_bot(cfg, bob, "Builder")
    await make_bot(cfg, user_id, "Fixer")
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("u1", "update_project", project="House", lead_bot="Builder"),
        _tool("u2", "update_project", project="House", lead_bot="@fixer"),
        _tool("g", "get_project", project="House"),
        _tool("u3", "update_project", project="House", lead_bot=""),
        say("ok"),
    ]}, "let Fixer lead the House project, then nobody")
    refused, led, page, cleared = _tool_texts(rig.model.requests[-1])
    assert refused == "Refused: None of your bots is called “Builder”."
    assert led.startswith("Updated: “House” in EUR") and "Lead bot: Fixer" in page
    assert cleared.startswith("Updated: “House” in EUR")
    assert (await ProjectStore(cfg).get(user_id, project.id)).lead_bot_id is None


async def test_a_top_up_is_added_changed_and_undone_with_its_history(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    project = await _project(cfg, user_id, "House")
    first = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("a", "add_topup", project="house", amount="100", source="birthday"), say("Added."),
    ]}, "add the 100 from my birthday to House")
    [credit] = [row for row in await ProjectStore(cfg).topups(user_id, project.id) if row.kind == "credit"]
    assert _tool_texts(first.model.requests[-1]) == [
        f"Added a 100.00 EUR top-up (id={credit.id}). The total budget of “House” is now 100.00 EUR."]
    second = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "edit_topup", topup=credit.id, amount=150),
        _tool("g", "get_project", project="House"),
        _tool("u", "undo_topup", topup=credit.id),
        _tool("a", "undo_topup", topup=credit.id),
        _tool("x", "undo_topup", topup="no-such-top-up"),
        say("ok"),
    ]}, "it was 150, actually; no, undo it")
    edited, page, undone, again, missing = _tool_texts(second.model.requests[-1])
    assert edited == "Changed the top-up to 150.00 EUR. The total budget of “House” is now 150.00 EUR."
    assert "Top-up 100.00 EUR · birthday" in page and "Top-up changed 50.00 EUR" in page
    assert undone.startswith("Undid the top-up and its changes.")
    assert again == "Refused: That top-up was undone already."
    assert missing == "Refused: there is no top-up with that id."
    assert ((await ProjectStore(cfg).get(user_id, project.id)).budget or Decimal("0")) == Decimal("0")


async def test_an_unknown_project_is_refused_and_only_log_expense_makes_one(cfg, user_id):
    """H3: a name no project has is refused everywhere but log_expense."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("g", "get_project", project="Garden"),
        _tool("t", "add_task", title="Plant roses", project="Garden"),
        _tool("n", "add_note", content="Roses like sun", project="Garden"),
        _tool("d", "create_doc", title="Roses", markdown="- sun", project="Garden"),
        _tool("b", "set_budget", project="Garden", amount=100),
        _tool("e", "log_expense", amount=7, project="Garden", note="seeds"),
        say("ok"),
    ]}, "start a garden")
    texts = _tool_texts(rig.model.requests[-1])
    assert texts[:5] == [NO_GARDEN] * 5
    assert texts[5].startswith("Logged 7.00 EUR to Garden on ")
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["Garden"]
    assert await TaskStore(cfg).list(user_id, status="all") == ()
    assert await NoteStore(cfg).list(user_id) == ()
    assert await DocumentStore(cfg).list(user_id) == ()


async def test_several_matching_projects_ask_which_and_a_web_made_name_taints_the_run(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    kitchen = await _project(cfg, user_id, "Kitchen paint")
    await _project(cfg, user_id, "Garage paint", tainted=True)
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("t", "add_task", title="Buy rollers", project="paint"),
        _tool("u", "update_project", project="Kitchen paint", color=PROJECT_COLORS[1]),
        say("Which one?"),
    ]}, "add buy rollers to the paint project")
    which, refused = _tool_texts(rig.model.requests[-1])
    assert which == ("Refused: Several projects match “paint”. "
                     "Say which one: “Garage paint” [from web content]; “Kitchen paint”.")
    assert refused == TAINTED_CHANGE_TEXT
    assert (await ProjectStore(cfg).get(user_id, kitchen.id)).color == kitchen.color
    assert await TaskStore(cfg).list(user_id) == ()


async def test_listing_projects_over_web_made_money_taints_the_run(cfg, user_id):
    """As with money_summary: a web-made expense behind the sums a listing
    prints taints the run; a clean listing leaves it free to change things."""
    bot = await make_bot(cfg, user_id, "Helper")
    house = await _project(cfg, user_id, "House")
    clean = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("l", "list_projects"), _tool("u", "update_project", project="House", color=PROJECT_COLORS[3]),
        say("ok"),
    ]}, "how are my projects? and make House yellow")
    assert _tool_texts(clean.model.requests[-1])[1].startswith("Updated: “House”")
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(house.id, Decimal("9"), spent_at=today_madrid()),
                                created_by_bot=None, tainted=True)
    web = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("l", "list_projects"), _tool("u", "update_project", project="House", color=PROJECT_COLORS[4]),
        say("No."),
    ]}, "how are my projects now? and make House green")
    listing, refused = _tool_texts(web.model.requests[-1])
    assert "total: 9.00 EUR spent" in listing and refused == TAINTED_CHANGE_TEXT
    assert (await ProjectStore(cfg).get(user_id, house.id)).color == PROJECT_COLORS[3]


async def test_general_stays_hidden_and_no_bot_can_change_or_take_its_name(cfg, user_id):
    """H2 through the tools: loose money goes to General, which the list hides
    and no bot may rename, archive or copy."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "log_expense", amount=3, note="coffee"),
        _tool("l", "list_projects", include_archived=True),
        _tool("u", "update_project", project="General", name="Misc"),
        _tool("c", "create_project", name="general"),
        say("ok"),
    ]}, "3 on coffee, then rename General to Misc")
    logged, listed, renamed, created = _tool_texts(rig.model.requests[-1])
    assert logged.startswith("Logged 3.00 EUR to General on ")
    assert listed == "No projects yet."
    assert renamed == "Refused: General is where expenses with no project go; it cannot be changed or deleted."
    assert created == "Refused: General is kept for expenses with no project; pick another name."
    assert [p.name for p in await ProjectStore(cfg).list(user_id)] == ["General"]


GENERAL_FIXED = "Refused: General is where expenses with no project go; it cannot be changed or deleted."


async def test_set_budget_refuses_general(cfg, user_id):
    """Carried from Task 6: General has no budget (H2), so the money tool's
    set_budget refuses it as the project tools do, and nothing is written."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "log_expense", amount=3, note="coffee"),
        _tool("b", "set_budget", project="General", amount=100),
        _tool("t", "add_topup", project="general", amount=10),
        say("No."),
    ]}, "3 on coffee, then give General a budget of 100")
    _, budget, topup = _tool_texts(rig.model.requests[-1])
    assert budget == GENERAL_FIXED and topup == GENERAL_FIXED
    general = await ProjectStore(cfg).find(user_id, "General")
    assert general.budget is None and await ProjectStore(cfg).topups(user_id, general.id) == ()


async def test_nothing_is_linked_to_general_through_any_tool(cfg, user_id):
    """Carried from Task 6: General is hidden, so a task, note or document
    cannot be filed in it; money may still be moved there (it is where loose
    money goes)."""
    bot = await make_bot(cfg, user_id, "Helper")
    house = await _project(cfg, user_id, "House")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Paint the hall"), created_by_bot=None, tainted=False)
    await NoteStore(cfg).create(user_id, NoteDraft(title="Ideas", content="green tiles"), created_by_bot=None,
                                tainted=False)
    await _documents(cfg).create_doc(user_id, "Plan", "- tiles")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(house.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("e", "log_expense", amount=3, note="coffee"),
        _tool("t", "add_task", title="Buy tiles", project="General"),
        _tool("ut", "update_task", task="Paint the hall", project="general"),
        _tool("n", "add_note", content="Green tiles", project="General"),
        _tool("un", "update_note", note="Ideas", project="General"),
        _tool("d", "create_doc", title="Tiles", markdown="- green", project="General"),
        _tool("s", "create_sheet", title="Costs", rows=[["a"]], project="General"),
        _tool("sd", "set_document_project", document="Plan", project="General"),
        _tool("ue", "update_expense", expense=expense.id, project="General"),
        say("ok"),
    ]}, "put everything in General")
    texts = _tool_texts(rig.model.requests[-1])
    assert texts[1:8] == [GENERAL_FIXED] * 7
    assert texts[8].startswith("Updated: 10.00 EUR on ")
    assert [(t.title, t.project_id) for t in await TaskStore(cfg).list(user_id, status="all")] == [
        ("Paint the hall", None)]
    assert [(n.title, n.project_id) for n in await NoteStore(cfg).list(user_id)] == [("Ideas", None)]
    assert [(m.title, m.project_id) for m in await DocumentStore(cfg).list(user_id)] == [("Plan", None)]
    general = await ProjectStore(cfg).find(user_id, "General")
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).project_id == general.id


async def test_failing_a_task_with_other_changes_still_closes_it_through_fail(cfg, user_id):
    """Carried from Task 4: status failed is never a plain patch, so
    completed_at is set whatever else the call changes."""
    bot = await make_bot(cfg, user_id, "Helper")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Fix the tap"), created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("f", "update_task", task="Fix the tap", status="failed", priority="high"),
        _tool("f2", "update_task", task="Fix the tap", status="failed"),
        say("ok"),
    ]}, "the tap could not be fixed")
    failed, again = _tool_texts(rig.model.requests[-1])
    assert failed == "Failed: Fix the tap."
    assert again.startswith("Refused: no open task matches")
    [closed] = await TaskStore(cfg).list(user_id, status="failed")
    assert (closed.status, closed.priority) == ("failed", "high") and closed.completed_at is not None


async def test_starred_and_void_are_read_as_real_booleans(cfg, user_id):
    """Carried from Task 3: ExpensePatch rejects a non-bool is_favorite, so the
    tool hands it a real bool whatever form the model sent."""
    bot = await make_bot(cfg, user_id, "Helper")
    house = await _project(cfg, user_id, "House")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(house.id, Decimal("10"), spent_at=today_madrid()),
                                          created_by_bot=None, tainted=False)
    rig = await _talk(cfg, user_id, bot, {"Helper": [
        _tool("a", "update_expense", expense=expense.id, starred="true", void="false"),
        _tool("b", "update_expense", expense=expense.id, starred=0, void=1),
        _tool("c", "log_expense", amount=2, project="House", starred="yes"),
        say("ok"),
    ]}, "star it; no, unstar and void it; and star a new one")
    starred, voided, logged = _tool_texts(rig.model.requests[-1])
    today = today_madrid()
    assert starred == f"Updated: 10.00 EUR on {today} [starred]."
    assert voided == f"Updated: 10.00 EUR on {today} [void]."
    assert ", starred (id=" in logged
    kept = await ExpenseStore(cfg).get(user_id, expense.id)
    assert (kept.is_favorite, kept.status) == (False, "void")
