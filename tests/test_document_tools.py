"""The docs role end to end (M2 D2, D3): a bot's tools over the user's shared
documents, alone and together with its other roles."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.documents import pdf_ops
from roost.documents.doc_markdown import doc_to_markdown
from roost.documents.models import Document
from roost.documents.render import pdf_bytes_of, snapshot_of
from roost.documents.service import DocumentService
from roost.documents.sheet_snapshot import as_grid
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.talk.gate import TAINTED_CHANGE_TEXT
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import ask, make_bot, make_rig, say, send, team_model, wait_idle


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
    return rig, thread


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


def _service(cfg) -> DocumentService:
    return DocumentService(DocumentStore(cfg), EventHub(cfg))


async def _documents(cfg, user_id) -> list[Document]:
    store = DocumentStore(cfg)
    return [await store.get(user_id, meta.id) for meta in await store.list(user_id)]


async def test_save_all_my_tasks_in_a_document(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    for title in ("Call the dentist", "Buy orchids for Ana"):
        await TaskStore(cfg).create(user_id, TaskDraft(title=title), created_by_bot=None, tainted=False)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l", "list_tasks", status="all"),
        _tool("d", "create_doc", title="My tasks", markdown="# My tasks\n\n- Call the dentist\n- Buy orchids for Ana"),
        say("Saved your tasks in “My tasks”."),
    ]}, "save all my tasks in a document")
    listing, created = _tool_texts(rig.model.requests[-1])
    assert "Call the dentist" in listing and "Buy orchids for Ana" in listing
    assert created.startswith("Created doc")
    [document] = await _documents(cfg, user_id)
    assert (document.meta.kind, document.meta.title, document.meta.created_by_bot, document.meta.tainted) == (
        "doc", "My tasks", bot.id, False)
    assert "- Buy orchids for Ana" in doc_to_markdown(snapshot_of(document))


async def test_a_sheet_of_my_october_expenses(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("e", "log_expense", amount=12.5, project="food", note="lunch", spent_at="2026-10-03"),
        _tool("l", "list_expenses", month="2026-10"),
        _tool("s", "create_sheet", title="October expenses",
              rows=[["Date", "Category", "Amount", "Note"], ["2026-10-03", "food", "12.50", "lunch"]]),
        say("Made the sheet “October expenses”."),
    ]}, "log lunch 12.50 on 3 October, then make a sheet of my October expenses")
    assert "12.50 EUR" in _tool_texts(rig.model.requests[-1])[1]
    [sheet] = await _documents(cfg, user_id)
    assert (sheet.meta.kind, sheet.meta.title) == ("sheet", "October expenses")
    assert as_grid(snapshot_of(sheet))[1] == ["2026-10-03", "food", 12.5, "lunch"]


async def test_create_sheet_keeps_ambiguous_text_as_text(cfg, user_id):
    """Fix round 1, finding 1: create_sheet's cell coercion (sheet_snapshot's
    coerce_value, called via sheet_from_rows) must not turn a birthdays
    sheet's "Nan" nickname, a leading-zero postcode or a leading-'+' phone
    number into a number — this is the create_sheet TOOL path (tools.py)."""
    bot = await make_bot(cfg, user_id, "Office")
    await _talk(cfg, user_id, bot, {"Office": [
        _tool("s", "create_sheet", title="Birthdays",
              rows=[["Name", "Nickname", "Postcode", "Phone"], ["Ana", "Nan", "08001", "+34600123456"]]),
        say("ok"),
    ]}, "make a birthdays sheet")
    [sheet] = await _documents(cfg, user_id)
    assert as_grid(snapshot_of(sheet))[1] == ["Ana", "Nan", "08001", "+34600123456"]


async def test_all_sixty_tasks_reach_the_document(cfg, user_id):
    """More than one listing's worth (TASK_LIST_LIMIT is 50): the first listing
    says how to get the rest, and the second holds the other ten."""
    bot = await make_bot(cfg, user_id, "Office")
    titles = [f"Task {n:02d}" for n in range(1, 61)]
    for title in titles:
        await TaskStore(cfg).create(user_id, TaskDraft(title=title), created_by_bot=None, tainted=False)
    markdown = "# My tasks\n\n" + "\n".join(f"- {title}" for title in titles)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l1", "list_tasks", status="all"),
        _tool("l2", "list_tasks", status="all", offset=50),
        _tool("d", "create_doc", title="My tasks", markdown=markdown),
        say("Saved all 60 tasks in “My tasks”."),
    ]}, "save all my tasks in a document")
    first, second, created = _tool_texts(rig.model.requests[-1])
    assert first.endswith("…and 10 more: call again with offset=50.")
    assert len(second.splitlines()) == 10 and "more" not in second
    assert all(title in first + second for title in titles)
    assert created.startswith("Created doc")
    [document] = await _documents(cfg, user_id)
    assert "- Task 60" in doc_to_markdown(snapshot_of(document))


async def test_a_long_month_of_expenses_says_how_many_more(cfg, user_id):
    """M1's list_expenses cut at 50 and said nothing; now it says how to get the rest."""
    bot = await make_bot(cfg, user_id, "Office")
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    for n in range(60):
        await money.log_expense(user_id, ExpenseEntry(amount=Decimal("1.50"), spent_at=f"2026-10-{n % 28 + 1:02d}",
                                                      project="food", note=f"snack {n:02d}"))
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("l1", "list_expenses", month="2026-10"),
        _tool("l2", "list_expenses", month="2026-10", offset=50),
        say("ok"),
    ]}, "make a sheet of my October expenses")
    first, second = _tool_texts(rig.model.requests[-1])
    assert first.endswith("…and 10 more: call again with offset=50.")
    assert len(second.splitlines()) == 10 and "more" not in second
    assert all(f"snack {n:02d}" in first + second for n in range(60))


async def test_a_hand_over_longer_than_the_old_chat_cap_is_not_refused(cfg, user_id):
    """Fix round 1, finding 2: ask_bot's task used to share MAX_MESSAGE_TEXT_
    LENGTH (8000) with a human-typed chat message. Once "the full content" a
    bot gathers (hundreds of tasks, status all) passes that, the old cap
    refused the handoff with BAD_ASK_ARGS and the doc was never made. It now
    has its own larger cap (MAX_HANDOFF_TASK_LENGTH).

    Round 2 of this fix round: under S1 D2 every bot holds every tool, so
    the handoff is no longer role-routed ("docs") — it names the teammate
    directly ("Writer") — but ask_bot's own task-length cap is unchanged and
    still needs its own coverage."""
    life_admin = await make_bot(cfg, user_id, "Life admin")
    writer = await make_bot(cfg, user_id, "Writer")
    markdown = "# My tasks\n\n" + "\n".join(f"- Task {n:03d}" for n in range(900))
    assert len(markdown) > 8000
    await _talk(cfg, user_id, life_admin, {
        "Life admin": [
            _tool("l", "list_tasks", status="all"),
            [ask("h", "Writer", f"Save this as a doc titled My tasks:\n{markdown}"), TurnDone("tool_use")],
            say("Writer saved your tasks."),
        ],
        "Writer": [_tool("d", "create_doc", title="My tasks", markdown=markdown), say("Saved.")],
    }, "save all my tasks in a document")
    # A refusal (BAD_ASK_ARGS, the pre-fix behavior) means Writer's create_doc
    # step is never reached at all, so this would unpack an empty list.
    [document] = await _documents(cfg, user_id)
    assert (document.meta.title, document.meta.created_by_bot) == ("My tasks", writer.id)
    assert "- Task 899" in doc_to_markdown(snapshot_of(document))


async def test_a_doc_made_from_tainted_tasks_is_tainted(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Buy the gadget"), created_by_bot=None, tainted=True)
    await _talk(cfg, user_id, bot, {"Office": [
        _tool("l", "list_tasks"), _tool("d", "create_doc", title="My tasks", markdown="- Buy the gadget"), say("ok"),
    ]}, "save my tasks in a doc")
    [document] = await _documents(cfg, user_id)
    assert document.meta.tainted is True


async def test_an_uploaded_pdf_taints_the_run_that_reads_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    data = pdf_ops.generate_from_text("The deposit is two months' rent.", title="Lease")
    await _service(cfg).create_pdf(user_id, "Lease", data, tainted=True)
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("r", "read_document", document="Lease"), _tool("d", "delete_document", document="Lease"), say("No."),
    ]}, "what does the lease say about the deposit? then delete it")
    read, refused = _tool_texts(rig.model.requests[-1])
    assert "two months" in read and "[from web content]" in read
    assert refused == TAINTED_CHANGE_TEXT
    assert len(await DocumentStore(cfg).list(user_id)) == 1


async def test_read_document_shows_a_sheet_as_a_small_table_and_escapes_markup(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_sheet(user_id, "Trip plan", [["<b>Item</b>", "Cost"], ["Hotel", 240]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("r", "read_document", document="trip plan"), say("ok")]},
                         "read the trip plan")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "&lt;b&gt;Item&lt;/b&gt;" in text and "<b>" not in text and "240" in text and "A | B" in text


async def test_append_to_doc_and_update_sheet_cells(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_doc(user_id, "Packing", "- passport")
    await _service(cfg).create_sheet(user_id, "Trip", [["Item", "Cost"], ["Hotel", 240]])
    await _talk(cfg, user_id, bot, {"Office": [
        _tool("a", "append_to_doc", document="Packing", markdown="- keys"),
        _tool("c", "update_sheet_cells", document="Trip",
              cells=[{"cell": "A3", "value": "Train"}, {"cell": "b3", "value": 35}, {"cell": "B4", "formula": "=SUM(B2:B3)"}]),
        say("ok"),
    ]}, "add keys to packing and the train to the trip")
    by_title = {document.meta.title: document for document in await _documents(cfg, user_id)}
    assert doc_to_markdown(snapshot_of(by_title["Packing"])).splitlines() == ["- passport", "- keys"]
    assert by_title["Packing"].meta.revision == 2
    assert as_grid(snapshot_of(by_title["Trip"]))[2:] == [["Train", 35], ["", "=SUM(B2:B3)"]]


async def test_a_doc_tool_on_a_sheet_is_refused_plainly(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_sheet(user_id, "Trip", [["Item"]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("a", "append_to_doc", document="Trip", markdown="x"),
                                                        say("ok")]}, "add x to trip")
    assert _tool_texts(rig.model.requests[-1])[0] == "Refused: “Trip” is a sheet, not a doc."


async def test_update_sheet_cells_refuses_a_cell_past_the_corner(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_sheet(user_id, "Trip", [["Item"]])
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("c", "update_sheet_cells", document="Trip", cells=[{"cell": "ZZZ9999999", "value": 1}]), say("No."),
    ]}, "put 1 in ZZZ9999999 of the trip sheet")
    assert "from A1 to ZZ100000" in _tool_texts(rig.model.requests[-1])[0]
    [sheet] = await _documents(cfg, user_id)
    assert sheet.meta.revision == 1


async def test_create_sheet_refuses_too_many_rows(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("s", "create_sheet", title="Big", rows=[["x"]] * 501),
                                                        say("No.")]}, "make a big sheet")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Refused: create_sheet needs rows (1 to 500")
    assert await DocumentStore(cfg).list(user_id) == ()


async def test_make_pdf_from_doc_creates_a_pdf_that_reads_back(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_doc(user_id, "Letter", "# Dear Ana\n\nHappy birthday!")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("p", "make_pdf_from_doc", document="Letter"), say("ok")]},
                         "make a PDF of the letter")
    assert _tool_texts(rig.model.requests[-1])[0].startswith("Created PDF")
    pdf = next(document for document in await _documents(cfg, user_id) if document.meta.kind == "pdf")
    assert (pdf.meta.title, pdf.meta.pages, pdf.meta.created_by_bot) == ("Letter", 1, bot.id)
    assert "Happy birthday" in pdf_ops.extract_text(pdf_bytes_of(pdf))


async def test_a_near_miss_document_name_never_changes_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _service(cfg).create_doc(user_id, "Packing list", "- passport")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [_tool("d", "delete_document", document="Packing lust"),
                                                        say("Which?")]}, "delete packing lust")
    assert "Did you mean" in _tool_texts(rig.model.requests[-1])[0]
    assert len(await DocumentStore(cfg).list(user_id)) == 1


async def test_two_bots_with_the_docs_role_share_the_users_documents(cfg, user_id):
    writer = await make_bot(cfg, user_id, "Writer")
    office = await make_bot(cfg, user_id, "Office")
    await _talk(cfg, user_id, writer, {"Writer": [_tool("d", "create_doc", title="Ideas", markdown="- garden"),
                                                  say("ok")]}, "start an ideas doc")
    rig, _ = await _talk(cfg, user_id, office, {"Office": [_tool("l", "list_documents"), say("ok")]}, "what docs do I have?")
    assert "“Ideas”" in _tool_texts(rig.model.requests[-1])[0]




async def test_documents_are_made_in_a_project_listed_by_it_and_a_pdf_follows_its_doc(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    await _service(cfg).create_doc(user_id, "Loose", "- x")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("d", "create_doc", title="Plan", markdown="- tiles", project="renovation"),
        _tool("s", "create_sheet", title="Costs", rows=[["Item", "Cost"], ["Tiles", 240]], project="Renovation"),
        _tool("l", "list_documents", project="Renovation"),
        _tool("p", "make_pdf_from_doc", document="Plan"),
        say("ok"),
    ]}, "start the renovation plan and its costs sheet, then a PDF of the plan")
    doc, sheet, listed, pdf = _tool_texts(rig.model.requests[-1])
    assert doc.startswith("Created doc: [doc] “Plan”") and doc.endswith(" Project: “Renovation”.")
    assert sheet.startswith("Created sheet: [sheet] “Costs”") and sheet.endswith(" Project: “Renovation”.")
    assert "“Plan”" in listed and "“Costs”" in listed and "“Loose”" not in listed
    assert pdf.startswith("Created PDF: [PDF] “Plan”")
    linked = {(meta.kind, meta.title): meta.project_id for meta in await DocumentStore(cfg).list(user_id)}
    assert linked == {("doc", "Plan"): project.id, ("sheet", "Costs"): project.id, ("pdf", "Plan"): project.id,
                      ("doc", "Loose"): None}


async def test_set_document_project_moves_a_document_and_keeps_its_revision(cfg, user_id):
    """H12: set_document_project links and unlinks without a new revision, so an
    open Univer editor still saves; a near miss never moves anything."""
    bot = await make_bot(cfg, user_id, "Office")
    await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None, tainted=False)
    plan = await _service(cfg).create_doc(user_id, "Plan", "- tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Office": [
        _tool("m", "set_document_project", document="plan", project="Renovation"),
        _tool("u", "set_document_project", document="Plan", project=""),
        _tool("n", "set_document_project", document="Plan", project="Renovaton"),
        say("ok"),
    ]}, "file the plan under the renovation")
    moved, unlinked, near = _tool_texts(rig.model.requests[-1])
    assert moved == "Moved “Plan” to the project “Renovation”."
    assert unlinked == "“Plan” is in no project now."
    assert near == "Refused: No project is called “Renovaton”. Did you mean “Renovation”? Say it exactly."
    kept = await DocumentStore(cfg).get_meta(user_id, plan.id)
    assert (kept.project_id, kept.revision) == (None, 1)
