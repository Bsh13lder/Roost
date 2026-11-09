"""The activity pill's words (docs/plans/2026-10-23-roost-activity-pill.md): every tool step in plain words, never
code, a command line, typed text, a file's contents or a URL's path or query."""

from __future__ import annotations

import pytest

from roost.talk.plain_steps import PLAIN_KINDS, plain_step
from roost.talk.tool_catalog import CATALOG

SECRETS = ("sk-ant-SECRET123", "/etc/passwd", "rm -rf", "hunter2", "?token=abc", "SELECT * FROM", "| head -n 1")
SAFE_KEYS = {("web_search", "query"), ("add_task", "title"), ("ask_bot", "bot")}
ARG_NAMES = (
    "command", "text", "path", "url", "query", "title", "bot", "task", "body", "content", "edits", "key",
    "name", "description", "instructions", "app", "target", "new_text", "file", "note", "expect", "value",
)


def _args_with(tool: str, secret: str) -> dict:
    safe = {key for name, key in SAFE_KEYS if name == tool}
    return {key: secret for key in ARG_NAMES if key not in safe}


@pytest.mark.parametrize("tool", sorted(CATALOG))
@pytest.mark.parametrize("secret", SECRETS)
def test_no_tool_ever_leaks_code_or_secrets(tool, secret):
    step = plain_step(tool, _args_with(tool, secret))
    assert secret not in step.line
    assert step.kind in PLAIN_KINDS
    assert step.line and step.line[0].isupper()


def test_every_catalog_tool_has_its_own_words():
    fallback = plain_step("no_such_tool", {}).line
    assert [tool for tool in CATALOG if plain_step(tool, {}).line == fallback] == []


def test_a_search_names_its_query_and_a_page_its_host_only():
    assert plain_step("web_search", {"query": "WhatsApp   Web"}).line == "Searched the web for “WhatsApp Web”"
    page = plain_step("open_page", {"url": "https://web.whatsapp.com/path?token=abc"})
    assert (page.kind, page.line, page.host) == ("read", "Opened web.whatsapp.com", "web.whatsapp.com")


def test_a_program_never_shows_its_command():
    fetch = plain_step("run_program", {"command": "curl -sI -m 10 https://web.whatsapp.com | head -n 1"})
    assert (fetch.kind, fetch.line, fetch.host) == (
        "program", "Checked that web.whatsapp.com answers", "web.whatsapp.com")
    other = plain_step("run_program", {"command": "python3 build.py --key sk-1"})
    assert (other.line, other.host) == ("Ran a program", None)


def test_a_bad_host_in_a_fetch_is_just_a_program():
    assert plain_step("run_program", {"command": "curl http://$(cat /etc/passwd)"}).line == "Ran a program"


def test_task_title_and_teammate_are_plain_and_short():
    assert plain_step("add_task", {"title": "Call   the dentist"}).line == "Added a task: Call the dentist"
    assert plain_step("ask_bot", {"bot": "Chief", "task": "secret plan"}).line == "Asked Chief"
    assert len(plain_step("add_task", {"title": "x" * 300}).line) <= 120


def test_helpers_say_how_many_never_their_tasks():
    sent = plain_step("send_helpers", {"helpers": [{"task": "secret one"}, {"task": "secret two"}]})
    assert (sent.kind, sent.line) == ("bots", "Sent 2 helpers")
    assert plain_step("send_helpers", {"helpers": [{"task": "x"}]}).line == "Sent a helper"
    assert plain_step("send_helpers", {"helpers": "nonsense"}).line == "Sent helpers"


def test_screen_and_other_kinds():
    assert plain_step("click", {"target": {"text": "Send"}}).kind == "computer"
    assert plain_step("type", {"text": "hunter2"}).line == "Typed in a box"
    assert plain_step("open_app", {"app": "browser"}).line == "Opened the browser"
    assert plain_step("open_app", {"app": "gimp"}).line == "Opened an app"
    assert plain_step("remember", {"text": "x"}).kind == "memory"
    assert plain_step("log_expense", {}).kind == "money"
    assert plain_step("no_such_tool", {}).kind == "other"
