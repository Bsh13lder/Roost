"""Tool groups (owner, 2026-11-09, "how does Claude Code do it? all tools in one turn is too much"): a run is
offered the core tools plus the groups it loaded; ``load_tools`` adds a group for the rest of the run."""

from __future__ import annotations

import pytest

from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_groups import (
    CORE_TOOLS, LOAD_TOOLS, TOOL_GROUPS, group_of, groups_in_text, index_text, load_tools_result, parse_groups,
    tool_groups_on, visible_specs,
)


def _specs(*names: str):
    return tuple(CATALOG[name].spec for name in names)


def test_every_catalog_tool_is_core_or_in_exactly_one_group():
    for name in CATALOG:
        if name == LOAD_TOOLS:
            continue
        homes = [group for group, tools in TOOL_GROUPS.items() if name in tools.names]
        assert (name in CORE_TOOLS) != bool(homes), name
        assert len(homes) <= 1, (name, homes)


def test_load_tools_is_in_the_catalog_as_a_read():
    assert CATALOG[LOAD_TOOLS].kind == "read"
    assert LOAD_TOOLS in CORE_TOOLS


def test_group_of():
    assert group_of("add_task") == "tasks"
    assert group_of("click") == "computer"
    assert group_of("remember") is None


def test_visible_specs_keep_core_and_loaded_groups_in_catalog_order():
    every = _specs("open_page", "add_task", "log_expense", "remember", LOAD_TOOLS)
    shown = visible_specs(every, frozenset({"money"}))
    assert [s.name for s in shown] == ["open_page", "log_expense", "remember", LOAD_TOOLS]


def test_visible_specs_keep_load_tools_even_when_nothing_is_left_to_load():
    """Keeping the cache warm (§4): the tool list's tail never changes mid-run, so load_tools stays offered."""
    every = _specs("open_page", "remember", LOAD_TOOLS)
    assert [s.name for s in visible_specs(every, frozenset())] == ["open_page", "remember", LOAD_TOOLS]
    assert [s.name for s in visible_specs(every, frozenset(TOOL_GROUPS))] == ["open_page", "remember", LOAD_TOOLS]


@pytest.mark.parametrize("text, groups", [
    ("add a task to call Ana tomorrow", {"tasks"}),
    ("recuérdame la tarea de mañana", {"tasks"}),
    ("I spent €12 on coffee", {"money"}),
    ("make a doc of my notes", {"notes"}),
    ("every morning at 8 check the news", {"routines"}),
    ("open upwork.com and sign in", {"computer"}),
    ("hello, how are you?", set()),
    ("run update_task on it", {"tasks"}),
])
def test_groups_in_text(text, groups):
    assert groups_in_text(text) == frozenset(groups)


def test_index_names_each_group_not_loaded_with_its_tools():
    every = _specs("open_page", "add_task", "list_tasks", "log_expense", LOAD_TOOLS)
    text = index_text(every, frozenset({"money"}))
    assert "tasks:" in text and "add_task" in text and "list_tasks" in text
    assert "money:" not in text and "log_expense" not in text
    assert LOAD_TOOLS in text


def test_index_is_empty_when_every_group_is_loaded():
    every = _specs("open_page", "add_task", LOAD_TOOLS)
    assert index_text(every, frozenset({"tasks"})) == ""


def test_parse_groups_takes_known_names_and_tool_names():
    assert parse_groups({"groups": ["tasks", "Money", "add_note", "nope"]}) == (
        frozenset({"tasks", "money", "notes"}), ("nope",))
    assert parse_groups({"groups": "tasks"}) == (frozenset({"tasks"}), ())
    assert parse_groups({}) == (frozenset(), ())


def test_load_tools_result_lists_what_came():
    allowed = ("add_task", "list_tasks", "log_expense", LOAD_TOOLS)
    text = load_tools_result(allowed, frozenset({"tasks"}), unknown=("nope",))
    assert "add_task" in text and "list_tasks" in text and "nope" in text and "log_expense" not in text
    assert "Nothing new" in load_tools_result(allowed, frozenset(), unknown=())


def test_the_switch(monkeypatch):
    monkeypatch.delenv("ROOST_TOOL_GROUPS", raising=False)
    assert tool_groups_on()
    monkeypatch.setenv("ROOST_TOOL_GROUPS", "off")
    assert not tool_groups_on()


def _item(kind: str, body: str):
    from roost.work.models import WorkItem
    return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin="user", body=body,
                    tainted=False, depth=0, parent_item_id=None, message_id=None, state="claimed", run_id=None,
                    inflight=None, result=None, result_tainted=False, created_at="", updated_at="")


def test_start_groups_read_the_items_and_the_recent_chat(monkeypatch):
    from roost.talk.run_groups import start_groups
    monkeypatch.delenv("ROOST_TOOL_GROUPS", raising=False)
    assert start_groups((_item("text", "hello"),), ("I added the task for Friday",), stuck_reply=False) == {"tasks"}
    assert start_groups((_item("text", "hello"),), (), stuck_reply=False) == frozenset()


def test_a_card_answer_or_a_stuck_reply_carries_on_the_screen(monkeypatch):
    from roost.talk.run_groups import start_groups
    monkeypatch.delenv("ROOST_TOOL_GROUPS", raising=False)
    assert "computer" in start_groups((_item("card_answer", "Yes"),), (), stuck_reply=False)
    assert "computer" in start_groups((_item("text", "done"),), (), stuck_reply=True)


def test_start_groups_off(monkeypatch):
    from roost.talk.run_groups import start_groups
    monkeypatch.setenv("ROOST_TOOL_GROUPS", "off")
    assert start_groups((_item("text", "add a task"),), (), stuck_reply=False) is None
