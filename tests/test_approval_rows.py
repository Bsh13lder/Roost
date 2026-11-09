"""Every card step shows ALL of its stored arguments, and what is shown is what Yes runs (security finding 2)."""

from __future__ import annotations

import pytest

from roost.approvals.models import PendingCall, approval_card_out, step_from_dict, step_to_dict
from roost.approvals.preview import preview_call
from roost.approvals.rows import with_rows
from roost.approvals import topics
from roost.constants import APPROVAL_ROW_SHOWN_CHARS
from roost.talk.tool_catalog import CATALOG


def _step(name, arguments):
    return with_rows(preview_call(name, arguments, topics.topic_of(name)))


def test_the_expense_card_shows_amount_and_income_first_and_everything_else():
    step = _step("log_expense", {"note": "coffee", "vendor": "v", "currency": "EUR", "spent_at": "today",
                                 "income": True, "amount": 9999})
    assert [r.key for r in step.rows][:2] == ["amount", "income"]
    assert step.rows[0].value == "9999" and step.rows[1].value == "Income (money in)"
    assert {r.key for r in step.rows} == set(step.arguments)


def test_an_expense_without_the_flag_shows_expense_and_stores_it():
    step = _step("log_expense", {"amount": 3, "note": "tea"})
    assert step.rows[1].key == "income" and step.rows[1].value == "Expense (money out)"
    assert step.arguments["income"] is False


def test_unknown_keys_are_dropped_from_the_stored_call():
    step = _step("add_task", {"title": "x", "sneaky": "rm -rf", "priority": "high"})
    assert "sneaky" not in step.arguments
    assert {r.key for r in step.rows} == set(step.arguments)


def test_booleans_lists_and_dicts_are_shown():
    step = _step("update_sheet_cells", {"document": "d", "cells": {"A1": "x", "B2": ["y"]}, "starred": True})
    values = {r.key: r.value for r in step.rows}
    assert '"A1": "x"' in values["cells"] and set(step.arguments) == set(values)


@pytest.mark.parametrize("name", sorted(n for n, t in CATALOG.items() if t.kind != "read" and not n.startswith("mac_")
                                        and n != "use_connector" and topics.topic_of(n) is not None))
def test_every_write_tool_card_shows_every_stored_argument(name):
    props = CATALOG[name].spec.input_schema.get("properties", {})
    sample = {k: ("x" if v.get("type") == "string" else True if v.get("type") == "boolean"
                  else 7 if v.get("type") in ("number", "integer") else ["a"]) for k, v in props.items()}
    step = _step(name, {**sample, "hidden_extra": "boo"})
    assert step is not None
    assert {r.key for r in step.rows} == set(step.arguments)
    assert "hidden_extra" not in step.arguments


def test_a_connector_step_shows_what_is_sent_and_hides_its_id():
    args = {"connector": "Search", "connector_id": "c1", "method": "POST", "path": "/x", "query": {"a": "1"},
            "json": {"b": 2}}
    step = with_rows(PendingCall(tool="use_connector", arguments=args, topic="posting", title="t"))
    assert [r.label for r in step.rows] == ["Connector", "Method", "Path", "Query", "Body"]
    assert dict(step.arguments) == args
    sneaky = PendingCall(tool="use_connector", arguments={**args, "secret": "k"}, topic="posting", title="t")
    assert with_rows(sneaky) is None


def test_a_step_that_cannot_be_rendered_gets_no_card():
    deep = {"a": 1}
    for _ in range(12):
        deep = {"n": deep}
    assert _step("add_task", {"title": "x", "notes": deep}) is None
    assert with_rows(PendingCall(tool="no_such_tool", arguments={"a": 1}, topic=None, title="t")) is None


def test_mac_steps_refuse_an_unexplained_key():
    ok = PendingCall(tool="mac_trash", arguments={"folder": "F", "grant_id": "g", "path": "a.md", "base_sha256": "h"},
                     topic="files", title="t")
    assert [r.key for r in with_rows(ok).rows] == ["folder", "path"]
    bad = PendingCall(tool="mac_trash", arguments={"folder": "F", "path": "a.md", "extra": 1}, topic="files", title="t")
    assert with_rows(bad) is None


def test_rows_survive_sealing_and_the_wire_cuts_long_text_but_full_has_all():
    long = "z" * (APPROVAL_ROW_SHOWN_CHARS * 3)
    step = _step("create_bot", {"name": "N", "job": "j", "instructions": long})
    again = step_from_dict(step_to_dict(step))
    assert again.rows == step.rows

    class _Card:
        id = "c"; bot_id = "b"; thread_id = "t"; kind = "ask"; state = "open"; tainted = False
        session_offer = False; created_at = "x"; closed_at = None; steps = (again,)

    cut = approval_card_out(_Card()).steps[0].rows
    row = next(r for r in cut if r.key == "instructions")
    assert row.truncated and len(row.value) == APPROVAL_ROW_SHOWN_CHARS
    whole = next(r for r in approval_card_out(_Card(), full=True).steps[0].rows if r.key == "instructions")
    assert whole.value == long and not whole.truncated
