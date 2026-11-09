"""The SDK process env turns CLI telemetry off and never carries the API key."""

from roost.llm.claude_sdk import build_options
from roost.llm.registry import DEFAULT_BOT_MODEL


def test_telemetry_off_and_api_key_excluded(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    env = build_options("sys", (), DEFAULT_BOT_MODEL).env
    assert env["DISABLE_TELEMETRY"] == "1"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert "ANTHROPIC_API_KEY" not in env
