"""Multi-line paste (Amendment T): each line a task, an indented line a step of the task above."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.tasks.paste import split_paste

O = {"Origin": "http://127.0.0.1:18800"}


def test_split_plain_lines_and_steps():
    text = "Buy milk\n\nCall Ana tomorrow\n  - ask about rent\n\tbring keys\n- Pay bill\n  * not a bullet star"
    items = split_paste(text)
    assert [(i.line, i.steps) for i in items] == [
        ("Buy milk", ()), ("Call Ana tomorrow", ("ask about rent", "bring keys")),
        ("Pay bill", ("* not a bullet star",)),
    ]


def test_windows_line_ends_checkboxes_and_blank_lines():
    items = split_paste("- [ ] One\r\n- [x] Two\r\n\r\n   \r\n")
    assert [i.line for i in items] == ["One", "Two"]


def test_leading_indent_with_no_task_above_is_a_task():
    assert [i.line for i in split_paste("  first\n  second")] == ["first", "second"]


def test_too_many_lines_is_refused():
    with pytest.raises(ValueError, match="at most 50"):
        split_paste("\n".join(f"t{n}" for n in range(51)))


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_parse_many_reads_each_line_as_the_quick_line_does():
    c = _client()
    c.post("/api/projects", json={"name": "Reno"}, headers=O)
    read = c.post("/api/tasks/parse-many", json={"text": "Call plumber tomorrow !! /Reno\n  check pipes\nBuy milk *"},
                  headers=O)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["count"] == 2 and body["ready"] is True and body["problem"] is None
    first, second = body["tasks"]
    assert (first["title"], first["priority"], first["steps"]) == ("Call plumber", "high", ["check pipes"])
    assert first["project"]["name"] == "Reno" and first["due_date"]
    assert (second["title"], second["starred"], second["steps"]) == ("Buy milk", True, [])


def test_parse_many_says_what_is_wrong_and_is_not_ready():
    c = _client()
    body = c.post("/api/tasks/parse-many", json={"text": "Fine\nBad /Nowhere"}, headers=O).json()
    assert body["ready"] is False and "Nowhere" in body["problem"] and body["count"] == 2


def test_parse_many_never_hands_work_to_a_bot():
    c = _client()
    c.post("/api/bots", json={"name": "Scout", "job": "helps", "instructions": "",
                              "avatar": {"shape": "round", "color": "#22c55e", "badge": "none"}}, headers=O)
    body = c.post("/api/tasks/parse-many", json={"text": "Book @Scout\nOther"}, headers=O).json()
    assert body["ready"] is False and "one task at a time" in body["problem"]


def test_parse_many_guards_its_input():
    c = _client()
    assert c.post("/api/tasks/parse-many", json={"text": "x" * 30_000}, headers=O).status_code == 422
    assert c.post("/api/tasks/parse-many", json={"text": "\n\n"}, headers=O).status_code == 422
    assert c.post("/api/tasks/parse-many", json={"text": "a\nb"}).status_code == 403


def test_tasks_are_created_with_steps():
    c = _client()
    made = c.post("/api/tasks", json={"title": "Call", "steps": ["one", "two"]}, headers=O)
    assert made.status_code in (200, 201), made.text
    assert [s["title"] for s in made.json()["steps"]] == ["one", "two"]
    assert c.post("/api/tasks", json={"title": "x", "steps": ["s"] * 60}, headers=O).status_code == 422
