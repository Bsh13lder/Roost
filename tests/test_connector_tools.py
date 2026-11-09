"""Connector tools through the runner and the gate (design §4): reads taint, writes park on a card in every mode
and Yes runs exactly the stored call, the key never reaches a result, a card or the audit."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from roost.approvals.executor import ApprovedCalls
from roost.approvals.models import ApprovalCard, ApprovalState, steps_json
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.connectors import texts
from roost.connectors.http import ConnectorClient
from roost.connectors.limits import RunCounter
from roost.connectors.models import ConnectorDraft, ConnectorPatch
from roost.connectors.service import ConnectorService
from roost.connectors.store import ConnectorStore
from roost.connectors.tools import ConnectorTools
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path, init_db
from roost.desk.fake import FakeDesk
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import Gate
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner
from team_helpers import make_bot

SECRET = "sk-live-SECRET-0123456789"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    return user_id, (await make_bot(cfg, user_id, "Scout")).id


class Net:
    """A MockTransport that records requests and echoes the key back, like a careless API."""

    def __init__(self, resolved=("93.184.216.34",)) -> None:
        self.seen: list[httpx.Request] = []
        self.resolved = list(resolved)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return httpx.Response(200, json={"echo": request.headers.get("authorization", ""), "ok": True})

    async def resolve(self, host: str) -> list[str]:
        return self.resolved

    def client(self) -> ConnectorClient:
        return ConnectorClient(client_factory=lambda _pin: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
                               resolver=self.resolve)


def _service(cfg) -> ConnectorService:
    return ConnectorService(ConnectorStore(cfg), BotStore(cfg))


async def _connector(cfg, user_id, **fields):
    draft = {"name": "Search", "purpose": "keyword data", "base_url": "https://api.example.com/v1",
             "secret": SECRET} | fields
    return await _service(cfg).add(user_id, ConnectorDraft(**draft))


def _tools(cfg, net: Net, counter: RunCounter | None = None) -> ConnectorTools:
    return ConnectorTools(_service(cfg), net.client(), counter)


def _runner(cfg, ids, tools, *, mode="auto_edit", tainted=False, approval=True, cards=True, run_id="run-1"):
    user_id, bot_id = ids
    state = ApprovalState(mode=mode, ask_topics=frozenset(), cards=cards) if approval else None
    return ToolRunner(user_id=user_id, bot_id=bot_id, desk=FakeDesk(bot_id), gate=Gate(cfg), activity=ActivityBoard(),
                      events=EventHub(cfg), allowed=frozenset(CATALOG), tainted=tainted,
                      domain=DomainTools((tools,)), approval=state, run_id=run_id)


def _call(name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=name, name=name, arguments=arguments)


async def _audit_texts(cfg, user_id) -> str:
    dek = await get_user_dek(cfg, user_id)
    con = sqlite3.connect(get_db_path(cfg))
    try:
        rows = con.execute("SELECT detail FROM audit WHERE user_id = ?", (user_id,)).fetchall()
    finally:
        con.close()
    return " ".join(decrypt(row[0], dek, user_aad(user_id, "audit:detail")) for row in rows)


async def test_list_connectors_shows_names_never_keys(cfg, ids):
    user_id, bot_id = ids
    await _connector(cfg, user_id, allowed_prefixes=("/sites",))
    other = await make_bot(cfg, user_id, "Ledger")
    await _connector(cfg, user_id, name="Mail", base_url="https://mail.example.com", secret="x" * 20,
                     bot_ids=(other.id,))
    text = await _runner(cfg, ids, _tools(cfg, Net())).run(_call("list_connectors"))
    assert "Search" in text and "keyword data" in text and "api.example.com" in text and "/sites" in text
    assert "Mail" not in text and SECRET not in text and "••••" not in text


async def test_a_get_runs_taints_and_hides_an_echoed_key(cfg, ids):
    user_id, _ = ids
    await _connector(cfg, user_id)
    net = Net()
    runner = _runner(cfg, ids, _tools(cfg, net), mode="ask")
    text = await runner.run(_call("use_connector", connector="search", method="GET", path="/sites", query={"n": 5}))
    assert net.seen[0].headers["authorization"] == f"Bearer {SECRET}"
    assert str(net.seen[0].url) == "https://api.example.com/v1/sites?n=5"
    assert "HTTP 200" in text and "<connector_response" in text and SECRET not in text
    assert runner.tainted
    assert SECRET not in await _audit_texts(cfg, user_id)


@pytest.mark.parametrize("mode", ["ask", "auto_edit", "plan"])
@pytest.mark.parametrize("tainted", [False, True])
async def test_a_write_parks_on_a_card_and_sends_nothing(cfg, ids, mode, tainted):
    user_id, _ = ids
    made = await _connector(cfg, user_id)
    net = Net()
    runner = _runner(cfg, ids, _tools(cfg, net), mode=mode, tainted=tainted)
    await runner.run(_call("use_connector", connector="Search", method="post", path="/sites", json={"url": "x"}))
    assert net.seen == [] and runner.parked is not None
    step = runner.parked
    assert step.floor == "posting" and step.tainted_basis is tainted
    assert dict(step.arguments) == {"connector": "Search", "connector_id": made.id, "method": "POST",
                                    "path": "/sites", "json": {"url": "x"}}
    assert [(r.label, r.value) for r in step.rows][:3] == [("Connector", "Search"), ("Method", "POST"),
                                                          ("Path", "/sites")]
    assert step.rows[-1].label == "Body" and '"url": "x"' in step.rows[-1].value
    assert SECRET not in steps_json((step,))
    assert SECRET not in await _audit_texts(cfg, user_id)


@pytest.mark.parametrize("approval,cards", [(False, True), (True, False)])
async def test_a_write_is_refused_where_no_card_can_show(cfg, ids, approval, cards):
    user_id, _ = ids
    await _connector(cfg, user_id)
    net = Net()
    runner = _runner(cfg, ids, _tools(cfg, net), approval=approval, cards=cards)
    text = await runner.run(_call("use_connector", connector="Search", method="DELETE", path="/sites/1"))
    assert text == NEEDS_YOUR_OK_TEXT and net.seen == [] and runner.parked is None


async def test_yes_runs_exactly_the_stored_call(cfg, ids):
    user_id, bot_id = ids
    await _connector(cfg, user_id)
    net = Net()
    tools = _tools(cfg, net)
    runner = _runner(cfg, ids, tools)
    await runner.run(_call("use_connector", connector="Search", method="PATCH", path="/sites/1", json={"a": [1, 2]}))
    ctx = RecordContext(user_id=user_id, bot_id=bot_id, tainted=False)
    outcome = await tools.execute("use_connector", dict(runner.parked.arguments), ctx)
    assert net.seen[0].method == "PATCH" and json.loads(net.seen[0].content) == {"a": [1, 2]}
    assert outcome.tainted and not outcome.failed and SECRET not in outcome.text


async def test_a_tainted_card_still_runs_after_yes(cfg, ids):
    user_id, bot_id = ids
    await _connector(cfg, user_id)
    net = Net()
    tools = _tools(cfg, net)
    runner = _runner(cfg, ids, tools, tainted=True)
    await runner.run(_call("use_connector", connector="Search", method="POST", path="/sites", json={"a": 1}))
    card = ApprovalCard(id="c1", user_id=user_id, bot_id=bot_id, thread_id="t1", work_item_id=None, kind="ask",
                        state="open", steps=(runner.parked,), request="r", tainted=True, session_offer=False,
                        answer_item_id=None, created_at="t", closed_at=None)
    executor = ApprovedCalls(DomainTools((tools,)), Gate(cfg), TalkStore(cfg), EventHub(cfg))
    outcome = await executor.run(user_id, card, runner.parked)
    assert outcome.ok and outcome.tainted and len(net.seen) == 1
    assert SECRET not in await _audit_texts(cfg, user_id)


async def test_yes_on_a_deleted_or_unshared_connector_sends_nothing(cfg, ids):
    user_id, bot_id = ids
    made = await _connector(cfg, user_id)
    net = Net()
    tools = _tools(cfg, net)
    stored = {"connector": "Search", "connector_id": made.id, "method": "POST", "path": "/x"}
    ctx = RecordContext(user_id=user_id, bot_id=bot_id, tainted=False)
    other = await make_bot(cfg, user_id, "Ledger")
    await _service(cfg).update(user_id, made.id, ConnectorPatch(bot_ids=(other.id,)))
    assert (await tools.execute("use_connector", stored, ctx)).text == texts.GONE
    await _service(cfg).delete(user_id, made.id)
    assert (await tools.execute("use_connector", stored, ctx)).failed and net.seen == []


async def test_refusals_send_nothing(cfg, ids):
    user_id, _ = ids
    await _connector(cfg, user_id, auth_style="query", auth_name="key", allowed_prefixes=("/sites",))
    net = Net()
    runner = _runner(cfg, ids, _tools(cfg, net))
    cases = [
        ({"path": "https://evil.example.org/x"}, texts.BAD_PATH),
        ({"path": "//evil.example.org/x"}, texts.BAD_PATH),
        ({"path": "/sites/../admin"}, texts.BAD_PATH),
        ({"path": "/other"}, texts.OUTSIDE_PREFIXES),
        ({"path": "/sites", "query": {"KEY": "mine"}}, texts.BAD_QUERY_KEY),
        ({"path": "/sites", "method": "TRACE"}, texts.BAD_CALL),
        ({"path": "/sites", "query": {"a": {"nested": 1}}}, texts.BAD_CALL),
    ]
    for extra, sentence in cases:
        args = {"connector": "Search", "method": "GET"} | extra
        assert await runner.run(_call("use_connector", **args)) == sentence, extra
    unknown = await runner.run(_call("use_connector", connector="Nope", method="GET", path="/sites"))
    assert "No connector named Nope" in unknown and "Search" in unknown
    assert net.seen == [] and not runner.tainted


async def test_a_body_too_big_is_refused(cfg, ids):
    user_id, _ = ids
    await _connector(cfg, user_id)
    runner = _runner(cfg, ids, _tools(cfg, Net()))
    text = await runner.run(_call("use_connector", connector="Search", method="POST", path="/x", json="x" * 70_000))
    assert text == texts.BODY_TOO_BIG and runner.parked is None


async def test_a_private_address_and_the_run_cap(cfg, ids):
    user_id, _ = ids
    await _connector(cfg, user_id)
    private = Net(resolved=("10.0.0.5",))
    runner = _runner(cfg, ids, _tools(cfg, private))
    assert await runner.run(_call("use_connector", connector="Search", method="GET", path="/x")) == \
        texts.PRIVATE_ADDRESS
    assert private.seen == [] and not runner.tainted
    net = Net()
    runner = _runner(cfg, ids, _tools(cfg, net, RunCounter(limit=2)))
    for _ in range(2):
        await runner.run(_call("use_connector", connector="Search", method="HEAD", path="/x"))
    assert await runner.run(_call("use_connector", connector="Search", method="GET", path="/x")) == texts.RUN_CAP
    assert len(net.seen) == 2


def test_the_run_counter_forgets_old_runs():
    counter = RunCounter(limit=1, tracked=2)
    assert counter.take("a") and not counter.take("a")
    assert counter.take("b") and counter.take("c")
    assert counter.take("a")             # "a" was forgotten
    assert counter.take(None) and counter.take(None)


async def test_other_users_connectors_are_invisible(cfg, ids):
    user_id, _ = ids
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    await _connector(cfg, bob)
    runner = _runner(cfg, ids, _tools(cfg, Net()))
    assert await runner.run(_call("list_connectors")) == texts.NO_CONNECTORS
    text = await runner.run(_call("use_connector", connector="Search", method="GET", path="/x"))
    assert text.startswith("No connector named")
