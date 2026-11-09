"""Copying a tool result back into a record (M2 final fix). Every result
escapes record text (html.escape, quote=True — the rule against tag
smuggling), so a model that copies "Ana&#x27;s" from list_tasks into
create_doc must still store "Ana's". The write tools reverse exactly that
escape, once, so the text a record holds is the text the user wrote."""

from __future__ import annotations

import html
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.documents.doc_markdown import doc_to_markdown
from roost.documents.render import snapshot_of
from roost.documents.service import DocumentService
from roost.documents.sheet_snapshot import as_grid
from roost.documents.store import DocumentStore
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.expense_store import ExpenseStore
from roost.money.project_store import ProjectStore
from roost.money.service import ExpenseEntry, MoneyService
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.records.tool_text import plain
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

TRICKY = ("Call Ana's mum & co", 'say "hi" <3', "AT&amp;T in HTML", "a &lt;b&gt; tag", "Tasks&notes &copy R&D")


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


async def _talk(cfg, user_id, bot, steps: list, text: str):
    rig = make_rig(cfg, team_model({bot.name: [*steps, say("ok")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return [turn.text for turn in rig.model.requests[-1].turns if turn.role == "tool"]


def _seen(text: str) -> str:
    """The text exactly as a tool result shows it to the model."""
    return html.escape(text, quote=True)


async def _documents(cfg, user_id):
    store = DocumentStore(cfg)
    return {meta.title: await store.get(user_id, meta.id) for meta in await store.list(user_id)}


@pytest.mark.parametrize("text", TRICKY)
def test_plain_reverses_the_result_escape_exactly(text):
    assert plain(_seen(text)) == text


def test_plain_leaves_text_that_only_looks_like_an_entity():
    assert plain("Tasks&notes &copy R&D &#60; &apos;") == "Tasks&notes &copy R&D &#60; &apos;"
    assert plain("Ana's & co") == "Ana's & co"


async def test_save_all_my_tasks_in_a_document_keeps_apostrophes_exact(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await TaskStore(cfg).create(user_id, TaskDraft(title="Ana's & co"), created_by_bot=None, tainted=False)
    listing, created = await _talk(cfg, user_id, bot, [
        _tool("l", "list_tasks", status="all"),
        _tool("d", "create_doc", title=_seen("Ana's tasks"), markdown=_seen("- Ana's & co")),
    ], "save all my tasks in a document")
    assert _seen("Ana's & co") in listing and created.startswith("Created doc")
    [(title, document)] = (await _documents(cfg, user_id)).items()
    assert title == "Ana's tasks"
    assert doc_to_markdown(snapshot_of(document)) == "- Ana's & co"


async def test_a_sheet_of_expenses_keeps_joes_exact(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    money = MoneyService(ProjectStore(cfg), ExpenseStore(cfg), EventHub(cfg))
    await money.log_expense(user_id, ExpenseEntry(amount=Decimal("30"), spent_at="2026-10-03", project="food",
                                                  note="Dinner at Joe's"))
    await DocumentService(DocumentStore(cfg), EventHub(cfg)).create_sheet(user_id, "Notes", [["x"]])
    listing, created, updated = await _talk(cfg, user_id, bot, [
        _tool("l", "list_expenses", month="2026-10"),
        _tool("s", "create_sheet", title="October", rows=[["Note"], [_seen("Dinner at Joe's")]]),
        _tool("c", "update_sheet_cells", document="Notes",
              cells=[{"cell": "A2", "value": _seen('"quoted" & <b>')}, {"cell": "B1", "formula": "=A1&\"!\""}]),
    ], "make a sheet of my October expenses")
    assert _seen("Dinner at Joe's") in listing and created.startswith("Created sheet") and "Updated" in updated
    by_title = await _documents(cfg, user_id)
    assert as_grid(snapshot_of(by_title["October"]))[1] == ["Dinner at Joe's"]
    assert as_grid(snapshot_of(by_title["Notes"]))[:2] == [["x", '=A1&"!"'], ['"quoted" & <b>', ""]]


async def test_a_note_rewritten_after_read_note_keeps_its_characters(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    content = "Ana's party & cake <3\nAT&amp;T in HTML\nTasks&notes"
    await NoteStore(cfg).create(user_id, NoteDraft(title="Ana's birthday", content=content), created_by_bot=None,
                                tainted=False)
    read, updated, appended = await _talk(cfg, user_id, bot, [
        _tool("r", "read_note", note=_seen("Ana's birthday")),
        _tool("u", "update_note", note=_seen("Ana's birthday"), title=_seen("Ana's 40th"),
              content=_seen(content + "\nbring \"wine\""), tags=[_seen("#Mums")]),
        _tool("a", "append_to_note", note=_seen("Ana's 40th"), text=_seen("Joe's cake")),
    ], "add wine to Ana's birthday note")
    assert _seen(content) in read and updated.startswith("Updated") and appended.startswith("Added to")
    [note] = await NoteStore(cfg).list(user_id)
    assert note.title == "Ana's 40th" and note.tags == ("mums",)   # a tag is one word (obsidian track)
    assert note.content == content + "\nbring \"wine\"\n\nJoe's cake"


async def test_add_note_stores_plain_text(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, [
        _tool("n", "add_note", title=_seen("Joe's list"), content=_seen("eggs & ham"), tags=[_seen("#Joes")]),
    ], "note eggs and ham on Joe's list")
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.title, note.content, note.tags) == ("Joe's list", "eggs & ham", ("bot:writer", "joes"))   # folded, after the bot tag


async def test_a_task_and_an_expense_copied_from_a_note_keep_their_characters(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Office")
    await _talk(cfg, user_id, bot, [
        _tool("t", "add_task", title=_seen("Call Ana's mum"), category=_seen("Mum & Dad"), steps=[_seen("Joe's")]),
        _tool("e", "log_expense", amount=12, project="food", note=_seen("Dinner at Joe's"), spent_at="2026-10-03"),
    ], "add a task and log the dinner")
    [task] = await TaskStore(cfg).list(user_id, status="all")
    assert (task.title, task.category) == ("Call Ana's mum", "Mum & Dad")
    [expense] = await ExpenseStore(cfg).list_month(user_id, "2026-10")
    assert expense.description == "Dinner at Joe's"
