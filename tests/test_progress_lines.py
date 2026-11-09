"""The bot's words between steps (owner, 2026-11-01 "make it smooth like Grok"; 2026-11-04 "the steps belong
inside that card"): in a run of your own chat, the words before a later step's tool calls go into the activity
pill's steps as a ``note`` (a live ``run_step`` frame carrying the run's taint at that moment), never as their own
chat bubble; they never repeat in the final reply, and a handoff, room or routine run gets none."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.rooms.models import RoomContext
from roost.talk.chat_feel import PROGRESS_RULE, chat_feel_section, on_it_only
from roost.talk.run_steps import RUN_STEP_TYPE
from roost.talk.turn import RunInputs, _progress_lines_allowed
from roost.work.models import ORIGIN_YOU, WorkItem, WorkKind, WorkState
from team_helpers import ask, frames_so_far, make_bot, make_rig, say, send, team_model, wait_idle

ROOM = RoomContext(room_id="r1", name="Saturday", members=(), coordinator_id=None)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _step(text: str, call_id: str, name: str = "list_bots", **arguments) -> list:
    events = [TextDelta(text)] if text else []
    return [*events, ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _bot_rows(rig, user_id, thread_id) -> list[tuple[str, bool]]:
    return [(m.body, m.tainted) for m in await rig.talk.list_messages(user_id, thread_id)
            if m.role == "bot" and m.kind == "text"]


def _notes(frames: list[dict], bot_id: str) -> list[tuple[str, bool]]:
    return [(f["line"], f["tainted"]) for f in frames
            if f["type"] == RUN_STEP_TYPE and f["kind"] == "note" and f["bot_id"] == bot_id]


async def _chat(rig, user_id, bot_id, text):
    sub = rig.events.subscribe(user_id)
    thread = await rig.talk.create_thread(user_id, bot_id)
    await send(rig, user_id, bot_id, thread.id, text)
    await wait_idle(rig.runner, timeout=8)
    frames = await frames_so_far(sub)
    sub.close()
    return thread, frames


async def test_words_between_steps_are_notes_in_the_steps_never_bubbles(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Gigs")
    rig = make_rig(cfg, team_model({"Gigs": [
        _step("On it: a fresh search first.", "c1"),
        _step("Search is done. I'm picking the Acme job because it fits your rate.", "c2"),
        _step("Next I'm opening the apply form.", "c3"),
        say("The proposal is drafted."),
    ]}))
    thread, frames = await _chat(rig, user_id, bot.id, "find me an upwork job and apply")

    assert await _bot_rows(rig, user_id, thread.id) == [
        ("On it: a fresh search first.\n\nThe proposal is drafted.", False),   # one reply, no lines repeated
    ]
    assert _notes(frames, bot.id) == [
        ("Search is done. I'm picking the Acme job because it fits your rate.", False),
        ("Next I'm opening the apply form.", False),
    ]
    run_ids = {f["run_id"] for f in frames if f["type"] == RUN_STEP_TYPE}
    assert len(run_ids) == 1   # the notes sit among the same run's steps


async def test_a_note_carries_the_runs_taint_at_that_moment(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Gigs")
    rig = make_rig(cfg, team_model({"Gigs": [
        _step("On it.", "c1"),
        _step("Opening the page now.", "c2", "open_page", url="https://example.com/"),
        _step("I read the page; next the price.", "c3"),
        say("It costs 3 EUR."),
    ]}))
    thread, frames = await _chat(rig, user_id, bot.id, "what does https://example.com/ sell?")

    assert _notes(frames, bot.id) == [("Opening the page now.", False), ("I read the page; next the price.", True)]
    assert await _bot_rows(rig, user_id, thread.id) == [("On it.\n\nIt costs 3 EUR.", True)]


async def test_blank_words_on_it_lines_and_repeats_add_no_note(cfg, user_id):
    # Owner, 2026-11-04: a bot on a form said "On it: …" before nearly every step.
    bot = await make_bot(cfg, user_id, "Gigs")
    rig = make_rig(cfg, team_model({"Gigs": [
        _step("On it: opening the form.", "c0"), _step("   \n ", "cb"),
        _step("On it: trying the form again.", "c1"),
        _step("On it, filling in the milestones.\n\nThe form had no price box, so I'm loading it again.", "c2"),
        _step("Still searching.", "c3"), _step("Still searching.", "c4"), say("Found it."),
    ]}))
    thread, frames = await _chat(rig, user_id, bot.id, "apply to the job")

    assert _notes(frames, bot.id) == [
        ("The form had no price box, so I'm loading it again.", False), ("Still searching.", False),
    ]
    assert [body for body, _ in await _bot_rows(rig, user_id, thread.id)] == ["On it: opening the form.\n\nFound it."]


async def test_a_handoff_run_keeps_its_words_between_steps_to_itself(cfg, user_id):
    chief = await make_bot(cfg, user_id, "Chief", "leads")
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig = make_rig(cfg, team_model({
        "Chief": [[ask("a1", "Scout", "price a kettle"), TurnDone("tool_use")], say("Scout says 30 EUR.")],
        "Scout": [_step("On it.", "s1"), _step("Found the shop; reading the price.", "s2"), say("30 EUR.")],
    }))
    thread, frames = await _chat(rig, user_id, chief.id, "how much is a kettle?")

    scout_thread = next(t for t in await rig.talk.list_threads(user_id, scout.id) if t.title == "From Chief")
    assert [body for body, _ in await _bot_rows(rig, user_id, scout_thread.id)] == ["On it.\n\n30 EUR."]
    assert [body for body, _ in await _bot_rows(rig, user_id, thread.id)] == ["Scout says 30 EUR."]
    assert _notes(frames, scout.id) == []


def _item(kind: WorkKind, n: int = 0) -> WorkItem:
    return WorkItem(
        id=f"i{n}", user_id="u", bot_id="b", thread_id="t", kind=kind, origin=ORIGIN_YOU, body="hi",
        tainted=False, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r",
        inflight=None, result=None, result_tainted=False, created_at="2026-11-01T10:00:00+00:00",
        updated_at="2026-11-01T10:00:00+00:00",
    )


@pytest.mark.parametrize(("kinds", "room", "expected"), [
    ((), None, False),                                      # a run outside the queue
    ((WorkKind.MESSAGE,), None, True),
    ((WorkKind.CARD_ANSWER,), None, True),                  # carrying on after your Yes or Give it back
    ((WorkKind.MESSAGE, WorkKind.CARD_ANSWER), None, True),
    ((WorkKind.HANDOFF,), None, False),
    ((WorkKind.ROOM_POST,), None, False),
    ((WorkKind.ROUTINE,), None, False),
    ((WorkKind.TRIGGER,), None, False),
    ((WorkKind.MESSAGE,), ROOM, False),
])
def test_notes_come_only_in_runs_of_your_own_chat(kinds, room, expected):
    inputs = RunInputs(items=tuple(_item(kind, n) for n, kind in enumerate(kinds)), room=room)
    assert _progress_lines_allowed(inputs) is expected


def test_the_prompt_asks_for_one_short_line_before_each_stage():
    assert PROGRESS_RULE in chat_feel_section()
    assert "short" in PROGRESS_RULE and "stage" in PROGRESS_RULE


def test_on_it_only_reads_an_opening_line_with_nothing_after_it():
    assert on_it_only("On it: checking the form.") is True
    assert on_it_only("  on it — trying again  ") is True
    assert on_it_only("On it: checking.\n\nFound two jobs.") is False
    assert on_it_only("Search is done.") is False
    assert on_it_only("") is True
