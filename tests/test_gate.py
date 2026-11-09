"""Unit tests for ``roost.talk.gate.Gate`` (M1 D3/D4): per-run allowlists
and gate kinds, the tainted-write rule, the link guard, with exactly one
encrypted ``audit`` row written per decision.
"""

from __future__ import annotations

import json

import pytest

from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import CU_FREE_ACT_TOOLS, MAX_TAINTED_CREATES_PER_RUN
from roost.crypto.encryption import decrypt, is_encrypted, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from types import MappingProxyType

from roost.llm.types import ToolSpec
from roost.talk.gate import (
    LINK_REFUSAL_TEXT, TAINTED_CHANGE_TEXT, TAINTED_CREATE_CAP_TEXT, GateContext, Gate, REFUSAL_TEXT,
)
from roost.talk.link_scope import LinkScope
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef

AVATAR = Avatar("round", "#22c55e", "none")

_EMPTY = {"type": "object", "properties": {}}
_FAKE = MappingProxyType({
    **CATALOG,
    "add_thing": ToolDef(ToolSpec("add_thing", "adds a record", _EMPTY), "write_create"),
    "change_thing": ToolDef(ToolSpec("change_thing", "changes a record", _EMPTY), "write_change"),
})
_ALL = frozenset(_FAKE)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    u = await register_user(cfg, "alice", "pw-123456")
    return u.id


@pytest.fixture
async def bot_id(cfg, user_id):
    bot = await BotStore(cfg).create(
        user_id, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR),
    )
    return bot.id


@pytest.fixture
def gate(cfg):
    return Gate(cfg)


@pytest.fixture
def fake_gate(cfg):
    return Gate(cfg, catalog=_FAKE)


async def _audit_rows(cfg, user_id: str) -> list:
    async with db_session(cfg) as db:
        cursor = await db.execute(
            "SELECT action, decision, detail FROM audit WHERE user_id = ? ORDER BY id", (user_id,),
        )
        return await cursor.fetchall()


async def test_a_tool_outside_this_runs_allowed_set_is_never(gate, user_id, bot_id):
    assert await gate.check(user_id, bot_id, "open_page", {"url": "https://x.example"}, allowed=frozenset({"get_time"})) == "never"


# C3: a click, typing or key press is judged only on the page's resolution; without one it is never.
# install_app and remove_app have no read form: they always ask (tests/test_apps_gate.py).
_NOT_ACTS = sorted(name for name, tool in CATALOG.items()
                   if tool.kind != "act" and not (tool.asks_always and tool.read_when is None)
                   and not tool.own_settings)   # set_my_voice: no card only in your own chat (test_voice_tool.py)


@pytest.mark.parametrize("name", _NOT_ACTS)
async def test_every_allowed_tool_decides_do(gate, user_id, bot_id, name):
    # A connector's write always asks (tests/test_connector_gate.py); its read is the "do" here.
    args = {"method": "GET"} if CATALOG[name].asks_always else {}
    assert await gate.check(user_id, bot_id, name, args) == "do"


# open_app has no page to resolve and is free inside the bot's own computer (full computer, D1;
# tests/test_cu_gate_screen.py).
@pytest.mark.parametrize("name", sorted(name for name, tool in CATALOG.items()
                                        if tool.kind == "act" and name not in CU_FREE_ACT_TOOLS))
async def test_an_act_without_a_page_resolution_is_never(gate, user_id, bot_id, name):
    assert await gate.check(user_id, bot_id, name, {}) == "never"


async def test_open_app_needs_no_page_resolution(gate, user_id, bot_id):
    assert await gate.check(user_id, bot_id, "open_app", {"app": "files"}) == "do"


async def test_allowed_tool_records_exactly_one_audit_row(gate, cfg, user_id, bot_id):
    await gate.check(user_id, bot_id, "open_page", {"url": "https://example.com"})

    rows = await _audit_rows(cfg, user_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "open_page"
    assert rows[0]["decision"] == "do"


async def test_unknown_tool_decides_never(gate, user_id, bot_id):
    decision = await gate.check(user_id, bot_id, "type_text", {"selector": "#x", "text": "hi"})
    assert decision == "never"


async def test_unknown_tool_records_one_audit_row_with_decision_never(gate, cfg, user_id, bot_id):
    await gate.check(user_id, bot_id, "type_text", {"selector": "#x", "text": "hi"})

    rows = await _audit_rows(cfg, user_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "type_text"
    assert rows[0]["decision"] == "never"


async def test_a_second_unrelated_tool_name_is_also_never(gate, user_id, bot_id):
    assert await gate.check(user_id, bot_id, "send_whatsapp", {}) == "never"


async def test_each_check_call_writes_its_own_audit_row(gate, cfg, user_id, bot_id):
    await gate.check(user_id, bot_id, "open_page", {"url": "https://a.example"})
    await gate.check(user_id, bot_id, "open_page", {"url": "https://b.example"})

    rows = await _audit_rows(cfg, user_id)
    assert len(rows) == 2


async def test_audit_detail_is_encrypted_and_holds_the_arguments(gate, cfg, user_id, bot_id):
    await gate.check(user_id, bot_id, "open_page", {"url": "https://example.com"})

    rows = await _audit_rows(cfg, user_id)
    detail = rows[0]["detail"]
    assert is_encrypted(detail)
    assert "example.com" not in detail

    dek = await get_user_dek(cfg, user_id)
    decrypted = json.loads(decrypt(detail, dek, user_aad(user_id, "audit:detail")))
    assert decrypted == {"url": "https://example.com"}


def test_refusal_text_matches_the_contracts_exact_wording():
    assert REFUSAL_TEXT == "Refused: that action is not available yet."


def test_every_catalog_tool_has_a_gate_kind():
    assert {tool.kind for tool in CATALOG.values()} <= {"read", "write_create", "write_change", "act"}


async def test_a_clean_run_may_create_and_change(fake_gate, user_id, bot_id):
    for name in ("add_thing", "change_thing"):
        verdict = await fake_gate.decide(user_id, bot_id, name, {}, GateContext(allowed=_ALL))
        assert (verdict.decision, verdict.reason) == ("do", "allowed")


async def test_a_tainted_run_may_create_and_the_verdict_says_so(fake_gate, user_id, bot_id):
    verdict = await fake_gate.decide(user_id, bot_id, "add_thing", {}, GateContext(allowed=_ALL, tainted=True))
    assert (verdict.decision, verdict.reason) == ("do", "tainted_create")


async def test_a_tainted_run_may_not_change_or_delete(fake_gate, user_id, bot_id):
    verdict = await fake_gate.decide(user_id, bot_id, "change_thing", {}, GateContext(allowed=_ALL, tainted=True))
    assert (verdict.decision, verdict.reason, verdict.text) == ("never", "tainted_change", TAINTED_CHANGE_TEXT)


async def test_a_create_past_the_cap_in_a_tainted_run_is_refused(fake_gate, user_id, bot_id):
    ctx = GateContext(allowed=_ALL, tainted=True, creates=MAX_TAINTED_CREATES_PER_RUN)
    verdict = await fake_gate.decide(user_id, bot_id, "add_thing", {}, ctx)
    assert (verdict.decision, verdict.reason, verdict.text) == ("never", "tainted_create_cap", TAINTED_CREATE_CAP_TEXT)


async def test_the_link_guard_refuses_a_model_made_url_and_allows_a_chain_link(gate, user_id, bot_id):
    ctx = GateContext(allowed=frozenset({"open_page"}), tainted=True,
                      link_guard=LinkScope.of(["https://example.com"]))
    refused = await gate.decide(user_id, bot_id, "open_page", {"url": "https://evil.example/?q=1"}, ctx)
    assert (refused.decision, refused.reason, refused.text) == ("never", "link_not_trusted", LINK_REFUSAL_TEXT)
    allowed = await gate.decide(user_id, bot_id, "open_page", {"url": "https://example.com/"}, ctx)
    assert (allowed.decision, allowed.url) == ("do", "https://example.com")   # R3: the stored entry


async def test_without_a_link_guard_a_tainted_run_still_opens_pages(gate, user_id, bot_id):
    ctx = GateContext(allowed=frozenset({"open_page"}), tainted=True)
    verdict = await gate.decide(user_id, bot_id, "open_page", {"url": "https://other.example"}, ctx)
    assert (verdict.decision, verdict.url) == ("do", None)


async def test_a_name_outside_the_catalog_is_never_even_when_allowed(gate, user_id, bot_id):
    verdict = await gate.decide(user_id, bot_id, "send_email", {}, GateContext(allowed=frozenset({"send_email"})))
    assert (verdict.decision, verdict.reason, verdict.text) == ("never", "not_allowed", REFUSAL_TEXT)


async def test_every_decision_writes_its_reason_and_the_runs_taint(fake_gate, cfg, user_id, bot_id):
    await fake_gate.decide(user_id, bot_id, "change_thing", {}, GateContext(allowed=_ALL, tainted=True))
    await fake_gate.decide(user_id, bot_id, "add_thing", {}, GateContext(allowed=_ALL))
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT action, decision, reason, tainted FROM audit WHERE user_id = ? ORDER BY id", (user_id,),
        )).fetchall()
    assert [tuple(row) for row in rows] == [
        ("change_thing", "never", "tainted_change", 1), ("add_thing", "do", "allowed", 0),
    ]


def test_a_tool_can_name_its_own_tainted_refusal():
    from roost.talk.gate import GateContext, judge
    from roost.talk.tool_catalog import CATALOG, TAINTED_CREATE_BOT_TEXT
    verdict = judge(CATALOG["create_bot"], "create_bot", {}, GateContext(allowed=frozenset({"create_bot"}), tainted=True))
    assert (verdict.decision, verdict.reason, verdict.text) == ("never", "tainted_change", TAINTED_CREATE_BOT_TEXT)
