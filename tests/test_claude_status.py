"""Tests for ``python -m roost.llm.claude_status`` — what ``make
claude-status`` runs inside the gateway container to say whether the
bundled ``claude`` CLI is logged in.

It reads ``$CLAUDE_CONFIG_DIR/.credentials.json`` (the gateway image sets
``CLAUDE_CONFIG_DIR=/home/roost/.claude``, a named volume) and prints one
line: ``logged in until <date>``, ``expired`` or ``not logged in``. It
must never print the token itself. Every test uses a ``tmp_path`` config
dir — never a real one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from roost.llm import claude_status

_NOW_MS = 1_760_000_000_000  # 2025-10-09T08:53:20Z


def _write_credentials(config_dir: Path, payload: object) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / ".credentials.json"
    path.write_text(json.dumps(payload))
    return path


def _oauth(expires_at: object, token: str = "sk-ant-oat-secret-value") -> dict:
    return {"claudeAiOauth": {"accessToken": token, "refreshToken": "r", "expiresAt": expires_at}}


def test_missing_file_is_not_logged_in(tmp_path):
    assert claude_status.describe_login(tmp_path / ".credentials.json", _NOW_MS) == "not logged in"


def test_future_expiry_is_logged_in_until_that_date(tmp_path):
    expires = _NOW_MS + 3_600_000
    path = _write_credentials(tmp_path, _oauth(expires))
    when = datetime.fromtimestamp(expires / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    assert claude_status.describe_login(path, _NOW_MS) == f"logged in until {when}"


def test_past_expiry_is_expired(tmp_path):
    path = _write_credentials(tmp_path, _oauth(_NOW_MS - 1))
    assert claude_status.describe_login(path, _NOW_MS) == "expired"


def test_expiry_exactly_now_is_expired(tmp_path):
    path = _write_credentials(tmp_path, _oauth(_NOW_MS))
    assert claude_status.describe_login(path, _NOW_MS) == "expired"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"claudeAiOauth": None},
        {"claudeAiOauth": {}},
        {"claudeAiOauth": {"accessToken": "", "expiresAt": _NOW_MS + 1}},
        [],
        "just a string",
    ],
)
def test_no_access_token_is_not_logged_in(tmp_path, payload):
    path = _write_credentials(tmp_path, payload)
    assert claude_status.describe_login(path, _NOW_MS) == "not logged in"


@pytest.mark.parametrize("expires_at", [None, "soon", True])
def test_missing_or_bad_expiry_with_a_token_is_expired(tmp_path, expires_at):
    # Can't prove it's still valid -> report the safe answer, so the user
    # re-logs in rather than trusting a token that may be dead.
    path = _write_credentials(tmp_path, _oauth(expires_at))
    assert claude_status.describe_login(path, _NOW_MS) == "expired"


def test_malformed_json_is_not_logged_in(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text("{not json")
    assert claude_status.describe_login(path, _NOW_MS) == "not logged in"


def test_credentials_path_follows_claude_config_dir(tmp_path):
    assert claude_status.credentials_path({"CLAUDE_CONFIG_DIR": str(tmp_path)}) == tmp_path / ".credentials.json"


def test_credentials_path_defaults_to_home_dot_claude(tmp_path):
    assert claude_status.credentials_path({"HOME": str(tmp_path)}) == tmp_path / ".claude" / ".credentials.json"


def test_main_prints_one_line_and_never_the_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    _write_credentials(tmp_path, _oauth(4_102_444_800_000))  # 2100-01-01
    assert claude_status.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("logged in until 2100-01-01")
    assert out.count("\n") == 1
    assert "sk-ant-oat-secret-value" not in out


def test_main_not_logged_in(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    assert claude_status.main() == 0
    assert capsys.readouterr().out == "not logged in\n"


def test_unreadable_credentials_are_reported_on_stderr(tmp_path, capsys):
    path = tmp_path / ".credentials.json"
    path.mkdir()  # a directory where the file should be -> OSError on read
    assert claude_status.describe_login(path, _NOW_MS) == "not logged in"
    assert "could not read" in capsys.readouterr().err
