"""Token usage: parsing the SDK's usage, the run's scope, and the per-day store (schema v39 ``token_usage``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import MIGRATIONS
from roost.gateway.auth import register_user
from roost.llm.types import Usage
from roost.usage.counts import UsageTotals, usage_from_sdk
from roost.usage.scope import UsageScope, current_scope, kind_for_work, kind_scope, note_usage, usage_scope
from roost.usage.store import TokenUsageStore
from roost.work.models import WorkKind

NOW = datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc)     # 00:30 on 4 November in Madrid


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail = fail

    async def add(self, user_id, bot_id, kind, model, usage) -> None:
        if self.fail:
            raise RuntimeError("disk full")
        self.calls.append((user_id, bot_id, kind, model, usage))


def test_usage_from_sdk_reads_the_four_counts():
    raw = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 300, "cache_creation_input_tokens": 7,
           "server_tool_use": {"web_search_requests": 0}}
    assert usage_from_sdk(raw) == Usage(input=10, output=5, cache_read=300, cache_write=7)


@pytest.mark.parametrize("raw", [None, {}, "junk", {"input_tokens": "a lot"}, {"input_tokens": -4}])
def test_usage_from_sdk_without_numbers_is_none(raw):
    assert usage_from_sdk(raw) is None


def test_usage_from_sdk_ignores_a_bad_count_but_keeps_the_rest():
    raw = {"input_tokens": 10, "output_tokens": True, "cache_read_input_tokens": 10**12}
    assert usage_from_sdk(raw) == Usage(input=10)


def test_totals_add_up_and_say_in_and_out():
    one = UsageTotals.of(Usage(input=10, output=5, cache_read=100, cache_write=2))
    both = one.plus(one)
    assert both.as_dict() == {"input": 20, "output": 10, "cache_read": 200, "cache_write": 4, "calls": 2,
                              "tokens_in": 224, "tokens_out": 10, "tokens": 234}
    assert UsageTotals().as_dict()["tokens"] == 0


def test_kind_for_work():
    assert kind_for_work(WorkKind.MESSAGE) == "chat"
    assert kind_for_work(WorkKind.CARD_ANSWER) == "chat"
    assert kind_for_work(WorkKind.TRIGGER) == "chat"
    assert kind_for_work(WorkKind.ROUTINE) == "routine"
    assert kind_for_work(WorkKind.HANDOFF) == "handoff"
    assert kind_for_work(WorkKind.ROOM_POST) == "room"


async def test_note_usage_without_a_scope_or_usage_records_nothing():
    recorder = Recorder()
    await note_usage("m", Usage(input=1))          # no scope
    with usage_scope(UsageScope(recorder, "u1", "b1", "chat")):
        await note_usage("m", None)                # no usage
    assert recorder.calls == []


async def test_note_usage_records_in_scope_and_kind_scope_changes_only_the_kind():
    recorder = Recorder()
    with usage_scope(UsageScope(recorder, "u1", "b1", "chat")):
        await note_usage("claude-sonnet-5-5", Usage(input=3))
        with kind_scope("helper"):
            await note_usage("claude-haiku-5-5", Usage(output=2))
        await note_usage("claude-haiku-5-5", Usage(output=1), kind="background")
        assert current_scope().kind == "chat"
    assert current_scope() is None
    assert recorder.calls == [("u1", "b1", "chat", "claude-sonnet-5-5", Usage(input=3)),
                              ("u1", "b1", "helper", "claude-haiku-5-5", Usage(output=2)),
                              ("u1", "b1", "background", "claude-haiku-5-5", Usage(output=1))]


async def test_kind_scope_without_a_scope_is_a_no_op():
    with kind_scope("helper"):
        assert current_scope() is None


async def test_a_failing_recorder_never_breaks_the_call(caplog):
    with usage_scope(UsageScope(Recorder(fail=True), "u1", "b1", "chat")):
        await note_usage("m", Usage(input=1))       # no exception
    assert "token usage" in caplog.text.lower()


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def test_the_migration_is_one_step_named_token_usage():
    migration = next(m for m in MIGRATIONS if m.name == "token usage")
    assert migration.version == 39 and len([m for m in MIGRATIONS if m.name == "token usage"]) == 1


async def test_the_table_exists_after_init(cfg):
    con = sqlite3.connect(get_db_path(cfg))
    try:
        cols = {row[1] for row in con.execute("PRAGMA table_info(token_usage)")}
    finally:
        con.close()
    assert {"user_id", "bot_id", "kind", "model", "day", "input_tokens", "output_tokens", "cache_read_tokens",
            "cache_write_tokens", "calls"} <= cols


async def test_store_sums_calls_into_one_row_per_day_kind_and_model(cfg):
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    store = TokenUsageStore(cfg, clock=lambda: NOW)
    await store.add(alice, "b1", "chat", "claude-sonnet-5-5", Usage(input=10, output=2))
    await store.add(alice, "b1", "chat", "claude-sonnet-5-5", Usage(input=5, output=1, cache_read=9))
    await store.add(alice, "b1", "background", "claude-haiku-5-5", Usage(input=1))
    await store.add(alice, None, "background", "claude-haiku-5-5", Usage(input=4))
    await store.add(alice, None, "background", "claude-haiku-5-5", Usage(input=4))
    await store.add(bob, "b9", "chat", "claude-sonnet-5-5", Usage(input=100))
    rows = await store.rows(alice, since_day="2026-11-01")
    by_key = {(r.bot_id, r.kind, r.model): r for r in rows}
    assert len(rows) == 3
    chat = by_key[("b1", "chat", "claude-sonnet-5-5")]
    assert chat.day == "2026-11-04"     # Madrid's day
    assert chat.totals == UsageTotals(input=15, output=3, cache_read=9, cache_write=0, calls=2)
    assert by_key[(None, "background", "claude-haiku-5-5")].totals.calls == 2
    assert [r.bot_id for r in await store.rows(alice, since_day="2026-11-01", bot_id="b1")] == ["b1", "b1"]
    assert await store.rows(alice, since_day="2026-11-05") == ()
    assert all(r.bot_id == "b9" for r in await store.rows(bob, since_day="2026-11-01"))


async def test_store_refuses_an_unknown_kind(cfg):
    alice = (await register_user(cfg, "alice", "pw-123456")).id
    store = TokenUsageStore(cfg, clock=lambda: NOW)
    with pytest.raises(ValueError):
        await store.add(alice, "b1", "mystery", "m", Usage(input=1))
