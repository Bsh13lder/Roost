"""A very long digit run is refused in plain words and never crashes (review A, finding 1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.amounts import MAX_NUMBER_DIGITS, number_value
from roost.money.expression import ExpressionError, evaluate
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
LONG = "1" * 40
LINES = [f"€{LONG} lunch", f"{LONG} lunch", f"€{LONG}x2 lunch", f"€1+{LONG} lunch", f"€{LONG},50 lunch",
         f"€{'1.234' * 10} lunch", f"€{'9' * 29} lunch", f"lunch {'7' * 13}€"]


def _client() -> TestClient:
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    return c


def test_number_value_refuses_more_than_the_digit_cap():
    assert MAX_NUMBER_DIGITS == 12
    assert number_value("1" * 12) is not None
    for text in ("1" * 13, LONG, "1" * 40 + ",50", "1." + "234." * 10 + "234"):
        assert number_value(text) is None


def test_evaluate_refuses_in_a_sentence():
    for text in (LONG, f"{LONG}x2", f"2x{LONG}", "1" * 13, "9" * 29):
        with pytest.raises(ExpressionError, match="12 digits"):
            evaluate(text)
    with pytest.raises(ExpressionError, match="at most 1,000,000"):
        evaluate("1" * 12)                  # 12 digits are read, then the amount cap speaks


@pytest.mark.parametrize("line", LINES)
def test_money_parse_never_500s(line):
    r = _client().post("/api/money/parse", json={"text": line}, headers=O)
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert r.json()["ready"] is False


@pytest.mark.parametrize("line", LINES)
def test_task_parse_never_500s(line):
    r = _client().post("/api/tasks/parse", json={"text": f"pay {line}"}, headers=O)
    assert r.status_code in (200, 422), r.text


def test_money_parse_says_why():
    r = _client().post("/api/money/parse", json={"text": f"€{LONG}x2 lunch"}, headers=O)
    assert "12 digits" in r.text


async def test_the_bot_tool_refuses_a_long_amount():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Life admin")
    rig = make_rig(cfg, team_model({"Life admin": [
        [ToolCallRequested(id="e", name="log_expense", arguments={"amount": LONG, "project": "food"}),
         TurnDone("tool_use")], say("ok")]}))
    thread = await rig.talk.create_thread(user.id, bot.id)
    await send(rig, user.id, bot.id, thread.id, "spent a lot")
    await wait_idle(rig.runner)
    texts = [t.text for t in rig.model.requests[-1].turns if t.role == "tool"]
    assert texts and texts[0].startswith("Refused:")
