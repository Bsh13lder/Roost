"""Programs: a workspace path is relative, inside /workspace, and plain (docs/plans/2026-10-22-roost-programs.md §3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roost.constants import PROGRAM_COMMAND_MAX_CHARS, PROGRAM_FILE_MAX_CHARS, PROGRAM_PATH_MAX_CHARS, PROGRAM_TIMEOUT_DEFAULT_S
from roost.programs.args import ListArgs, ReadArgs, RunArgs, WriteArgs, workspace_path


@pytest.mark.parametrize("raw, kept", [
    ("a.txt", "a.txt"), ("src/main.py", "src/main.py"), ("/workspace/a.txt", "a.txt"),
    ("/workspace/src/x.py", "src/x.py"), ("notes/2026 plan.md", "notes/2026 plan.md"), ("a/", "a"),
])
def test_plain_paths_are_kept_relative(raw, kept):
    assert workspace_path(raw) == kept


@pytest.mark.parametrize("raw", [
    "", "/", "/etc/passwd", "/workspace", "/workspaces/a", "../x", "a/../b", "..", "./a", "a/./b", "a//b",
    "a\x00b", "a\nb", "a\tb", "x" * (PROGRAM_PATH_MAX_CHARS + 1), "~/x", "\\x",
])
def test_paths_outside_or_odd_are_refused(raw):
    with pytest.raises(ValueError):
        workspace_path(raw)


@pytest.mark.parametrize("raw", ["", "/workspace", "/workspace/", ".", "src"])
def test_a_folder_to_list_may_be_the_workspace_itself(raw):
    assert ListArgs.model_validate({"path": raw}).path in ("", "src")


def test_list_args_default_to_the_workspace():
    assert ListArgs.model_validate({}).path == ""


def test_run_args_take_a_command_and_a_bounded_timeout():
    assert RunArgs.model_validate({"command": "ls"}).timeout_s == PROGRAM_TIMEOUT_DEFAULT_S
    assert RunArgs.model_validate({"command": "ls", "timeout_s": 5}).timeout_s == 5
    for bad in ({"command": ""}, {"command": "  "}, {"command": "a\x00"},
                {"command": "x" * (PROGRAM_COMMAND_MAX_CHARS + 1)},
                {"command": "ls", "timeout_s": 0}, {"command": "ls", "timeout_s": 121}, {}):
        with pytest.raises(ValidationError):
            RunArgs.model_validate(bad)


def test_write_args_cap_the_text_and_check_the_path():
    assert WriteArgs.model_validate({"path": "/workspace/a.py", "text": "print(1)\n"}).path == "a.py"
    with pytest.raises(ValidationError):
        WriteArgs.model_validate({"path": "../a.py", "text": ""})
    with pytest.raises(ValidationError):
        WriteArgs.model_validate({"path": "a.py", "text": "x" * (PROGRAM_FILE_MAX_CHARS + 1)})
    with pytest.raises(ValidationError):
        ReadArgs.model_validate({"path": "/etc/passwd"})
