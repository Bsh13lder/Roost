"""Task 6: a helper is the shared step loop with a silent sink, a read-only runner and a shared computer."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.fake import FakeDesk
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.helpers.desk_lock import LockedDesk
from roost.helpers.run import HelperResult, run_helper
from roost.llm.registry import HAIKU
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.talk.gate import Gate
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner
from team_helpers import make_bot

_READ = frozenset({"open_page", "get_time"})


def _tool(name: str, call_id: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


def _say(text: str):
    return [TextDelta(text), TurnDone("end_turn")]


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    return cfg, user.id, bot.id


def _runner(cfg, ids, desk, events=None) -> ToolRunner:
    user_id, bot_id = ids
    return ToolRunner(
        user_id=user_id, bot_id=bot_id, desk=desk, gate=Gate(cfg), activity=ActivityBoard(),
        events=events or EventHub(cfg), allowed=_READ,
    )


def _specs():
    return tuple(CATALOG[n].spec for n in sorted(_READ))


async def _run(cfg, ids, model, desk=None, n=1, **options) -> HelperResult:
    return await run_helper(
        task="find the price", model=model, model_id=HAIKU.id, tool_runner=_runner(cfg, ids, desk or FakeDesk(ids[1])),
        tools=_specs(), agent=f"Scout/helper-{n}", **options,
    )


def test_the_parents_turns_still_pass():
    import subprocess, sys
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "tests/test_turn.py",
                           "tests/test_turn_model_choice.py", "tests/test_work_runner.py"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout[-2000:]


async def test_a_helper_runs_its_task_and_returns_its_summary(world):
    cfg, user, bot = world
    model = ScriptedTeamModel({"Scout/helper-1": [_tool("open_page", "a", url="https://example.com/p"),
                                                  _say("It costs 5 euros.")]})
    result = await _run(cfg, (user, bot), model)
    assert result.text == "It costs 5 euros."
    assert result.tainted is True and result.link_scope == ("https://example.com/p",)


async def test_a_clean_helper_taints_nothing(world):
    cfg, user, bot = world
    result = await _run(cfg, (user, bot), ScriptedTeamModel({"Scout/helper-1": [_say("Done.")]}))
    assert (result.tainted, result.link_scope) == (False, ())


async def test_a_helpers_text_never_reaches_the_chat(world):
    cfg, user, bot = world
    events = EventHub(cfg)
    published = []
    real = events.publish

    async def spy(uid, frame):
        published.append(frame["type"])
        await real(uid, frame)

    events.publish = spy
    model = ScriptedTeamModel({"Scout/helper-1": [_tool("get_time", "t"), _say("secret summary")]})
    await run_helper(task="t", model=model, model_id=HAIKU.id,
                     tool_runner=_runner(cfg, (user, bot), FakeDesk(bot), events), tools=_specs(), agent="Scout/helper-1")
    assert "text_delta" not in published and "message" not in published and "message_done" not in published


async def test_a_helper_stops_at_its_step_and_time_limits(world):
    cfg, user, bot = world
    loop = {"Scout/helper-1": [_tool("get_time", f"t{i}") for i in range(5)]}
    capped = await _run(cfg, (user, bot), ScriptedTeamModel(loop), max_steps=2)
    assert "limit" in capped.text

    class Slow:
        async def stream(self, request):
            await asyncio.sleep(5)
            yield TurnDone("end_turn")

    timed = await _run(cfg, (user, bot), Slow(), deadline_s=0.05)
    assert "limit" in timed.text


class _SlowDesk(FakeDesk):
    def __init__(self, bot_id):
        super().__init__(bot_id)
        self.now = 0
        self.peak = 0

    async def open_page(self, url):
        self.now += 1
        self.peak = max(self.peak, self.now)
        await asyncio.sleep(0.05)
        try:
            return await super().open_page(url)
        finally:
            self.now -= 1


async def test_helpers_take_turns_on_the_one_computer(world):
    cfg, user, bot = world
    desk = _SlowDesk(bot)
    shared = LockedDesk(desk)
    model = ScriptedTeamModel({
        f"Scout/helper-{n}": [_tool("open_page", f"o{n}", url=f"https://example.com/{n}"), _say("ok")] for n in (1, 2)
    })
    results = await asyncio.gather(*(
        run_helper(task="t", model=model, model_id=HAIKU.id, tool_runner=_runner(cfg, (user, bot), shared),
                   tools=_specs(), agent=f"Scout/helper-{n}") for n in (1, 2)
    ))
    assert desk.peak == 1 and [r.text for r in results] == ["ok", "ok"]
    assert len(desk.open_page_calls) == 2


async def test_a_helper_uses_the_model_it_was_given(world):
    cfg, user, bot = world
    seen: list[ModelRequest] = []

    class Spy:
        async def stream(self, request):
            seen.append(request)
            yield TextDelta("hi")
            yield TurnDone("end_turn")

    await _run(cfg, (user, bot), Spy())
    assert seen[0].model == HAIKU.id and seen[0].agent == "Scout/helper-1"
    assert {t.name for t in seen[0].tools} == _READ
    assert "read-only" in seen[0].system.lower() or "only read" in seen[0].system.lower()
