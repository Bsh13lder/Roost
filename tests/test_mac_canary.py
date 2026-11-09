"""Task 12: a canary proves Mac file contents never reach logs, events or the audit in plaintext."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import httpx
import pytest

from approval_helpers import make_card_rig
from keeper_mac_helpers import build_rig
from mac_helpers import SwitchTransport
from roost.approvals.models import BotApproval
from roost.bots.store import BotStore
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.desk.client import KeeperClient
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.mac.files import KeeperMacFiles
from roost.mac.grant_service import GrantService
from roost.mac.grants import GrantStore
from roost.mac.limits import MacLimits
from roost.mac.marks import MacMarkStore, path_key
from roost.mac.redact import redact_for_audit
from roost.mac.tools import MacTools
from roost.talk.domain_tools import RecordContext
from roost.talk.gate import Gate
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

CANARY = "CANARY-7f3c9e"
SECRET_NAME = "secret-plan-91.md"
FORBIDDEN_KEYS = {"text", "edits", "query", "path", "new_text", "new_path", "base_hash", "base_sha256"}
DEK = b"d" * 32


def _call(name, call_id="c1", **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _audit_details(config, user_id: str, prefix: str = "") -> list[tuple[str, dict]]:
    dek = await get_user_dek(config, user_id)
    async with db_session(config) as db:
        rows = await (await db.execute(
            "SELECT action, detail FROM audit WHERE user_id = ? ORDER BY id", (user_id,))).fetchall()
    return [(row["action"], json.loads(decrypt(row["detail"], dek, user_aad(user_id, "audit:detail"))))
            for row in rows if row["action"].startswith(prefix)]


# --- the pure redaction ---------------------------------------------------------------------------


def test_a_mac_call_keeps_only_counts_flags_and_a_keyed_path():
    out = redact_for_audit(
        "mac_edit", {"folder": "MySpace", "path": SECRET_NAME, "base_hash": "ab" * 32,
                     "edits": [{"old": "a", "new": CANARY}, {"old": "b", "new": "c"}], "text": CANARY}, DEK)
    assert out == {"folder": "MySpace", "path_key": path_key(DEK, "MySpace", SECRET_NAME), "chars": len(CANARY),
                   "edit_count": 2, "has_text": True}
    find = redact_for_audit("mac_find", {"query": SECRET_NAME, "text": CANARY, "folder": "F"}, DEK)
    assert find == {"folder": "F", "has_query": True, "has_text": True}
    assert CANARY not in json.dumps(out) and SECRET_NAME not in json.dumps([out, find])


def test_a_resolved_step_is_redacted_the_same_way():
    out = redact_for_audit("mac_write_new", {"folder": "F", "grant_id": "g", "path": "a.md", "new_text": CANARY}, DEK)
    assert out["chars"] == len(CANARY) and "new_text" not in out and "path" not in out and CANARY not in json.dumps(out)


def test_record_writes_keep_ids_and_numbers_but_not_their_words():
    out = redact_for_audit("add_note", {"title": "t " + CANARY, "body": CANARY, "project_id": "p1"}, DEK)
    assert CANARY not in json.dumps(out) and out["project_id"] == "p1"
    money = redact_for_audit("log_expense", {"amount": 12.5, "vendor": CANARY, "currency": "EUR"}, DEK)
    assert money["amount"] == 12.5 and money["currency"] == "EUR" and CANARY not in json.dumps(money)


def test_a_non_write_call_is_unchanged():
    args = {"url": "https://example.com/a?b=c"}
    assert redact_for_audit("open_page", args, DEK) == args


# --- the gate's audit -----------------------------------------------------------------------------


@pytest.fixture
async def rig(tmp_path: Path):
    keeper = build_rig(tmp_path, push=False)
    await init_db(keeper.config)
    user = await register_user(keeper.config, "alice", "pw-123456")
    return keeper, user.id


async def test_mac_audit_details_are_redacted(rig):
    keeper, user_id = rig
    gate = Gate(keeper.config)
    bot = await make_bot(keeper.config, user_id, "Scout")
    arguments = {"folder": "F", "path": SECRET_NAME, "text": CANARY, "edits": [{"old": "a", "new": CANARY}],
                 "query": CANARY, "new_text": CANARY}
    for name in ("mac_find", "mac_read", "mac_write_new", "mac_edit", "mac_rename", "mac_trash"):
        await gate.check(user_id, bot.id, name, dict(arguments))
    await gate.record_approved(user_id, bot.id, "mac_edit", dict(arguments), reason="approved", tainted=False)
    await gate.record_approved(user_id, bot.id, "mac_write_new", dict(arguments), reason="plan_accepted", tainted=False)
    details = await _audit_details(keeper.config, user_id, "mac_")
    assert len(details) == 8
    for _, detail in details:
        assert not FORBIDDEN_KEYS & set(detail)
        assert CANARY not in json.dumps(detail) and SECRET_NAME not in json.dumps(detail)


# --- the whole path, with the real keeper ---------------------------------------------------------


def _read_all_logs(keeper) -> str:
    log = keeper.config.database_dir / "keeper-audit.log"
    return log.read_text() if log.exists() else ""


async def test_a_canary_never_reaches_the_db_logs_or_audit_in_plaintext(rig, caplog, monkeypatch):
    keeper, user_id = rig
    cfg = keeper.config
    caplog.set_level(logging.DEBUG)
    events: list[str] = []
    original = EventHub.publish

    async def recording(self, uid, event):
        events.append(json.dumps(event, default=str))
        return await original(self, uid, event)

    monkeypatch.setattr(EventHub, "publish", recording)
    files = KeeperMacFiles(cfg, client=KeeperClient(cfg, transport=httpx.ASGITransport(app=keeper.app)))
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    await grants.add(user_id, path=str(keeper.root), label="MySpace", access="read_write",
                     read_policy="ask_each", bot_id=None)
    bot = await make_bot(cfg, user_id, "Scout")
    first = f"first line {CANARY}\n"
    sha = hashlib.sha256(first.encode()).hexdigest()
    script = [
        _call("mac_write_new", "w1", folder="MySpace", path=SECRET_NAME, text=first),
        _call("mac_edit", "w2", folder="MySpace", path=SECRET_NAME, base_hash=sha,
              edits=[{"old": "first", "new": f"second {CANARY}"}]),
        say("done"),
    ]
    runner = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Scout": script})),
                           mac_files=files, grants=grants, limits=MacLimits())
    await runner.bots.set_approval(user_id, bot.id, BotApproval("auto_edit", frozenset()))
    thread = await runner.talk.create_thread(user_id, bot.id)
    await send(runner, user_id, bot.id, thread.id, "write it")
    await wait_idle(runner.runner)
    assert (keeper.root / SECRET_NAME).read_text() == f"second {CANARY} line {CANARY}\n"

    reads = MacTools(grants, files, MacMarkStore(cfg))
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=False, thread_id=thread.id)
    found = await reads.run("mac_find", {"text": CANARY}, ctx)
    read = await reads.run("mac_read", {"folder": "MySpace", "path": SECRET_NAME}, ctx)
    assert CANARY in found.text and CANARY in read.text         # the bot may see it; nothing else may

    for _, detail in await _audit_details(cfg, user_id):
        assert CANARY not in json.dumps(detail) and SECRET_NAME not in json.dumps(detail)
    assert len(await _audit_details(cfg, user_id, "mac_")) >= 2
    assert not any(CANARY in event for event in events)
    assert not any(CANARY in record.getMessage() or SECRET_NAME in record.getMessage() for record in caplog.records)
    assert CANARY not in _read_all_logs(keeper) and SECRET_NAME not in _read_all_logs(keeper)
    for path in cfg.database_dir.glob("roost.db*"):
        assert CANARY.encode() not in path.read_bytes()


class _Down(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise httpx.ConnectError("keeper is away")


async def test_python_logs_never_carry_a_path_on_errors(rig, caplog):
    keeper, user_id = rig
    cfg = keeper.config
    caplog.set_level(logging.DEBUG)
    switch = SwitchTransport(httpx.ASGITransport(app=keeper.app))
    files = KeeperMacFiles(cfg, client=KeeperClient(cfg, transport=switch))
    grants = GrantService(GrantStore(cfg), BotStore(cfg), files)
    await grants.add(user_id, path=str(keeper.root), label="MySpace", access="read_write",
                     read_policy="ask_each", bot_id=None)
    bot = await make_bot(cfg, user_id, "Scout")
    (keeper.root / SECRET_NAME).write_text(f"hello {CANARY}\n")
    from roost.mac.write_tools import MacWrites
    from roost.talk.store import TalkStore
    writes = MacWrites(grants, files, MacMarkStore(cfg), TalkStore(cfg), EventHub(cfg))
    ctx = RecordContext(user_id=user_id, bot_id=bot.id, tainted=False, thread_id=None)
    changed = await writes.run("mac_edit", {"folder": "MySpace", "path": SECRET_NAME, "base_hash": "0" * 64,
                                            "text": CANARY}, ctx)
    missing = await writes.run("mac_trash", {"folder": "MySpace", "path": "gone-" + SECRET_NAME}, ctx)
    assert "changed" in changed.text.lower() and missing.text
    switch.current = _Down()
    outage = await writes.run("mac_trash", {"folder": "MySpace", "path": SECRET_NAME}, ctx)
    assert outage.text
    for record in caplog.records:
        text = record.getMessage() + str(record.exc_text or "")
        assert SECRET_NAME not in text and CANARY not in text and str(keeper.root) not in text
