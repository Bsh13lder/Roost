"""Tests for the turn loop (``roost.talk.turn.run_turn`` via
``roost.talk.runner.TurnRunner``) — contract's Interfaces and Review
Focus #2 ("a hostile page's text is data, not instructions").

Every event the loop publishes also reaches a plain in-memory
``EventHub.subscribe`` in these tests, so assertions can check the exact
frame sequence a WS client would have seen, without a real WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from roost.bots.models import Avatar, BotDraft, BotStatus, BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk import DeskFactory
from roost.desk.fake import FakeDesk
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.llm.types import ModelRequest, ModelUnreachable, TextDelta, ToolCallRequested, TurnDone
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore

AVATAR = Avatar("round", "#22c55e", "none")


class _RecordingModel:
    """Wraps ``ScriptedModel`` to record every ``ModelRequest`` it was
    asked to stream — lets a test inspect what a LATER call's history
    looked like (e.g. that a tool result got wrapped in
    ``<untrusted_page>``) without needing the real Claude SDK's own
    prompt renderer, which only ``ClaudeSdkModel`` uses."""

    def __init__(self, script):
        self._inner = ScriptedModel(script=script)
        self.requests: list[ModelRequest] = []

    async def stream(self, request):
        self.requests.append(request)
        async for event in self._inner.stream(request):
            yield event


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
    store = BotStore(cfg)
    bot = await store.create(user_id, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    await store.update(user_id, bot.id, BotPatch(computer="mac_brave"))   # these tests fake the Mac Brave desk
    return bot.id


def _runner(cfg, *, model=None, script=None):
    model = model if model is not None else _RecordingModel(script or [])
    bots = BotStore(cfg)
    talk = TalkStore(cfg)
    events = EventHub(cfg)
    desks = DeskFactory(cfg)
    activity = ActivityBoard()
    runner = TurnRunner(cfg, bots, talk, events, desks, model, activity)
    return runner, bots, talk, events, desks, model


async def _drain(subscription, count: int, *, steps: bool = False) -> list[dict]:
    """The next ``count`` frames; the activity pill's ``run_step`` frames are skipped unless ``steps``."""
    frames: list[dict] = []
    while len(frames) < count:
        frame = await asyncio.wait_for(subscription.__anext__(), timeout=2)
        if steps or frame.get("type") != "run_step":
            frames.append(frame)
    return frames


async def test_a_run_tells_the_activity_pill_its_steps_in_plain_words(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "https://example.com/a?b=1"})],
        [TextDelta("Done."), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")
    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = []
    while not frames or frames[-1].get("type") != "bot_status" or frames[-1].get("status") != "resting":
        frames.append(await asyncio.wait_for(sub.__anext__(), timeout=2))
    sub.close()
    steps = [(f["step"], f["kind"], f["state"], f["line"]) for f in frames if f["type"] == "run_step"]
    assert steps == [
        (1, "think", "start", "Thinking"), (1, "think", "done", "Thinking"),
        (2, "read", "start", "Opened example.com"), (2, "read", "done", "Opened example.com"),
        (3, "message", "start", "Writing the reply"), (3, "message", "done", "Writing the reply"),
    ]
    assert {f["thread_id"] for f in frames if f["type"] == "run_step"} == {thread.id}


# ---------------------------------------------------------------------------
# Plain reply
# ---------------------------------------------------------------------------

async def test_plain_reply_is_stored_and_streamed(cfg, user_id, bot_id):
    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("Hi "), TextDelta("there"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _drain(sub, 7)
    sub.close()

    assert [f["type"] for f in frames] == [
        "bot_status", "message", "text_delta", "text_delta", "message", "message_done", "bot_status",
    ]
    assert frames[0]["status"] == "on_it"
    assert frames[-1]["status"] == "resting"
    assert frames[1]["message"]["body"] == ""  # Ruling 15's placeholder
    assert frames[4]["message"]["body"] == "Hi there"
    assert frames[4]["message"]["id"] == frames[1]["message"]["id"]  # same pre-generated id

    messages = await talk.list_messages(user_id, thread.id)
    bot_messages = [m for m in messages if m.role == "bot"]
    assert len(bot_messages) == 1
    assert bot_messages[0].body == "Hi there"
    assert bot_messages[0].tainted is False
    assert bot_messages[0].id == frames[1]["message"]["id"]

    bot = await bots.get(user_id, bot_id)
    assert bot.status == BotStatus.RESTING


async def test_status_sequence_is_on_it_then_resting(cfg, user_id, bot_id):
    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("hi"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _drain(sub, 6)
    sub.close()

    statuses = [f["status"] for f in frames if f["type"] == "bot_status"]
    assert statuses == ["on_it", "resting"]


# ---------------------------------------------------------------------------
# open_page: taint + <untrusted_page> wrapping
# ---------------------------------------------------------------------------

async def test_open_page_call_taints_the_reply_and_wraps_the_page_for_the_model(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "https://example.com"})],
        [TextDelta("Done."), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")

    await runner.run_turn(user_id, bot_id, thread.id)

    fake_desk = desks.for_bot(bot_id)
    assert isinstance(fake_desk, FakeDesk)
    assert fake_desk.open_page_calls == ["https://example.com"]

    messages = await talk.list_messages(user_id, thread.id)
    bot_message = next(m for m in messages if m.role == "bot")
    assert bot_message.tainted is True
    assert bot_message.body == "Done."

    assert len(model.requests) == 2
    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "<untrusted_page" in second_request_text


async def test_open_page_blocked_host_is_not_tainted_and_returns_the_blocked_text(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "http://192.168.1.1"})],
        [TextDelta("ok"), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open 192.168.1.1")

    await runner.run_turn(user_id, bot_id, thread.id)

    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "Blocked: that address is not allowed." in second_request_text

    messages = await talk.list_messages(user_id, thread.id)
    bot_message = next(m for m in messages if m.role == "bot")
    assert bot_message.tainted is False


# ---------------------------------------------------------------------------
# Disallowed tool call: refused + audited
# ---------------------------------------------------------------------------

async def test_read_page_call_taints_and_wraps_the_page(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="read_page", arguments={})],
        [TextDelta("Done."), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "what does the page say")

    await runner.run_turn(user_id, bot_id, thread.id)

    messages = await talk.list_messages(user_id, thread.id)
    bot_message = next(m for m in messages if m.role == "bot")
    assert bot_message.tainted is True

    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "<untrusted_page" in second_request_text


async def test_open_page_desk_unavailable_returns_the_unavailable_text(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "https://example.com"})],
        [TextDelta("ok"), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    fake_desk = desks.for_bot(bot_id)
    fake_desk.force_unavailable = True
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")

    await runner.run_turn(user_id, bot_id, thread.id)

    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "Your computer is unavailable right now." in second_request_text

    messages = await talk.list_messages(user_id, thread.id)
    bot_message = next(m for m in messages if m.role == "bot")
    assert bot_message.tainted is False


async def test_read_page_desk_unavailable_returns_the_unavailable_text(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="read_page", arguments={})],
        [TextDelta("ok"), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    fake_desk = desks.for_bot(bot_id)
    fake_desk.force_unavailable = True
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "what does the page say")

    await runner.run_turn(user_id, bot_id, thread.id)

    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "Your computer is unavailable right now." in second_request_text


async def test_run_turn_ignores_activity_and_system_history_when_building_turns(cfg, user_id, bot_id):
    """Only ``user``/``bot`` history rows become model turns (``roost.talk.
    turn._chat_turn_for``) -- an ``activity``/``system`` row is a UI/
    operational annotation the model doesn't need replayed every turn."""
    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("ok"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")
    await talk.add_message(user_id, thread.id, "system", "I hit my step limit — say continue.")
    await talk.add_message(user_id, thread.id, "activity", "opened example.com")

    await runner.run_turn(user_id, bot_id, thread.id)

    roles_sent_to_model = [t.role for t in model.requests[0].turns]
    assert roles_sent_to_model == ["user"]


async def test_run_turn_sends_the_model_the_newest_messages_not_the_oldest(cfg, user_id, bot_id, monkeypatch):
    """Final review, finding 8: ``list_messages``'s default (``ORDER BY
    seq ASC LIMIT 200``) returns the OLDEST page -- past that point the
    model would never see the user's newest message and would answer
    stale context. ``run_turn`` must load the NEWEST page instead."""
    import roost.talk.store as store_module

    monkeypatch.setattr(store_module, "DEFAULT_MESSAGE_PAGE_LIMIT", 2)

    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("ok"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "oldest -- must be dropped")
    await talk.add_message(user_id, thread.id, "bot", "middle")
    await talk.add_message(user_id, thread.id, "user", "newest -- must reach the model")

    await runner.run_turn(user_id, bot_id, thread.id)

    sent_texts = [t.text for t in model.requests[0].turns]
    assert "oldest -- must be dropped" not in sent_texts
    assert "newest -- must reach the model" in sent_texts


async def test_run_turn_deadline_adds_a_system_message(cfg, user_id, bot_id, monkeypatch):
    import roost.talk.turn as turn_module

    monkeypatch.setattr(turn_module, "MAX_RUN_SECONDS", -1)  # already "expired" on the first check

    runner, bots, talk, events, desks, model = _runner(
        cfg, script=[[TextDelta("never reached"), TurnDone("end_turn")]],
    )
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    await runner.run_turn(user_id, bot_id, thread.id)

    messages = await talk.list_messages(user_id, thread.id)
    assert any(m.role == "system" and m.body == "I hit my step limit — say continue." for m in messages)
    assert model.requests == []  # the deadline was already past before any model call


async def test_disallowed_tool_call_is_refused_and_leaves_one_never_audit_row(cfg, user_id, bot_id):
    script = [
        [ToolCallRequested(id="tu_1", name="type_text", arguments={"selector": "#x", "text": "hi"})],
        [TextDelta("ok"), TurnDone("end_turn")],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "type something")

    await runner.run_turn(user_id, bot_id, thread.id)

    second_request_text = " ".join(t.text for t in model.requests[1].turns)
    assert "Refused: that action is not available yet." in second_request_text

    async with db_session(cfg) as db:
        cursor = await db.execute(
            "SELECT decision FROM audit WHERE user_id = ? AND action = ?", (user_id, "type_text"),
        )
        rows = await cursor.fetchall()
    assert [r["decision"] for r in rows] == ["never"]


# ---------------------------------------------------------------------------
# Step cap
# ---------------------------------------------------------------------------

async def test_step_cap_adds_a_system_message(cfg, user_id, bot_id, monkeypatch):
    import roost.talk.turn as turn_module

    monkeypatch.setattr(turn_module, "MAX_STEPS", 2)

    # Every step asks for another tool call, so the loop never finds a
    # natural TurnDone-without-tool-calls exit and must hit the cap.
    script = [
        [ToolCallRequested(id="tu_1", name="get_time", arguments={})],
        [ToolCallRequested(id="tu_2", name="get_time", arguments={})],
        [ToolCallRequested(id="tu_3", name="get_time", arguments={})],
    ]
    runner, bots, talk, events, desks, model = _runner(cfg, script=script)
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "loop forever")

    await runner.run_turn(user_id, bot_id, thread.id)

    messages = await talk.list_messages(user_id, thread.id)
    system_messages = [m for m in messages if m.role == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].body == "I hit my step limit — say continue."
    assert len(model.requests) == 2  # MAX_STEPS calls were made, the 3rd script entry unused


# ---------------------------------------------------------------------------
# Unexpected exception
# ---------------------------------------------------------------------------

async def test_run_turn_wall_clock_timeout_posts_a_took_too_long_message_and_rests(cfg, user_id, bot_id, monkeypatch):
    """Final review, finding 4: a hostile page (or a hung SDK/CLI
    stream) can leave a turn stuck forever -- `_run_steps`'s own
    between-step deadline check never runs if the hang is INSIDE one
    await, not between steps. `TurnRunner.run_turn` wraps the whole
    turn in `asyncio.timeout(MAX_RUN_SECONDS)` as the real backstop
    (the spec's 20-minute wall-time cap), so even a dead-in-the-water
    turn ends, posts something the user can act on, and frees the bot
    (and every message queued behind it) instead of staying `on_it`
    until the gateway itself restarts."""
    import roost.talk.runner as runner_module

    monkeypatch.setattr(runner_module, "MAX_RUN_SECONDS", 0.05)

    class _HangingModel:
        async def stream(self, request):
            await asyncio.sleep(10)
            yield TurnDone("end_turn")  # pragma: no cover -- never reached

    runner, bots, talk, events, desks, model = _runner(cfg, model=_HangingModel())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    await runner.run_turn(user_id, bot_id, thread.id)

    messages = await talk.list_messages(user_id, thread.id)
    system_messages = [m for m in messages if m.role == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].body == "Took too long — say continue."

    bot = await bots.get(user_id, bot_id)
    assert bot.status == BotStatus.RESTING


async def test_an_unreachable_model_says_so_in_plain_words_and_rests(cfg, user_id, bot_id):
    class _OfflineModel:
        def stream(self, request):
            raise ModelUnreachable("API Error: Can't reach the API server (ENOTFOUND)")

    runner, bots, talk, events, desks, model = _runner(cfg, model=_OfflineModel())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    await runner.run_turn(user_id, bot_id, thread.id)

    system_messages = [m for m in await talk.list_messages(user_id, thread.id) if m.role == "system"]
    assert [m.body for m in system_messages] == [
        "I can't reach Claude right now: the internet or Claude's service is down. Send it again in a minute.",
    ]
    assert (await bots.get(user_id, bot_id)).status == BotStatus.RESTING


async def test_unexpected_exception_posts_the_generic_error_message_and_rests(cfg, user_id, bot_id):
    class _BrokenModel:
        def stream(self, request):
            raise RuntimeError("boom")

    runner, bots, talk, events, desks, model = _runner(cfg, model=_BrokenModel())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    await runner.run_turn(user_id, bot_id, thread.id)

    messages = await talk.list_messages(user_id, thread.id)
    system_messages = [m for m in messages if m.role == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].body == "Something went wrong on my side. Please try again."

    bot = await bots.get(user_id, bot_id)
    assert bot.status == BotStatus.RESTING


async def test_unexpected_exception_closes_the_placeholder_and_publishes_the_error_message(
    cfg, user_id, bot_id,
):
    """Fix round 1, finding 4: the pre-announced placeholder ``message``
    frame must be closed with its own ``message_done`` (roost/talk/
    turn.py's new ``except``), and the runner's "something went wrong"
    system message must actually be PUBLISHED, not just stored (roost/
    talk/runner.py's ``_fail_safely``) -- otherwise a live client's bot
    bubble stays blank forever with no explanation until a page reload."""
    class _BrokenModel:
        def stream(self, request):
            raise RuntimeError("boom")

    runner, bots, talk, events, desks, model = _runner(cfg, model=_BrokenModel())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "hello")

    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _drain(sub, 5)
    sub.close()

    assert [f["type"] for f in frames] == [
        "bot_status", "message", "message_done", "message", "bot_status",
    ]
    assert frames[0]["status"] == "on_it"
    placeholder_id = frames[1]["message"]["id"]
    assert frames[1]["message"]["body"] == ""
    # The placeholder opened above is closed as soon as the turn fails --
    # a live client's bot bubble stops showing a loading state right away.
    assert frames[2]["message_id"] == placeholder_id
    # The runner's own error message reaches the client as a real frame.
    assert frames[3]["message"]["role"] == "system"
    assert frames[3]["message"]["body"] == "Something went wrong on my side. Please try again."
    assert frames[4]["status"] == "resting"


class _FailsAfterText:
    """Reads a page, starts its answer, then fails mid-stream."""

    def __init__(self):
        self.calls = 0

    async def stream(self, request):
        self.calls += 1
        if self.calls == 1:
            yield ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "https://example.com"})
            yield TurnDone("tool_use")
            return
        yield TextDelta("It says")
        raise RuntimeError("boom")


async def _frames_until_idle(subscription) -> list[dict]:
    frames: list[dict] = []
    with contextlib.suppress(TimeoutError):
        while True:
            frames.append(await asyncio.wait_for(subscription.__anext__(), timeout=0.2))
    return frames


async def test_a_turn_cut_short_keeps_what_streamed_as_a_stored_reply(cfg, user_id, bot_id):
    """Task 7 fix round 2: a reply cut short (here an error mid-stream) is
    stored under its placeholder's id with a real per-thread ``seq`` and
    the run's taint, and published before ``message_done``."""
    runner, bots, talk, events, desks, model = _runner(cfg, model=_FailsAfterText())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")

    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _frames_until_idle(sub)
    sub.close()

    stored = [(m.role, m.body, m.seq, m.tainted) for m in await talk.list_messages(user_id, thread.id)]
    assert stored == [
        ("user", "open example.com", 1, False),
        ("bot", "It says", 2, True),
        ("system", "Something went wrong on my side. Please try again.", 3, False),
    ]
    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    kept = [i for i, f in enumerate(frames) if f["type"] == "message" and f["message"]["id"] == placeholder_id
            and f["message"]["body"] == "It says"]
    done = [i for i, f in enumerate(frames) if f["type"] == "message_done" and f["message_id"] == placeholder_id]
    assert len(kept) == 1 and frames[kept[0]]["message"]["seq"] == 2
    assert kept[0] < done[0]


async def test_a_cut_short_reply_that_cannot_be_stored_still_closes_the_placeholder(
    cfg, user_id, bot_id, caplog,
):
    """Storing the cut-short text must never mask why the turn ended: a
    failed store is logged, the placeholder still closes, and the runner
    still reports the original error."""
    runner, bots, talk, events, desks, model = _runner(cfg, model=_FailsAfterText())
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")
    add_message = talk.add_message

    async def _bot_rows_fail(user_id, thread_id, role, *args, **kwargs):
        if role == "bot":
            raise RuntimeError("disk full")
        return await add_message(user_id, thread_id, role, *args, **kwargs)

    talk.add_message = _bot_rows_fail
    sub = events.subscribe(user_id)
    await runner.run_turn(user_id, bot_id, thread.id)
    frames = await _frames_until_idle(sub)
    sub.close()

    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    assert any(f["type"] == "message_done" and f["message_id"] == placeholder_id for f in frames)
    assert [m.role for m in await talk.list_messages(user_id, thread.id)] == ["user", "system"]
    assert "Could not store the cut-short reply" in caplog.text


# ---------------------------------------------------------------------------
# TurnRunner.start -- asyncio scheduling
# ---------------------------------------------------------------------------

async def test_run_turn_for_a_deleted_bot_is_a_safe_no_op(cfg, user_id, bot_id):
    runner, bots, talk, events, desks, model = _runner(cfg, script=[])
    thread = await talk.create_thread(user_id, bot_id)
    await bots.delete(user_id, bot_id)

    await runner.run_turn(user_id, bot_id, thread.id)  # must not raise

    assert model.requests == []
    assert await talk.list_messages(user_id, thread.id) == []


async def test_cancel_stops_a_running_drain_task(cfg, user_id, bot_id):
    runner, *_ = _runner(cfg, script=[])
    still_running = asyncio.create_task(asyncio.sleep(10))
    runner._tasks[bot_id] = still_running

    await runner.cancel(bot_id)

    assert bot_id not in runner._tasks
    assert still_running.cancelled()


async def test_cancel_with_nothing_running_is_a_safe_no_op(cfg, user_id, bot_id):
    runner, *_ = _runner(cfg, script=[])
    await runner.cancel(bot_id)  # must not raise


async def test_a_tainted_reply_in_the_thread_taints_the_next_run(cfg, user_id, bot_id):
    """Spec §8.2: a run starts tainted when anything it loads into context
    is — a clean run can't launder an injection by reading it back."""
    runner, bots, talk, events, desks, model = _runner(cfg, script=[
        [ToolCallRequested(id="tu_1", name="open_page", arguments={"url": "https://example.com"})],
        [TextDelta("It says hi."), TurnDone("end_turn")],
        [TextDelta("Still hi."), TurnDone("end_turn")],
    ])
    thread = await talk.create_thread(user_id, bot_id)
    await talk.add_message(user_id, thread.id, "user", "open example.com")
    await runner.run_turn(user_id, bot_id, thread.id)
    await talk.add_message(user_id, thread.id, "user", "and now?")
    await runner.run_turn(user_id, bot_id, thread.id)

    replies = [m for m in await talk.list_messages(user_id, thread.id) if m.role == "bot"]
    assert [(m.body, m.tainted) for m in replies] == [("It says hi.", True), ("Still hi.", True)]
