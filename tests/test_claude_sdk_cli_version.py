"""The SDK's bundled Claude Code CLI must know the model ids in roost/llm/registry.py."""

import re
import subprocess
from pathlib import Path

import claude_agent_sdk
import pytest



MIN_BUNDLED_CLI_VERSION = (2, 1, 280)  # the Claude 5.5 model ids need CLI 2.1.280+
_BINARY = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"


def parse_version(text: str) -> tuple[int, ...]:
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    assert found, f"no version in {text!r}"
    return tuple(int(part) for part in found.groups())


def test_old_cli_is_below_the_minimum():
    assert parse_version("2.1.238 (Claude Code)") < MIN_BUNDLED_CLI_VERSION


@pytest.mark.skipif(not _BINARY.exists(), reason="bundled CLI binary is missing")
def test_bundled_cli_is_new_enough():
    out = subprocess.run([str(_BINARY), "--version"], capture_output=True, text=True, timeout=30, check=True).stdout
    assert parse_version(out) >= MIN_BUNDLED_CLI_VERSION
