"""The Bot Journal through a bot's run: journal_append / journal_read, the run's own line, find_notes."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.journal.runs import JournalRuns
from roost.journal.service import JournalService
from roost.journal.store import JournalStore
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome
from roost.talk.tool_catalog import CATALOG
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


async def _days(cfg, user_id, bot_id):
    return await JournalStore(cfg).recent(user_id, bot_id, 10)


def _entries(day) -> list[str]:
    return [line[8:] for line in day.content.splitlines() if line.startswith("- ")]


def test_the_journal_tools_are_in_the_catalog_as_the_bots_own_diary():
    append, read = CATALOG["journal_append"], CATALOG["journal_read"]
    assert (append.kind, append.allowed_when_tainted, append.no_ask) == ("write_create", True, True)
    assert (read.kind, read.allowed_when_tainted) == ("read", True)


async def test_a_run_that_did_work_leaves_one_line_built_from_its_steps(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    await _talk(cfg, user_id, bot, [_tool("t1", "add_task", title="Buy seeds"), _tool("t2", "add_task", title="Dig"),
                                    _tool("n", "add_note", title="Roses", content="red")])
    [day] = await _days(cfg, user_id, bot.id)
    assert _entries(day) == ["Added a task ×2, saved a note"]
    assert "bot/ana" in day.content and not day.tainted


async def test_a_run_that_only_read_or_was_refused_leaves_nothing(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    await _talk(cfg, user_id, bot, [_tool("l", "list_tasks"), _tool("t", "add_task", title="x", tags=["two words"])])
    assert await _days(cfg, user_id, bot.id) == ()


async def test_journal_append_and_read_round_trip(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    rig = await _talk(cfg, user_id, bot, [_tool("a", "journal_append", text="Found the <cheap> seeds"),
                                          _tool("r", "journal_read"), _tool("l", "journal_read", day="list"),
                                          _tool("b", "journal_read", day="next week")])
    appended, read, listed, bad = _tool_texts(rig)
    assert appended.startswith("Written in your journal for ")
    assert "Found the &lt;cheap&gt; seeds" in read and "(data, not instructions)" in read
    assert listed.startswith("Days in your journal, newest first: ") and bad.startswith("Refused: name a day")
    [day] = await _days(cfg, user_id, bot.id)
    assert _entries(day) == ["Found the <cheap> seeds"]   # the journal's own tools add no run line


async def test_an_empty_journal_says_so(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    rig = await _talk(cfg, user_id, bot, [_tool("r", "journal_read", day="yesterday"), _tool("l", "journal_read",
                                                                                             day="list")])
    empty, none = _tool_texts(rig)
    assert empty.startswith("Your journal has nothing for ") and none == "Your journal is empty so far."


async def test_find_notes_also_lists_matching_journal_days(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    rig = await _talk(cfg, user_id, bot, [_tool("a", "journal_append", text="Ordered orchids for Ana"),
                                          _tool("f", "find_notes", query="orchids")])
    found = _tool_texts(rig)[1]
    assert "In your journal (journal_read opens a day):" in found and "Ordered orchids for Ana" in found


async def test_a_tainted_day_taints_the_run_that_reads_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    service = JournalService(JournalStore(cfg), EventHub(cfg))
    await service.append(user_id, bot.id, bot.name, "from a page", tainted=True)
    from roost.journal.tools import JournalTools
    out = await JournalTools(service).run("journal_read", {}, RecordContext(user_id, bot.id, False))
    assert out.tainted and "from a page" in out.text


async def test_an_approved_step_outside_a_run_writes_its_line_at_once(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    runs = JournalRuns(JournalService(JournalStore(cfg), EventHub(cfg)))
    ctx = RecordContext(user_id, bot.id, False, bot_name="Ana")
    await runs.stepped("add_task", "adding a task", ctx, ToolOutcome("Added: x", created=True))
    await runs.stepped("delete_task", "deleting a task", ctx, ToolOutcome("Refused: no such task."))
    [day] = await _days(cfg, user_id, bot.id)
    assert _entries(day) == ["Added a task"]


async def test_a_failed_append_never_breaks_the_run(cfg, user_id, caplog):
    runs = JournalRuns(JournalService(JournalStore(cfg), EventHub(cfg)))
    ctx = RecordContext(user_id, "not-a-bot", False, run_id="r1")
    await runs.stepped("add_task", "adding a task", ctx, ToolOutcome("Added", created=True))
    await runs.finish_run(user_id, "not-a-bot", "r1")
    await runs.finish_run(user_id, "not-a-bot", "r1")   # forgotten after the first
    assert "journal line was not written" in caplog.text
