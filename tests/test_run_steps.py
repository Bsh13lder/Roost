"""``run_step`` frames (docs/plans/2026-10-23-roost-activity-pill.md): a run says Thinking, each tool's start and
end in plain words, and Writing the reply; the live snapshot keeps the current run's newest steps."""

from __future__ import annotations

import pytest

from roost.constants import RUN_NOTE_MAX_CHARS, RUN_STEPS_KEPT
from roost.events.hub import LIVE_ONLY_TYPES
from roost.talk.run_steps import RUN_STEP_TYPE, RunSteps, RunStepsLog


class Hub:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def publish(self, user_id: str, event: dict) -> int:
        self.frames.append(event)
        return len(self.frames)


@pytest.fixture
def hub():
    return Hub()


def _steps(hub: Hub) -> RunSteps:
    return RunSteps(hub, user_id="u1", bot_id="b1", thread_id="t1", run_id="r1")


def _summary(frames: list[dict]) -> list[tuple]:
    return [(f["step"], f["kind"], f["state"], f["line"]) for f in frames]


async def test_a_run_thinks_then_steps_then_writes(hub):
    steps = _steps(hub)
    await steps.begin()
    step = await steps.tool_start("web_search", {"query": "WhatsApp Web"})
    await steps.tool_end(step, ok=True)
    step = await steps.tool_start("run_program", {"command": "rm -rf / --key sk-1"})
    await steps.tool_end(step, ok=False)
    await steps.writing()
    await steps.writing()                   # one message step per streak
    await steps.finish()
    assert _summary(hub.frames) == [
        (1, "think", "start", "Thinking"),
        (1, "think", "done", "Thinking"),
        (2, "search", "start", "Searched the web for “WhatsApp Web”"),
        (2, "search", "done", "Searched the web for “WhatsApp Web”"),
        (3, "program", "start", "Ran a program"),
        (3, "program", "failed", "Ran a program"),
        (4, "message", "start", "Writing the reply"),
        (4, "message", "done", "Writing the reply"),
    ]
    frame = hub.frames[0]
    assert set(frame) == {"type", "bot_id", "thread_id", "run_id", "step", "kind", "line", "host", "at", "state"}
    assert frame["type"] == RUN_STEP_TYPE and frame["run_id"] == "r1" and frame["at"].endswith("+00:00")
    assert all("sk-1" not in f["line"] for f in hub.frames)


async def test_a_step_names_its_host(hub):
    steps = _steps(hub)
    step = await steps.tool_start("open_page", {"url": "https://web.whatsapp.com/x?y=1"})
    await steps.tool_end(step, ok=True)
    assert [f["host"] for f in hub.frames] == ["web.whatsapp.com", "web.whatsapp.com"]


async def test_finish_twice_and_writing_after_a_tool_open_a_new_message_step(hub):
    steps = _steps(hub)
    await steps.writing()
    step = await steps.tool_start("look", {})
    await steps.tool_end(step, ok=True)
    await steps.writing()
    await steps.finish()
    await steps.finish()
    assert _summary(hub.frames)[-2:] == [(3, "message", "start", "Writing the reply"),
                                         (3, "message", "done", "Writing the reply")]
    assert _summary(hub.frames)[1] == (1, "message", "done", "Writing the reply")


def test_run_steps_are_live_only():
    assert RUN_STEP_TYPE in LIVE_ONLY_TYPES


def _frame(run: str, step: int, state: str = "start", bot: str = "b1") -> dict:
    return {"type": RUN_STEP_TYPE, "bot_id": bot, "run_id": run, "step": step, "state": state, "line": "x",
            "seq": 9}


def test_the_log_keeps_the_newest_state_per_step_and_drops_a_finished_run():
    log = RunStepsLog()
    log.listen("u1", _frame("r1", 1))
    log.listen("u1", _frame("r1", 1, "done"))
    log.listen("u1", _frame("r1", 2))
    assert [(f["step"], f["state"]) for f in log.for_user("u1")["b1"]] == [(1, "done"), (2, "start")]
    assert "seq" not in log.for_user("u1")["b1"][0]
    log.listen("u1", _frame("r2", 1))                         # a new run starts over
    assert [f["run_id"] for f in log.for_user("u1")["b1"]] == ["r2"]
    log.listen("u1", {"type": "bot_status", "bot_id": "b1", "status": "resting"})
    assert log.for_user("u1") == {}
    assert log.for_user("someone else") == {}


def test_the_log_keeps_a_bounded_ring():
    log = RunStepsLog()
    for n in range(1, RUN_STEPS_KEPT + 6):
        log.listen("u1", _frame("r1", n))
    kept = log.for_user("u1")["b1"]
    assert len(kept) == RUN_STEPS_KEPT and kept[-1]["step"] == RUN_STEPS_KEPT + 5


# ---- notes (owner, 2026-11-04: the bot's words between steps belong in the steps, never as chat bubbles) ----

async def test_a_note_is_its_own_done_step_with_the_runs_taint(hub):
    steps = _steps(hub)
    await steps.begin()
    await steps.note("Search is done. I'm picking the Acme job.", tainted=False)
    step = await steps.tool_start("web_search", {"query": "jobs"})
    await steps.tool_end(step, ok=True)
    await steps.note("On it: reading the job.\n\nThe page asks for a rate.", tainted=True)
    assert _summary(hub.frames) == [
        (1, "think", "start", "Thinking"),
        (1, "think", "done", "Thinking"),
        (2, "note", "done", "Search is done. I'm picking the Acme job."),
        (3, "search", "start", "Searched the web for “jobs”"),
        (3, "search", "done", "Searched the web for “jobs”"),
        (4, "note", "done", "The page asks for a rate."),
    ]
    notes = [f for f in hub.frames if f["kind"] == "note"]
    assert [f["tainted"] for f in notes] == [False, True]
    assert all(f["host"] is None and f["type"] == RUN_STEP_TYPE for f in notes)


async def test_a_blank_an_on_it_only_or_a_repeated_note_adds_nothing(hub):
    steps = _steps(hub)
    await steps.note("   \n ", tainted=False)
    await steps.note("On it: trying the form again.", tainted=False)
    await steps.note("Still on the form.", tainted=False)
    await steps.note("  Still on the form. ", tainted=False)
    assert _summary(hub.frames) == [(1, "note", "done", "Still on the form.")]


async def test_a_long_note_is_trimmed_to_one_line(hub):
    steps = _steps(hub)
    await steps.note("word " * 200 + "\n\nsecond paragraph", tainted=False)
    [frame] = hub.frames
    assert len(frame["line"]) <= RUN_NOTE_MAX_CHARS and "\n" not in frame["line"]
    assert frame["line"].endswith("…")


def test_the_log_keeps_notes_in_the_snapshot():
    log = RunStepsLog()
    log.listen("u1", {"type": RUN_STEP_TYPE, "bot_id": "b1", "run_id": "r1", "step": 1, "kind": "note",
                      "state": "done", "line": "Search is done.", "tainted": False})
    assert log.for_user("u1")["b1"][0]["kind"] == "note"
