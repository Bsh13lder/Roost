"""ProjectService (projects hub Task 6): one place for projects — the list with
its numbers, a project's page, create / update / delete, top-ups, and
exact-or-ask names (H2, H3, H4, H7, H9, H10, H15)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import GENERAL_PROJECT_NAME, PROJECT_COLORS, TOPUP_SOURCE_MAX_CHARS
from roost.db.connection import init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentDraft, DocumentMeta
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import Expense, ExpenseDraft, ExpensePatch, ProjectDraft
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.money.topup_store import TopUpUndone
from roost.notes.models import Note, NoteDraft
from roost.notes.store import NoteStore
from roost.projects import service as service_module
from roost.projects.numbers import TaskMoney
from roost.projects.service import ProjectDetail, ProjectRefusal, ProjectService
from roost.tasks.models import Task, TaskDraft, TaskPatch
from roost.tasks.store import TaskStore
from team_helpers import frames_so_far, make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@dataclass(frozen=True)
class Rig:
    service: ProjectService
    projects: ProjectStore
    expenses: ExpenseStore
    tasks: TaskStore
    notes: NoteStore
    documents: DocumentStore
    events: EventHub


@pytest.fixture
def rig(cfg) -> Rig:
    projects, expenses, tasks = ProjectStore(cfg), ExpenseStore(cfg), TaskStore(cfg)
    notes, documents, events = NoteStore(cfg), DocumentStore(cfg), EventHub(cfg)
    service = ProjectService(projects, expenses, tasks, notes, documents, BotStore(cfg), events)
    return Rig(service, projects, expenses, tasks, notes, documents, events)


async def _expense(rig: Rig, user_id: str, project_id: str, amount: str, *, currency: str = "EUR",
                   spent_at: str | None = None, tainted: bool = False) -> Expense:
    draft = ExpenseDraft(project_id, Decimal(amount), currency=currency, spent_at=spent_at or today_madrid())
    return await rig.expenses.add(user_id, draft, created_by_bot=None, tainted=tainted)


async def _task(rig: Rig, user_id: str, title: str, project_id: str | None = None) -> Task:
    return await rig.tasks.create(user_id, TaskDraft(title=title, project_id=project_id),
                                  created_by_bot=None, tainted=False)


async def _note(rig: Rig, user_id: str, title: str, project_id: str, *, tainted: bool = False) -> Note:
    return await rig.notes.create(user_id, NoteDraft(title=title, content="green tiles", project_id=project_id),
                                  created_by_bot=None, tainted=tainted)


async def _doc(rig: Rig, user_id: str, title: str, project_id: str) -> DocumentMeta:
    body = json.dumps(doc_from_markdown(title, "- tiles"))
    return await rig.documents.create(user_id, DocumentDraft("doc", title, body, project_id=project_id),
                                      created_by_bot=None, tainted=False)


def _changes(frames: list[dict]) -> list[tuple[str, str]]:
    return [(frame["change"], frame["id"]) for frame in frames if frame["type"] == "money_changed"]


async def test_deleting_a_project_keeps_its_items_and_moves_its_money_to_general(rig, user_id):
    project = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    task = await _task(rig, user_id, "Buy tiles", project.id)
    note = await _note(rig, user_id, "Ideas", project.id)
    document = await _doc(rig, user_id, "Plan", project.id)
    expense = await _expense(rig, user_id, project.id, "40")
    subscription = rig.events.subscribe(user_id)

    assert await rig.service.delete(user_id, project.id) is True

    general = await rig.projects.find(user_id, GENERAL_PROJECT_NAME)
    assert general is not None
    kept_task = await rig.tasks.get(user_id, task.id)
    kept_note = await rig.notes.get(user_id, note.id)
    kept_document = await rig.documents.get_meta(user_id, document.id)
    assert (kept_task.title, kept_task.project_id) == ("Buy tiles", None)
    assert (kept_note.title, kept_note.project_id) == ("Ideas", None)
    assert (kept_document.title, kept_document.project_id) == ("Plan", None)
    moved = await rig.expenses.get(user_id, expense.id)
    assert (moved.project_id, moved.amount) == (general.id, Decimal("40"))
    assert await rig.projects.get(user_id, project.id) is None
    assert await rig.service.detail(user_id, project.id) is None
    assert _changes(await frames_so_far(subscription)) == [("project_deleted", project.id)]
    assert await rig.service.delete(user_id, project.id) is False


async def test_general_is_hidden_and_can_be_neither_changed_nor_deleted(rig, user_id):
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    shown = await rig.service.list(user_id, include_archived=True)
    assert [project.name for project, _, _ in shown] == ["Renovation"]
    for changes in ({"name": "Misc"}, {"status": "archived"}, {"color": PROJECT_COLORS[2]}):
        with pytest.raises(ValueError, match="General is where expenses with no project go"):
            await rig.service.update(user_id, general.id, changes)
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.delete(user_id, general.id)
    kept = await rig.projects.get(user_id, general.id)
    assert (kept.name, kept.status, kept.color) == (GENERAL_PROJECT_NAME, "active", general.color)


async def test_no_project_can_take_the_name_general(rig, user_id):
    with pytest.raises(ValueError, match="General is kept for expenses with no project"):
        await rig.service.create(user_id, ProjectDraft(name=" general "))
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    with pytest.raises(ValueError, match="General is kept for expenses with no project"):
        await rig.service.update(user_id, house.id, {"name": "GENERAL"})
    assert await rig.projects.find(user_id, GENERAL_PROJECT_NAME) is None


async def test_archiving_hides_a_project_until_asked_for(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.update(user_id, house.id, {"status": "archived"})).status == "archived"
    assert await rig.service.list(user_id) == ()
    assert [project.id for project, _, _ in await rig.service.list(user_id, include_archived=True)] == [house.id]
    assert (await rig.service.detail(user_id, house.id)).project.status == "archived"
    assert (await rig.service.update(user_id, house.id, {"status": "active"})).status == "active"
    assert [project.id for project, _, _ in await rig.service.list(user_id)] == [house.id]
    with pytest.raises(ValueError, match="either active or archived"):
        await rig.service.update(user_id, house.id, {"status": "done"})


async def test_the_list_puts_active_projects_first_sorted_by_name_and_is_capped(rig, user_id, monkeypatch):
    for name in ("trip", "House", "Attic"):
        await rig.service.create(user_id, ProjectDraft(name=name))
    attic = await rig.service.resolve(user_id, "Attic", change=True)
    await rig.service.update(user_id, attic.id, {"status": "archived"})
    shown = await rig.service.list(user_id, include_archived=True)
    assert [project.name for project, _, _ in shown] == ["House", "trip", "Attic"]
    monkeypatch.setattr(service_module, "PROJECT_LIST_LIMIT", 1)
    assert [project.name for project, _, _ in await rig.service.list(user_id)] == ["House"]


async def test_the_list_carries_each_projects_numbers_and_progress(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House", budget=Decimal("500"),
                                                            monthly_budget=Decimal("100")))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip", currency="USD"))
    await _expense(rig, user_id, house.id, "80")
    await _expense(rig, user_id, house.id, "30", currency="USD")
    await _expense(rig, user_id, trip.id, "12", currency="USD")
    await rig.tasks.complete(user_id, (await _task(rig, user_id, "Paint", house.id)).id)
    await rig.tasks.fail(user_id, (await _task(rig, user_id, "Fix the tap", house.id)).id)
    await _task(rig, user_id, "Tiles", house.id)
    pool = await _task(rig, user_id, "Pool", house.id)
    await rig.tasks.update(user_id, pool.id, TaskPatch({"status": "cancelled"}))
    await _task(rig, user_id, "Loose")

    rows = {project.name: (numbers, progress) for project, numbers, progress in await rig.service.list(user_id)}

    numbers, progress = rows["House"]
    total, month = numbers.total, numbers.month
    assert (numbers.currency, total.budget, total.spent, total.remaining, total.tone) == (
        "EUR", Decimal("500"), Decimal("80"), Decimal("420"), "ok")
    assert (month.budget, month.spent, month.remaining, month.used_percent, month.tone) == (
        Decimal("100"), Decimal("80"), Decimal("20"), 80, "warn")
    assert dict(numbers.other_currencies) == {"USD": Decimal("30")}
    assert (progress.done, progress.failed, progress.total) == (1, 1, 3)
    trip_numbers, trip_progress = rows["Trip"]
    assert (trip_numbers.currency, trip_numbers.total.spent, trip_numbers.total.budget) == (
        "USD", Decimal("12"), None)
    assert (trip_progress.done, trip_progress.failed, trip_progress.total) == (0, 0, 0)


async def test_the_lead_bot_must_be_one_of_the_users_own_bots(rig, cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs_bot = await make_bot(cfg, bob, "Builder")
    mine = await make_bot(cfg, user_id, "Fixer")
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await rig.service.create(user_id, ProjectDraft(name="House", lead_bot_id=bobs_bot.id))
    house = await rig.service.create(user_id, ProjectDraft(name="House", lead_bot_id=mine.id))
    assert house.lead_bot_id == mine.id
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await rig.service.update(user_id, house.id, {"lead_bot_id": bobs_bot.id})
    assert (await rig.service.detail(user_id, house.id)).lead_bot_name == "Fixer"
    assert (await rig.service.update(user_id, house.id, {"lead_bot_id": None})).lead_bot_id is None
    assert (await rig.service.detail(user_id, house.id)).lead_bot_name is None


async def test_the_currency_changes_only_while_the_project_has_no_money(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.update(user_id, house.id, {"currency": "USD"})).currency == "USD"
    await _expense(rig, user_id, house.id, "10", currency="USD")
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await rig.service.update(user_id, house.id, {"currency": "GBP"})
    kept = await rig.service.update(user_id, house.id, {"currency": "USD", "color": PROJECT_COLORS[3]})
    assert (kept.currency, kept.color) == ("USD", PROJECT_COLORS[3])
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    await rig.service.add_topup(user_id, trip.id, Decimal("50"))
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await rig.service.update(user_id, trip.id, {"currency": "USD"})
    assert (await rig.projects.get(user_id, trip.id)).currency == "EUR"


async def test_creating_and_changing_a_project_are_announced_on_money_changed(rig, user_id):
    subscription = rig.events.subscribe(user_id)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    home = await rig.service.update(user_id, house.id, {"name": "Home", "due_date": "2026-12-31"})
    assert (home.name, home.due_date) == ("Home", "2026-12-31")
    with pytest.raises(ValueError, match="A project with that name exists."):
        await rig.service.update(user_id, house.id, {"name": "trip"})
    assert await rig.service.update(user_id, "no-such-project", {"color": PROJECT_COLORS[1]}) is None
    assert _changes(await frames_so_far(subscription)) == [
        ("project_created", house.id), ("project_created", trip.id), ("project_updated", house.id),
    ]


async def test_top_ups_are_added_edited_and_undone_and_each_is_announced(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    subscription = rig.events.subscribe(user_id)

    topup = await rig.service.add_topup(user_id, house.id, Decimal("100"), "  birthday  ")
    assert (topup.kind, topup.amount, topup.source, topup.project_id, topup.undone) == (
        "credit", Decimal("100"), "birthday", house.id, False)
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("100")
    assert await rig.service.edit_topup(user_id, topup.id, Decimal("150")) is not None
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("150")
    assert await rig.service.undo_topup(user_id, topup.id) is not None
    assert ((await rig.projects.get(user_id, house.id)).budget or Decimal("0")) == Decimal("0")

    history = await rig.service.topups(user_id, house.id)
    assert sorted(row.kind for row in history) == ["credit", "edit"]
    assert all(row.undone for row in history)
    assert _changes(await frames_so_far(subscription)) == [
        ("topup_added", topup.id), ("topup_edited", topup.id), ("topup_undone", topup.id),
    ]


async def test_a_top_up_needs_a_positive_amount_and_a_short_source(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.add_topup(user_id, house.id, Decimal("0"))
    with pytest.raises(ValueError, match=f"at most {TOPUP_SOURCE_MAX_CHARS} characters"):
        await rig.service.add_topup(user_id, house.id, Decimal("5"), "x" * (TOPUP_SOURCE_MAX_CHARS + 1))
    plain = await rig.service.add_topup(user_id, house.id, Decimal("5"), "   ")
    assert plain.source is None
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.edit_topup(user_id, plain.id, Decimal("-1"))
    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("5")


async def test_the_board_sets_and_clears_the_total_budget_and_each_change_is_announced(rig, cfg, user_id):
    """P3, H5: the total budget is set or cleared through the service. Each
    change is a "Budget set" row and MoneyService's budget_set frame. General
    keeps no budget from here (H2), and another user's project is not found."""
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    subscription = rig.events.subscribe(user_id)

    assert (await rig.service.set_budget(user_id, house.id, Decimal("300"))).budget == Decimal("300.00")
    cleared = await rig.service.set_budget(user_id, house.id, None)

    assert cleared.budget is None and (await rig.projects.get(user_id, house.id)).budget is None
    history = await rig.service.topups(user_id, house.id)
    assert sorted((row.kind, row.amount, row.topup_id) for row in history) == [
        ("edit", Decimal("-300.00"), None), ("edit", Decimal("300.00"), None)]
    with pytest.raises(ValueError, match="more than 0"):
        await rig.service.set_budget(user_id, house.id, Decimal("0"))
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.set_budget(user_id, general.id, Decimal("50"))
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await rig.service.set_budget(bob, house.id, Decimal("10")) is None
    assert (await rig.projects.get(user_id, general.id)).budget is None
    assert (await rig.projects.get(user_id, house.id)).budget is None
    assert _changes(await frames_so_far(subscription)) == [("budget_set", house.id), ("budget_set", house.id)]


async def test_another_users_projects_and_top_ups_are_not_found(rig, cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    topup = await rig.service.add_topup(user_id, house.id, Decimal("10"))
    assert await rig.service.list(bob) == ()
    assert await rig.service.detail(bob, house.id) is None
    assert await rig.service.update(bob, house.id, {"color": PROJECT_COLORS[1]}) is None
    assert await rig.service.delete(bob, house.id) is False
    assert await rig.service.add_topup(bob, house.id, Decimal("10")) is None
    assert await rig.service.topups(bob, house.id) is None
    assert await rig.service.edit_topup(bob, topup.id, Decimal("20")) is None
    assert await rig.service.undo_topup(bob, topup.id) is None
    assert await rig.service.resolve(bob, house.id, change=False) == (
        f"No project is called “{house.id}”. Use create_project first.")
    kept = await rig.projects.get(user_id, house.id)
    assert (kept.budget, kept.color) == (Decimal("10"), house.color)


async def test_resolve_finds_a_project_by_id_exact_name_or_a_unique_part(rig, user_id):
    renovation = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    await rig.service.create(user_id, ProjectDraft(name="Trip"))
    for ref in (renovation.id, "renovation", "  RENOVATION ", "Renov"):
        for change in (False, True):
            found = await rig.service.resolve(user_id, ref, change=change)
            assert found.id == renovation.id, (ref, change)
    await rig.service.update(user_id, renovation.id, {"status": "archived"})
    assert (await rig.service.resolve(user_id, "Renovation", change=True)).id == renovation.id


async def test_a_near_miss_may_be_read_but_never_changed(rig, user_id):
    renovation = await rig.service.create(user_id, ProjectDraft(name="Renovation"))
    assert (await rig.service.resolve(user_id, "Renovaton", change=False)).id == renovation.id
    refusal = await rig.service.resolve(user_id, "Renovaton", change=True)
    assert isinstance(refusal, ProjectRefusal) and refusal.tainted is False
    assert refusal == "No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
    assert [project.name for project, _, _ in await rig.service.list(user_id)] == ["Renovation"]


async def test_several_matches_ask_which_one_and_carry_the_taint_of_the_names_shown(rig, user_id):
    await rig.service.create(user_id, ProjectDraft(name="Kitchen paint"))
    await rig.service.create(user_id, ProjectDraft(name="Garage paint"), tainted=True)
    refusal = await rig.service.resolve(user_id, "paint", change=False)
    assert refusal == ("Several projects match “paint”. "
                       "Say which one: “Garage paint” [from web content]; “Kitchen paint”.")
    assert refusal.tainted is True


async def test_an_unknown_name_is_refused_and_never_creates_a_project(rig, user_id):
    for change in (False, True):
        refusal = await rig.service.resolve(user_id, " Garden ", change=change)
        assert refusal == "No project is called “Garden”. Use create_project first."
        assert refusal.tainted is False
    assert await rig.service.list(user_id, include_archived=True) == ()
    assert await rig.projects.find(user_id, "Garden") is None


async def test_the_detail_holds_the_numbers_items_top_ups_and_lead(rig, cfg, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await rig.service.create(user_id, ProjectDraft(name="House", budget=Decimal("200"), lead_bot_id=lead.id))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    await rig.service.add_topup(user_id, house.id, Decimal("50"), "bonus")
    lunch = await _expense(rig, user_id, house.id, "40")
    void = await _expense(rig, user_id, house.id, "25")
    await rig.expenses.update(user_id, void.id, ExpensePatch({"status": "void"}))
    dollars = await _expense(rig, user_id, house.id, "9", currency="USD")
    await _expense(rig, user_id, trip.id, "70")
    task = await _task(rig, user_id, "Paint", house.id)
    note = await _note(rig, user_id, "Ideas", house.id)
    document = await _doc(rig, user_id, "Plan", house.id)

    detail = await rig.service.detail(user_id, house.id)

    assert isinstance(detail, ProjectDetail) and detail.project.id == house.id
    total = detail.numbers.total
    assert (total.budget, total.spent, total.remaining) == (Decimal("250"), Decimal("40"), Decimal("210"))
    assert dict(detail.numbers.other_currencies) == {"USD": Decimal("9")}
    assert {expense.id for expense in detail.expenses} == {lunch.id, void.id, dollars.id}
    assert [row.id for row in detail.tasks] == [task.id]
    assert [row.id for row in detail.notes] == [note.id]
    assert [row.id for row in detail.documents] == [document.id]
    assert [row.source for row in detail.topups if row.kind == "credit"] == ["bonus"]
    assert (detail.progress.total, detail.lead_bot_name, detail.tainted) == (1, "Fixer", False)


async def test_the_detail_shows_the_latest_page_of_expenses_notes_and_documents(rig, user_id, monkeypatch):
    monkeypatch.setattr(service_module, "PROJECT_PAGE_ITEMS", 2)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    for number in (1, 2, 3):
        await _expense(rig, user_id, house.id, str(number), spent_at=f"2026-10-0{number}")
        await _note(rig, user_id, f"Note {number}", house.id)
        await _doc(rig, user_id, f"Doc {number}", house.id)

    detail = await rig.service.detail(user_id, house.id)

    assert [expense.amount for expense in detail.expenses] == [Decimal("3"), Decimal("2")]
    assert detail.numbers.total.spent == Decimal("6")
    assert [note.title for note in detail.notes] == ["Note 3", "Note 2"]
    assert [document.title for document in detail.documents] == ["Doc 3", "Doc 2"]


async def test_the_detail_gives_each_task_its_planned_spent_and_left(rig, user_id, monkeypatch):
    """Design §2 and P6: a task's budget slice against the counted expenses linked
    to it, over every expense of the project, not only the latest page."""
    monkeypatch.setattr(service_module, "PROJECT_PAGE_ITEMS", 1)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    paint = await rig.tasks.create(user_id, TaskDraft(title="Paint", project_id=house.id,
                                                      allocated_budget=Decimal("100")),
                                   created_by_bot=None, tainted=False)
    tiles = await _task(rig, user_id, "Tiles", house.id)
    for amount, task_id in (("30", paint.id), ("12.50", paint.id), ("99", None)):
        draft = ExpenseDraft(house.id, Decimal(amount), spent_at=today_madrid(), task_id=task_id)
        await rig.expenses.add(user_id, draft, created_by_bot=None, tainted=False)

    detail = await rig.service.detail(user_id, house.id)

    assert len(detail.expenses) == 1
    assert dict(detail.task_money) == {
        paint.id: TaskMoney(planned=Decimal("100"), spent=Decimal("42.50"), left=Decimal("57.50")),
        tiles.id: TaskMoney(planned=None, spent=Decimal("0"), left=None),
    }


async def test_the_detail_is_tainted_when_the_project_or_anything_it_shows_is_web_made(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    assert (await rig.service.detail(user_id, house.id)).tainted is False
    await _expense(rig, user_id, house.id, "5", tainted=True)
    assert (await rig.service.detail(user_id, house.id)).tainted is True
    garden = await rig.service.create(user_id, ProjectDraft(name="Garden"))
    await _note(rig, user_id, "From a page", garden.id, tainted=True)
    assert (await rig.service.detail(user_id, garden.id)).tainted is True
    web = await rig.service.create(user_id, ProjectDraft(name="Web"), tainted=True)
    assert (await rig.service.detail(user_id, web.id)).tainted is True


async def test_the_detail_is_tainted_by_a_web_made_expense_of_another_project_that_changes_a_tasks_spent(rig, user_id):
    """A task's spent counts every expense linked to it, whatever project it is filed under, and the page
    shows that spent: so a web-made one behind the number taints the page, a long way from its own project."""
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip"))
    paint = await _task(rig, user_id, "Paint", house.id)
    assert (await rig.service.detail(user_id, house.id)).tainted is False

    def linked(project_id, **fields):
        draft = ExpenseDraft(project_id, Decimal("30"), spent_at=today_madrid(), task_id=paint.id, **fields)
        return rig.expenses.add(user_id, draft, created_by_bot=None, tainted=True)

    await linked(trip.id, currency="USD")                    # another currency: not in the task's spent
    voided = await linked(trip.id)
    await rig.expenses.update(user_id, voided.id, ExpensePatch({"status": "void"}))   # void: not in the sum
    await rig.expenses.add(user_id, ExpenseDraft(trip.id, Decimal("5"), spent_at=today_madrid()),
                           created_by_bot=None, tainted=True)                         # linked to no task
    assert (await rig.service.detail(user_id, house.id)).tainted is False

    counted = await linked(trip.id)                          # posted, in EUR, filed under Trip
    detail = await rig.service.detail(user_id, house.id)
    assert detail.task_money[paint.id].spent == Decimal("30.00")
    assert detail.tainted is True
    assert (await rig.service.detail(user_id, trip.id)).tainted is True      # its own page already was
    await rig.expenses.keep(user_id, counted.id)
    assert (await rig.service.detail(user_id, house.id)).tainted is False


async def test_a_top_up_taken_back_by_clearing_the_budget_is_refused_and_announced_as_nothing(rig, user_id):
    """Task 2 review: set 300, top up 50, clear, set 200. The clearing took the 50 back, so undoing or editing
    it is a broken rule (ValueError, a 422 in HTTP), never TopUpUndone (409), and no frame goes out."""
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    await rig.service.set_budget(user_id, house.id, Decimal("300"))
    topup = await rig.service.add_topup(user_id, house.id, Decimal("50"))
    await rig.service.set_budget(user_id, house.id, None)
    await rig.service.set_budget(user_id, house.id, Decimal("200"))
    subscription = rig.events.subscribe(user_id)

    attempts = (lambda: rig.service.undo_topup(user_id, topup.id),
                lambda: rig.service.edit_topup(user_id, topup.id, Decimal("80")))
    for attempt in attempts:
        with pytest.raises(ValueError, match="already taken back when the budget was cleared") as refused:
            await attempt()
        assert not isinstance(refused.value, TopUpUndone)

    assert (await rig.projects.get(user_id, house.id)).budget == Decimal("200.00")
    assert _changes(await frames_so_far(subscription)) == []


async def test_the_service_refuses_an_amount_the_ledger_could_not_hold(rig, user_id):
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    for amount, message in ((Decimal("0.005"), "at most 2 decimals"), (Decimal("-5"), "more than 0")):
        with pytest.raises(ValueError, match=message):
            await rig.service.set_budget(user_id, house.id, amount)
        with pytest.raises(ValueError, match=message):
            await rig.service.add_topup(user_id, house.id, amount)
    assert await rig.service.topups(user_id, house.id) == ()
    assert (await rig.projects.get(user_id, house.id)).budget is None


async def test_general_takes_no_top_up_either(rig, user_id):
    """H2: the Board can no more budget General through a top-up than through set_budget."""
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    subscription = rig.events.subscribe(user_id)
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.add_topup(user_id, general.id, Decimal("50"))
    assert (await rig.projects.get(user_id, general.id)).budget is None
    assert await rig.service.topups(user_id, general.id) == ()
    assert _changes(await frames_so_far(subscription)) == []


async def test_keep_clears_a_web_made_projects_mark_and_announces_it(rig, user_id):
    """A project made from web content is vouched for by the user (Keep): the taint bit goes,
    the project is announced as updated, and the name and money stay."""
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip", budget=Decimal("2000")), tainted=True)
    subscription = rig.events.subscribe(user_id)

    kept = await rig.service.keep(user_id, trip.id)

    assert (kept.id, kept.name, kept.tainted, kept.budget) == (trip.id, "Trip", False, Decimal("2000"))
    assert (await rig.projects.get(user_id, trip.id)).tainted is False
    assert _changes(await frames_so_far(subscription)) == [("project_updated", trip.id)]


async def test_keep_of_a_project_that_is_not_there_or_not_yours_is_none_and_announces_nothing(rig, cfg, user_id):
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    web = await rig.service.create(user_id, ProjectDraft(name="Web"), tainted=True)
    subscription = rig.events.subscribe(user_id)

    assert await rig.service.keep(bob, web.id) is None
    assert await rig.service.keep(user_id, "no-such-project") is None

    assert (await rig.projects.get(user_id, web.id)).tainted is True      # bob's Keep changed nothing
    assert _changes(await frames_so_far(subscription)) == []


async def test_a_tasks_spent_counts_every_expense_linked_to_it_in_any_project(rig, cfg, user_id):
    """H11: spent is every counted expense with the task's id, in the task's project currency, whatever
    project the expense is filed under (it may have been logged before the task moved, or elsewhere).
    Void ones and other currencies are not counted, and another user's expenses never are."""
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    garden = await rig.service.create(user_id, ProjectDraft(name="Garden"))
    trip = await rig.service.create(user_id, ProjectDraft(name="Trip", currency="USD"))
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    paint = await rig.tasks.create(user_id, TaskDraft(title="Paint", project_id=house.id,
                                                      allocated_budget=Decimal("100")),
                                   created_by_bot=None, tainted=False)
    elsewhere = await rig.service.create(bob, ProjectDraft(name="House"))

    async def spend(owner: str, project_id: str, amount: str, currency: str = "EUR", task_id: str | None = paint.id):
        draft = ExpenseDraft(project_id, Decimal(amount), currency=currency, spent_at=today_madrid(), task_id=task_id)
        return await rig.expenses.add(owner, draft, created_by_bot=None, tainted=False)

    await spend(user_id, house.id, "30")                      # in its own project
    await spend(user_id, garden.id, "12.50")                  # filed under another project
    await spend(user_id, general.id, "7")                     # filed under General
    await spend(user_id, trip.id, "99", currency="USD")       # another currency than the task's project
    await spend(user_id, garden.id, "100", task_id=None)      # not linked to the task
    void = await spend(user_id, garden.id, "5")
    await rig.expenses.update(user_id, void.id, ExpensePatch({"status": "void"}))
    await spend(bob, elsewhere.id, "1000")                    # someone else's, with the same task id

    detail = await rig.service.detail(user_id, house.id)

    assert detail.task_money[paint.id] == TaskMoney(planned=Decimal("100"), spent=Decimal("49.50"),
                                                    left=Decimal("50.50"))
    assert detail.numbers.total.spent == Decimal("30")       # the project's own total is still its own expenses


async def test_only_general_is_refused_as_a_link_target(rig, cfg, user_id):
    """H2: ensure_linkable refuses General with the service's own sentence. No link, a real project, an
    archived one, another user's id and an unknown id all pass (the record's write says "No such project.")."""
    general = await rig.projects.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    house = await rig.service.create(user_id, ProjectDraft(name="House"))
    attic = await rig.service.create(user_id, ProjectDraft(name="Attic"))
    await rig.service.update(user_id, attic.id, {"status": "archived"})
    bob = (await register_user(cfg, "bob", "pw-123456")).id

    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await rig.service.ensure_linkable(user_id, general.id)
    for project_id in (None, house.id, attic.id, "no-such-project"):
        assert await rig.service.ensure_linkable(user_id, project_id) is None
    assert await rig.service.ensure_linkable(bob, general.id) is None      # not bob's General
