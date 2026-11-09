"""Projects (projects hub Task 2: H2, H4, H5, H9, H15, H16): the new fields,
renaming, archiving, both budgets, top-ups and their history, and deleting a
project. Encrypted, per user, and ``budget == Σ live top-up rows`` while a
total budget is set."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import DEFAULT_PROJECT_COLOR, GENERAL_PROJECT_NAME, PROJECT_COLORS
from roost.db.connection import db_session, init_db
from roost.documents.doc_markdown import doc_from_markdown
from roost.documents.models import DocumentDraft
from roost.documents.store import DocumentStore
from roost.gateway.auth import register_user
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft, ProjectPatch
from roost.money.project_store import ProjectStore, is_general
from roost.money.topup_store import TopUpUndone, moved_budget
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
def store(cfg) -> ProjectStore:
    return ProjectStore(cfg)


async def _create(store, user_id, name="Renovation", **fields):
    return await store.create(user_id, ProjectDraft(name=name, **fields), created_by_bot=None, tainted=False)


async def _topup(store, user_id, project_id, amount, source=None):
    return await store.add_topup(user_id, project_id, Decimal(amount), source, created_by_bot=None, tainted=False)


async def _live_total(store, user_id, project_id) -> Decimal:
    """Σ amount of the live top-up rows: what H4 says the total budget equals."""
    return sum((row.amount for row in await store.topups(user_id, project_id) if not row.undone), Decimal("0"))


async def _raw(cfg, sql, params=()):
    async with db_session(cfg) as db:
        return [tuple(row) for row in await (await db.execute(sql, params)).fetchall()]


async def test_the_new_fields_read_back_and_the_monthly_budget_is_ciphertext(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    made = await _create(store, user_id, " Renovation ", currency="usd", budget=Decimal("500"),
                         monthly_budget=Decimal("120.5"), color=PROJECT_COLORS[4], start_date="2026-10-01",
                         due_date="2026-12-31", lead_bot_id=lead.id)
    again = await store.get(user_id, made.id)
    assert again == made
    assert (again.name, again.currency, again.budget, again.monthly_budget) == (
        "Renovation", "USD", Decimal("500.00"), Decimal("120.50"))
    assert (again.color, again.start_date, again.due_date, again.lead_bot_id, again.status) == (
        PROJECT_COLORS[4], "2026-10-01", "2026-12-31", lead.id, "active")
    [(name, budget, monthly, color, start, due, lead_id, status)] = await _raw(
        cfg, "SELECT name, budget, monthly_budget, color, start_date, due_date, lead_bot_id, status "
             "FROM money_projects WHERE id = ?", (made.id,))
    assert all(value.startswith("enc:v2:") for value in (name, budget, monthly))
    assert "120.50" not in monthly
    assert (color, start, due, lead_id, status) == (PROJECT_COLORS[4], "2026-10-01", "2026-12-31", lead.id, "active")


async def test_a_new_project_starts_active_in_the_first_colour_with_no_budget_rows(store, user_id):
    made = await _create(store, user_id)
    assert (made.color, made.status, made.budget, made.monthly_budget, made.currency) == (
        DEFAULT_PROJECT_COLOR, "active", None, None, "EUR")
    assert await store.topups(user_id, made.id) == ()
    food = await store.find_or_create(user_id, "Food", created_by_bot=None, tainted=False)
    assert (food.color, food.status) == (DEFAULT_PROJECT_COLOR, "active")


async def test_a_project_saved_before_v13_reads_with_the_default_colour(cfg, store, user_id):
    made = await _create(store, user_id)
    async with db_session(cfg) as db:
        await db.execute("UPDATE money_projects SET color = NULL WHERE id = ?", (made.id,))
        await db.commit()
    assert (await store.get(user_id, made.id)).color == DEFAULT_PROJECT_COLOR


async def test_find_never_creates_and_ignores_case_and_spacing(store, user_id):
    assert await store.find(user_id, "Renovation") is None
    assert await store.find(user_id, "   ") is None
    assert await store.list(user_id) == ()
    made = await _create(store, user_id)
    assert (await store.find(user_id, "  renovation ")).id == made.id
    assert await store.find(user_id, "Renov") is None
    assert [project.id for project in await store.list(user_id)] == [made.id]


async def test_a_name_in_use_is_refused(store, user_id):
    await _create(store, user_id)
    with pytest.raises(ValueError, match="A project with that name exists."):
        await _create(store, user_id, "RENOVATION")
    assert len(await store.list(user_id)) == 1


@pytest.mark.parametrize(("fields", "message"), [
    ({"name": "  "}, "needs a name"),
    ({"name": "x" * 41}, "needs a name"),
    ({"currency": "euro"}, "three-letter code"),
    ({"color": "#123456"}, "palette"),
    ({"start_date": "next week"}, "YYYY-MM-DD"),
    ({"due_date": "20261231"}, "YYYY-MM-DD"),
    ({"budget": Decimal("0")}, "more than 0"),
    ({"monthly_budget": Decimal("1.234")}, "at most 2 decimals"),
    ({"lead_bot_id": "  "}, "one of your bots"),
])
def test_a_draft_checks_every_field(fields, message):
    with pytest.raises(ValueError, match=message):
        ProjectDraft(**{"name": "Renovation", **fields})


def test_a_patch_takes_only_the_patchable_fields_and_tidies_them():
    with pytest.raises(ValueError, match="Projects have no field budget, created_at."):
        ProjectPatch({"budget": Decimal("5"), "created_at": "now"})
    with pytest.raises(ValueError, match="either active or archived"):
        ProjectPatch({"status": "done"})
    with pytest.raises(ValueError, match="needs a name"):
        ProjectPatch({"name": None})
    patch = ProjectPatch({"name": " Home ", "currency": "usd", "color": PROJECT_COLORS[2].upper(),
                          "due_date": "", "monthly_budget": "80,5", "lead_bot_id": None})
    assert dict(patch.changes) == {"name": "Home", "currency": "USD", "color": PROJECT_COLORS[2], "due_date": None,
                                   "monthly_budget": Decimal("80.50"), "lead_bot_id": None}
    with pytest.raises(TypeError):
        patch.changes["name"] = "Other"


async def test_rename_recomputes_the_name_key_and_a_clash_is_refused(cfg, store, user_id):
    food = await _create(store, user_id, "Food")
    await _create(store, user_id, "Travel")
    [(old_key,)] = await _raw(cfg, "SELECT name_key FROM money_projects WHERE id = ?", (food.id,))
    renamed = await store.update(user_id, food.id, ProjectPatch({"name": "Groceries"}))
    assert renamed.name == "Groceries"
    [(new_key,)] = await _raw(cfg, "SELECT name_key FROM money_projects WHERE id = ?", (food.id,))
    assert new_key != old_key
    assert (await store.find(user_id, "groceries")).id == food.id
    assert await store.find(user_id, "Food") is None
    with pytest.raises(ValueError, match="A project with that name exists."):
        await store.update(user_id, food.id, ProjectPatch({"name": " travel "}))
    assert (await store.get(user_id, food.id)).name == "Groceries"
    assert (await _create(store, user_id, "Food")).id != food.id     # the old name is free again


async def test_archiving_keeps_a_project_findable_and_out_of_the_active_list(store, user_id):
    house = await _create(store, user_id, "House")
    trip = await _create(store, user_id, "Trip")
    archived = await store.update(user_id, house.id, ProjectPatch({"status": "archived"}))
    assert archived.status == "archived"
    assert [project.id for project in await store.list(user_id, include_archived=False)] == [trip.id]
    assert [project.id for project in await store.list(user_id)] == [house.id, trip.id]
    assert (await store.find(user_id, "house")).status == "archived"
    assert (await store.update(user_id, house.id, ProjectPatch({"status": "active"}))).status == "active"
    assert len(await store.list(user_id, include_archived=False)) == 2


async def test_update_sets_and_clears_the_plain_fields_and_the_monthly_limit(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", monthly_budget=Decimal("100"))
    changed = await store.update(user_id, house.id, ProjectPatch({
        "color": PROJECT_COLORS[8], "start_date": "2026-11-01", "due_date": "2027-01-31", "lead_bot_id": lead.id,
        "monthly_budget": Decimal("150"),
    }))
    assert (changed.color, changed.start_date, changed.due_date, changed.lead_bot_id, changed.monthly_budget) == (
        PROJECT_COLORS[8], "2026-11-01", "2027-01-31", lead.id, Decimal("150.00"))
    cleared = await store.update(user_id, house.id, ProjectPatch({
        "start_date": None, "due_date": "", "lead_bot_id": None, "monthly_budget": None,
    }))
    assert (cleared.start_date, cleared.due_date, cleared.lead_bot_id, cleared.monthly_budget) == (
        None, None, None, None)
    assert await _raw(cfg, "SELECT monthly_budget FROM money_projects WHERE id = ?", (house.id,)) == [(None,)]
    assert await store.update(user_id, house.id, ProjectPatch({})) == cleared
    assert await store.update(user_id, "no-such-project", ProjectPatch({"color": PROJECT_COLORS[1]})) is None


async def test_a_lead_bot_that_does_not_exist_is_refused(store, user_id):
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await _create(store, user_id, lead_bot_id="no-such-bot")
    assert await store.find(user_id, "Renovation") is None
    house = await _create(store, user_id, "House")
    with pytest.raises(ValueError, match="The lead bot must be one of your bots."):
        await store.update(user_id, house.id, ProjectPatch({"lead_bot_id": "no-such-bot"}))
    assert (await store.get(user_id, house.id)).lead_bot_id is None


async def test_the_lead_bot_is_cleared_when_the_bot_is_retired(cfg, store, user_id):
    lead = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", lead_bot_id=lead.id)
    assert await BotStore(cfg).delete(user_id, lead.id) is True
    kept = await store.get(user_id, house.id)
    assert (kept.name, kept.lead_bot_id) == ("House", None)


async def test_clearing_the_total_budget_writes_an_edit_row_of_minus_the_budget(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("300"))
    cleared = await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    assert cleared.budget is None and (await store.get(user_id, house.id)).budget is None
    history = await store.topups(user_id, house.id)
    assert [(row.kind, row.amount, row.topup_id) for row in history] == [
        ("edit", Decimal("-300.00"), None), ("edit", Decimal("300.00"), None)]
    assert await _live_total(store, user_id, house.id) == Decimal("0")
    again = await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    assert again.budget is None and len(await store.topups(user_id, house.id)) == 2
    reset = await store.set_budget(user_id, house.id, Decimal("80"), created_by_bot=None, tainted=False)
    assert reset.budget == Decimal("80.00") == await _live_total(store, user_id, house.id)
    same = await store.set_budget(user_id, house.id, Decimal("80.00"), created_by_bot=None, tainted=False)
    assert same.budget == Decimal("80.00") and len(await store.topups(user_id, house.id)) == 3   # no +0.00 row


async def test_a_top_up_is_a_credit_row_that_raises_the_budget(cfg, store, user_id):
    bot = await make_bot(cfg, user_id, "Fixer")
    house = await _create(store, user_id, "House", budget=Decimal("200"))
    topup = await store.add_topup(user_id, house.id, Decimal("50"), "birthday", created_by_bot=bot.id, tainted=True)
    assert (topup.kind, topup.amount, topup.currency, topup.source, topup.topup_id, topup.undone) == (
        "credit", Decimal("50.00"), "EUR", "birthday", None, False)
    assert (topup.project_id, topup.created_by_bot, topup.tainted) == (house.id, bot.id, True)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("250.00") == await _live_total(store, user_id, house.id)
    [(amount, source)] = await _raw(cfg, "SELECT amount, source FROM money_topups WHERE id = ?", (topup.id,))
    assert amount.startswith("enc:v2:") and source.startswith("enc:v2:") and "birthday" not in source
    assert (await store.topups(user_id, house.id))[0] == topup


async def test_editing_a_top_up_writes_the_difference_and_keeps_the_invariant(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "40", "bonus")
    up = await store.edit_topup(user_id, credit.id, Decimal("55"))
    assert (up.kind, up.amount, up.topup_id, up.source) == ("edit", Decimal("15.00"), credit.id, None)
    down = await store.edit_topup(user_id, credit.id, Decimal("30"))
    assert (down.kind, down.amount, down.topup_id) == ("edit", Decimal("-25.00"), credit.id)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("130.00") == await _live_total(store, user_id, house.id)
    same = await store.edit_topup(user_id, credit.id, Decimal("30"))
    assert same == credit and len(await store.topups(user_id, house.id)) == 4
    assert await store.edit_topup(user_id, "no-such-top-up", Decimal("5")) is None
    assert await store.edit_topup(user_id, up.id, Decimal("5")) is None      # only a credit can be changed


async def test_undoing_an_edited_top_up_removes_it_and_its_edits(store, user_id):
    house = await _create(store, user_id, "House")
    await store.set_budget(user_id, house.id, Decimal("300"), created_by_bot=None, tainted=False)
    kept = await _topup(store, user_id, house.id, "20", "gift")
    credit = await _topup(store, user_id, house.id, "50", "bonus")
    await store.edit_topup(user_id, credit.id, Decimal("80"))
    await store.edit_topup(user_id, credit.id, Decimal("70"))
    assert (await store.get(user_id, house.id)).budget == Decimal("390.00")

    undone = await store.undo_topup(user_id, credit.id)

    assert (undone.id, undone.kind, undone.amount, undone.undone) == (credit.id, "credit", Decimal("50.00"), True)
    budget = (await store.get(user_id, house.id)).budget
    assert budget == Decimal("320.00") == await _live_total(store, user_id, house.id)
    history = await store.topups(user_id, house.id)
    edits = {row.id for row in history if row.topup_id == credit.id}
    assert len(edits) == 2
    assert {row.id for row in history if row.undone} == {credit.id} | edits
    assert [row.id for row in history if row.kind == "credit" and not row.undone] == [kept.id]
    with pytest.raises(TopUpUndone, match="undone already"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(TopUpUndone, match="undone already"):
        await store.edit_topup(user_id, credit.id, Decimal("10"))
    assert (await store.get(user_id, house.id)).budget == Decimal("320.00")


async def test_a_top_up_cannot_change_while_the_budget_is_cleared_or_take_it_below_zero(store, user_id):
    house = await _create(store, user_id, "House")
    credit = await _topup(store, user_id, house.id, "50")
    await store.set_budget(user_id, house.id, Decimal("10"), created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match="below 0"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(ValueError, match="below 0"):
        await store.edit_topup(user_id, credit.id, Decimal("1"))
    await store.set_budget(user_id, house.id, None, created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match="already taken back"):
        await store.undo_topup(user_id, credit.id)
    with pytest.raises(ValueError, match="already taken back"):
        await store.edit_topup(user_id, credit.id, Decimal("60"))
    assert (await store.get(user_id, house.id)).budget is None
    assert await _live_total(store, user_id, house.id) == Decimal("0")
    assert not any(row.undone for row in await store.topups(user_id, house.id))


async def test_has_money_counts_expenses_and_top_ups_but_not_a_budget_alone(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    assert await store.has_money(user_id, house.id) is False
    credit = await _topup(store, user_id, house.id, "5")
    assert await store.has_money(user_id, house.id) is True
    await store.undo_topup(user_id, credit.id)
    assert await store.has_money(user_id, house.id) is False
    expenses = ExpenseStore(cfg)
    expense = await expenses.add(user_id, ExpenseDraft(house.id, Decimal("3"), spent_at="2026-10-13"),
                                 created_by_bot=None, tainted=False)
    assert await store.has_money(user_id, house.id) is True
    await expenses.delete(user_id, expense.id)
    assert await store.has_money(user_id, house.id) is False


async def test_the_currency_changes_only_while_the_project_has_no_money_and_the_budget_rows_follow(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    moved = await store.update(user_id, house.id, ProjectPatch({"currency": "USD"}))
    assert (moved.currency, moved.budget) == ("USD", Decimal("100.00"))
    assert [row.currency for row in await store.topups(user_id, house.id)] == ["USD"]
    await _topup(store, user_id, house.id, "5")
    with pytest.raises(ValueError, match="no expenses and no top-ups"):
        await store.update(user_id, house.id, ProjectPatch({"currency": "GBP"}))
    kept = await store.update(user_id, house.id, ProjectPatch({"currency": "USD", "color": PROJECT_COLORS[3]}))
    assert (kept.currency, kept.color) == ("USD", PROJECT_COLORS[3])


async def test_deleting_a_project_moves_its_expenses_to_general_and_unlinks_its_items(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "10")
    expenses = ExpenseStore(cfg)
    lunch = await expenses.add(user_id, ExpenseDraft(house.id, Decimal("12.50"), spent_at="2026-10-13"),
                               created_by_bot=None, tainted=False)
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Buy tiles"), created_by_bot=None, tainted=False)
    note = await NoteStore(cfg).create(user_id, NoteDraft(title="Ideas", content="green tiles"),
                                       created_by_bot=None, tainted=False)
    body = json.dumps(doc_from_markdown("Plan", "- tiles"))
    document = await DocumentStore(cfg).create(user_id, DocumentDraft("doc", "Plan", body),
                                               created_by_bot=None, tainted=False)
    linked = (("tasks", task.id), ("notes", note.id), ("documents", document.id))
    async with db_session(cfg) as db:
        for table, row_id in linked:
            await db.execute(f"UPDATE {table} SET project_id = ? WHERE id = ?", (house.id, row_id))
        await db.commit()
    assert await store.find(user_id, GENERAL_PROJECT_NAME) is None

    assert await store.delete(user_id, house.id) is True

    general = await store.find(user_id, GENERAL_PROJECT_NAME)
    assert general is not None and is_general(general)
    assert (await expenses.get(user_id, lunch.id)).project_id == general.id
    for table, row_id in linked:
        assert await _raw(cfg, f"SELECT project_id, deleted_at FROM {table} WHERE id = ?", (row_id,)) == [
            (None, None)], table
    assert (await NoteStore(cfg).get(user_id, note.id)).revision == note.revision
    assert (await DocumentStore(cfg).get_meta(user_id, document.id)).revision == document.revision
    assert await store.get(user_id, house.id) is None
    assert await store.find(user_id, "House") is None
    assert [project.id for project in await store.list(user_id)] == [general.id]
    assert await store.undo_topup(user_id, credit.id) is None
    assert await store.delete(user_id, house.id) is False


async def test_deleting_uses_the_general_that_exists_and_frees_the_name(cfg, store, user_id):
    general = await store.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    trip = await _create(store, user_id, "Trip")
    expense = await ExpenseStore(cfg).add(user_id, ExpenseDraft(trip.id, Decimal("9"), spent_at="2026-10-13"),
                                          created_by_bot=None, tainted=False)
    assert await store.delete(user_id, trip.id) is True
    assert (await ExpenseStore(cfg).get(user_id, expense.id)).project_id == general.id
    assert [project.id for project in await store.list(user_id)] == [general.id]
    assert (await _create(store, user_id, "trip")).id != trip.id


async def test_general_can_be_neither_deleted_nor_renamed_nor_archived(store, user_id):
    general = await store.find_or_create(user_id, GENERAL_PROJECT_NAME, created_by_bot=None, tainted=False)
    assert is_general(general) and not is_general(await _create(store, user_id, "House"))
    for changes in ({"name": "Misc"}, {"status": "archived"}):
        with pytest.raises(ValueError, match="General is where expenses with no project go"):
            await store.update(user_id, general.id, ProjectPatch(changes))
    with pytest.raises(ValueError, match="General is where expenses with no project go"):
        await store.delete(user_id, general.id)
    kept = await store.find(user_id, GENERAL_PROJECT_NAME)
    assert (kept.id, kept.name, kept.status) == (general.id, GENERAL_PROJECT_NAME, "active")


async def test_another_users_project_and_top_ups_are_none(cfg, store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "10")
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    assert await store.get(bob, house.id) is None
    assert await store.find(bob, "House") is None
    assert await store.list(bob) == ()
    assert await store.update(bob, house.id, ProjectPatch({"name": "Mine"})) is None
    assert await store.set_budget(bob, house.id, Decimal("1"), created_by_bot=None, tainted=False) is None
    with pytest.raises(ValueError, match="No such project."):
        await _topup(store, bob, house.id, "5")
    assert await store.edit_topup(bob, credit.id, Decimal("99")) is None
    assert await store.undo_topup(bob, credit.id) is None
    assert await store.topups(bob, house.id) == ()
    assert await store.has_money(bob, house.id) is False
    assert await store.delete(bob, house.id) is False
    kept = await store.get(user_id, house.id)
    assert (kept.name, kept.budget) == ("House", Decimal("110.00"))


async def _budget(store, user_id, project_id, amount):
    return await store.set_budget(user_id, project_id, amount, created_by_bot=None, tainted=False)


@pytest.mark.parametrize("amount, message", [
    (Decimal("0.005"), "at most 2 decimals"), (Decimal("12.345"), "at most 2 decimals"),
    (Decimal("-5"), "more than 0"), (Decimal("0"), "more than 0"),
])
async def test_the_store_reads_every_amount_again_so_the_ledger_cannot_break(store, user_id, amount, message):
    """Task 2 review: a caller that skips the service can no longer write a row that
    breaks ``budget == Σ live rows`` (more than 2 decimals, or not above 0)."""
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    credit = await _topup(store, user_id, house.id, "20")
    history = await store.topups(user_id, house.id)
    with pytest.raises(ValueError, match=message):
        await _budget(store, user_id, house.id, amount)
    with pytest.raises(ValueError, match=message):
        await store.add_topup(user_id, house.id, amount, None, created_by_bot=None, tainted=False)
    with pytest.raises(ValueError, match=message):
        await store.edit_topup(user_id, credit.id, amount)
    assert await store.topups(user_id, house.id) == history
    assert (await store.get(user_id, house.id)).budget == Decimal("120.00") == await _live_total(
        store, user_id, house.id)


async def test_a_top_up_from_before_the_budget_was_cleared_can_be_neither_edited_nor_undone(store, user_id):
    """H5: the clearing row already took the 50 back. Setting a new total later
    does not bring it back, so undoing or editing it would take money off the new total."""
    house = await _create(store, user_id, "House")
    await _budget(store, user_id, house.id, Decimal("300"))
    credit = await _topup(store, user_id, house.id, "50")
    await _budget(store, user_id, house.id, None)
    await _budget(store, user_id, house.id, Decimal("200"))
    history = await store.topups(user_id, house.id)

    attempts = (lambda: store.undo_topup(user_id, credit.id),
                lambda: store.edit_topup(user_id, credit.id, Decimal("80")))
    for attempt in attempts:
        with pytest.raises(ValueError, match="already taken back when the budget was cleared") as refused:
            await attempt()
        assert not isinstance(refused.value, TopUpUndone)      # a broken rule (422), not a conflict (409)

    assert await store.topups(user_id, house.id) == history
    assert (await store.get(user_id, house.id)).budget == Decimal("200.00")


async def test_a_top_up_made_after_the_budget_was_cleared_can_still_be_edited_and_undone(store, user_id):
    house = await _create(store, user_id, "House", budget=Decimal("300"))
    await _budget(store, user_id, house.id, None)
    credit = await _topup(store, user_id, house.id, "40")
    assert (await store.get(user_id, house.id)).budget == Decimal("40.00")
    await store.edit_topup(user_id, credit.id, Decimal("60"))
    assert (await store.get(user_id, house.id)).budget == Decimal("60.00")
    assert (await store.undo_topup(user_id, credit.id)).undone is True
    assert (await store.get(user_id, house.id)).budget == Decimal("0.00")


async def test_setting_the_budget_lower_is_not_a_clearing_even_when_a_later_undo_empties_it(store, user_id):
    """Only clearing takes top-ups back. Here the total falls to 0 after an undo, but the row before
    it was a lower total (50), not a clearing, so the other top-up still counts."""
    house = await _create(store, user_id, "House", budget=Decimal("100"))
    first = await _topup(store, user_id, house.id, "50")
    second = await _topup(store, user_id, house.id, "30")
    await _budget(store, user_id, house.id, Decimal("50"))          # 180 -> 50
    await store.undo_topup(user_id, first.id)                       # 50 -> 0
    assert (await store.get(user_id, house.id)).budget == Decimal("0.00")

    await store.edit_topup(user_id, second.id, Decimal("40"))

    assert (await store.get(user_id, house.id)).budget == Decimal("10.00") == await _live_total(
        store, user_id, house.id)


def test_a_cleared_budget_is_still_refused_by_the_backstop_in_moved_budget():
    """``taken_back`` refuses every top-up that outlived a clearing first; this is the guard behind it."""
    with pytest.raises(ValueError, match="budget is cleared"):
        moved_budget(None, Decimal("1"))
    assert moved_budget(Decimal("10"), Decimal("-4")) == Decimal("6")
    with pytest.raises(ValueError, match="below 0"):
        moved_budget(Decimal("3"), Decimal("-4"))


async def test_keep_clears_the_mark_of_a_web_made_project_and_of_the_budget_it_was_made_with(store, user_id):
    """Keep (the user vouching, HTTP only) clears the project's taint bit and that of the "Budget set" row
    written when it was made, so the project page is no longer web content. Another user's Keep does nothing."""
    web = await store.create(user_id, ProjectDraft(name="Trip", budget=Decimal("2000")), created_by_bot=None,
                             tainted=True)
    plain = await _create(store, user_id, "Garden")
    assert [row.tainted for row in await store.topups(user_id, web.id)] == [True]

    assert await store.keep("someone-else", web.id) is None
    assert (await store.get(user_id, web.id)).tainted is True

    kept = await store.keep(user_id, web.id)

    assert (kept.id, kept.tainted, kept.budget) == (web.id, False, Decimal("2000.00"))
    assert [row.tainted for row in await store.topups(user_id, web.id)] == [False]
    assert (await store.get(user_id, plain.id)).tainted is False
    assert await store.keep(user_id, "no-such-project") is None


async def test_the_history_marks_the_credits_a_clearing_took_back(store, user_id):
    """``taken_back`` is what ``edit_topup`` and ``undo_topup`` refuse by, so every credit marked in the
    history is refused, and every other live one is not."""
    house = await _create(store, user_id, "House", budget=Decimal("300"))
    old = await _topup(store, user_id, house.id, "50")
    await _budget(store, user_id, house.id, None)
    await _budget(store, user_id, house.id, Decimal("200"))
    fresh = await _topup(store, user_id, house.id, "20")
    lowered = await _topup(store, user_id, house.id, "10")
    await _budget(store, user_id, house.id, Decimal("100"))      # lower, not a clearing

    history = {row.id: row for row in await store.topups(user_id, house.id)}

    assert [row.id for row in history.values() if row.taken_back] == [old.id]
    with pytest.raises(ValueError, match="already taken back"):
        await store.edit_topup(user_id, old.id, Decimal("60"))
    for credit in (fresh, lowered):
        assert history[credit.id].taken_back is False
        assert (await store.edit_topup(user_id, credit.id, Decimal("5"))) is not None
