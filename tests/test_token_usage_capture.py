"""Token usage capture: the SDK's ResultMessage usage reaches ``TurnDone``, the scripted models report fake usage,
and the step loop, the worker and a bot's runs record it against the right bot and kind."""

from __future__ import annotations

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.claude_sdk import ClaudeSdkModel
from roost.llm.registry import DEFAULT_BOT_MODEL, HAIKU, WORKER
from roost.llm.scripted import SCRIPTED_USAGE, ScriptedModel
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.scripted_worker import ScriptedWorker
from roost.llm.types import ChatTurn, ModelRequest, TextDelta, TurnDone, Usage
from roost.memory.worker import ask_worker
from roost.usage.scope import UsageScope, usage_scope
from roost.usage.store import TokenUsageStore
from team_helpers import make_bot, make_rig, send, wait_idle

_USAGE = Usage(input=11, output=4, cache_read=200, cache_write=9)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def add(self, user_id, bot_id, kind, model, usage) -> None:
        self.calls.append((user_id, bot_id, kind, model, usage))


class UsageModel:
    """Says ``text`` and reports ``_USAGE`` on every call."""

    def __init__(self, text: str = "Done.") -> None:
        self.text = text

    async def stream(self, request):
        yield TextDelta(self.text)
        yield TurnDone("end_turn", _USAGE)


async def test_the_sdk_models_usage_rides_on_turn_done(monkeypatch):
    import roost.llm.claude_sdk as sdk

    async def fake_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock("hi")], model=DEFAULT_BOT_MODEL)
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id="s1", stop_reason="end_turn", total_cost_usd=0.01,
                            usage={"input_tokens": 11, "output_tokens": 4, "cache_read_input_tokens": 200,
                                   "cache_creation_input_tokens": 9})

    monkeypatch.setattr(sdk, "query", fake_query)
    request = ModelRequest("sys", (ChatTurn("user", "hi"),), (), DEFAULT_BOT_MODEL)
    events = [event async for event in ClaudeSdkModel(DEFAULT_BOT_MODEL).stream(request)]
    assert events[-1] == TurnDone("end_turn", _USAGE)


async def test_the_scripted_models_report_fake_usage():
    request = ModelRequest("sys", (ChatTurn("user", "hi"),), (), DEFAULT_BOT_MODEL, agent="Scout")
    echo = [e async for e in ScriptedModel().stream(request)]
    team = [e async for e in ScriptedTeamModel.from_json({"Scout": [[{"text": "ok"}]]}).stream(request)]
    worker = [e async for e in ScriptedWorker().stream(request)]
    assert SCRIPTED_USAGE.input > 0
    assert echo[-1].usage == team[-1].usage == worker[-1].usage == SCRIPTED_USAGE


async def test_ask_worker_records_its_call_as_background_for_the_runs_bot():
    recorder = Recorder()
    with usage_scope(UsageScope(recorder, "u1", "b1", "chat")):
        assert await ask_worker(UsageModel("fine"), agent="x", system="s", text="t") == "fine"
    assert recorder.calls == [("u1", "b1", "background", WORKER, _USAGE)]


async def test_ask_worker_without_a_scope_records_nothing_and_still_answers():
    assert await ask_worker(UsageModel("fine"), agent="x", system="s", text="t") == "fine"


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    return cfg, user.id, bot


async def test_a_chat_run_records_its_steps_for_the_bot(world):
    cfg, user_id, bot = world
    rig = make_rig(cfg, UsageModel())
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    store = TokenUsageStore(cfg)
    rows = await store.rows(user_id, since_day="2000-01-01", bot_id=bot.id)
    chat = [r for r in rows if r.kind == "chat"]
    assert len(chat) == 1 and chat[0].totals.input == 11 and chat[0].totals.calls == 1
    assert chat[0].model == DEFAULT_BOT_MODEL


async def test_a_helper_records_as_helper(world):
    from roost.bots.status import ActivityBoard
    from roost.desk.fake import FakeDesk
    from roost.events.hub import EventHub
    from roost.helpers.run import run_helper
    from roost.talk.gate import Gate
    from roost.talk.tool_runner import ToolRunner

    cfg, user_id, bot = world
    recorder = Recorder()
    runner = ToolRunner(user_id=user_id, bot_id=bot.id, desk=FakeDesk(bot.id), gate=Gate(cfg),
                        activity=ActivityBoard(), events=EventHub(cfg), allowed=frozenset())
    with usage_scope(UsageScope(recorder, user_id, bot.id, "chat")):
        await run_helper(task="look", model=UsageModel("Report."), model_id=HAIKU.id, tool_runner=runner, tools=(),
                         agent="Scout/helper-1")
    assert recorder.calls == [(user_id, bot.id, "helper", HAIKU.id, _USAGE)]
