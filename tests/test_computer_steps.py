"""The computer card's steps (docs/plans/2026-10-23-roost-computer-card.md): one ``computer_step`` frame after
each screen tool in a live run, hosts only, no typed text, and an in-memory ring per bot for the snapshot."""

from __future__ import annotations

import pytest

from roost.computer_use.steps import ComputerSteps, step_frame, step_host
from roost.config import load_config
from roost.constants import COMPUTER_KEPT_RUNS_PER_BOT, COMPUTER_STEP_LINE_MAX, COMPUTER_STEPS_KEPT
from roost.db.connection import init_db
from roost.events.hub import LIVE_ONLY_TYPES

from cu_run_helpers import make_cu_rig, run_step, step

_KEYS = {"type", "bot_id", "thread_id", "run_id", "step", "kind", "line", "host", "at"}


def _frame(run_id: str = "r1", step_no: int = 1, bot_id: str = "b1", line: str = "Clicked 'Jobs'") -> dict:
    return step_frame(bot_id=bot_id, thread_id="t1", run_id=run_id, step=step_no, tool="click", line=line,
                      host="shop.example")


def test_a_frame_has_exactly_the_contract_keys():
    frame = _frame()
    assert set(frame) == _KEYS and frame["type"] == "computer_step" and frame["kind"] == "click"
    assert frame["at"].endswith("+00:00")


@pytest.mark.parametrize(("tool", "kind"), [
    ("look", "look"), ("wait_ready", "wait"), ("scroll", "scroll"), ("click", "click"), ("type", "type"),
    ("press_key", "key"), ("open_app", "open_app"), ("open_page", "open_page"), ("list_tabs", "tab"),
    ("switch_tab", "tab"), ("close_tab", "tab"),
])
def test_every_screen_tool_has_its_kind(tool, kind):
    frame = step_frame(bot_id="b", thread_id="t", run_id="r", step=1, tool=tool, line="x", host=None)
    assert frame["kind"] == kind


def test_a_long_line_is_cut():
    assert len(_frame(line="x" * 500)["line"]) == COMPUTER_STEP_LINE_MAX


@pytest.mark.parametrize(("url", "host"), [
    ("https://www.upwork.com/messages/rooms/1?x=2#y", "www.upwork.com"),
    ("http://localhost:8080/a", "localhost"),
    ("about:blank", None), ("", None), ("not a url", None), ("chrome://settings", None),
])
def test_only_a_host_name_is_kept(url, host):
    assert step_host(url) == host


def test_the_ring_keeps_the_current_runs_newest_steps():
    steps = ComputerSteps()
    for n in range(1, COMPUTER_STEPS_KEPT + 6):
        steps.listen("u1", {**_frame(step_no=n), "seq": 9})
    kept = steps.for_user("u1")["b1"]
    assert len(kept) == COMPUTER_STEPS_KEPT and kept[-1]["step"] == COMPUTER_STEPS_KEPT + 5
    assert "seq" not in kept[0]


def test_a_new_run_starts_a_new_ring_and_the_run_ending_clears_it():
    steps = ComputerSteps()
    steps.listen("u1", _frame(run_id="r1"))
    steps.listen("u1", _frame(run_id="r2"))
    assert [f["run_id"] for f in steps.for_user("u1")["b1"]] == ["r2"]
    steps.listen("u1", {"type": "bot_status", "bot_id": "b1", "status": "on_it", "activity": "x"})
    assert steps.for_user("u1")["b1"]
    steps.listen("u1", {"type": "bot_status", "bot_id": "b1", "status": "resting", "activity": None})
    assert steps.for_user("u1") == {}


def test_the_ring_is_per_user():
    steps = ComputerSteps()
    steps.listen("u1", _frame())
    assert steps.for_user("u2") == {}
    steps.listen("u1", {"type": "message", "bot_id": "b1"})          # other frames are ignored
    assert len(steps.for_user("u1")["b1"]) == 1


def _status(state: str) -> dict:
    return {"type": "bot_status", "bot_id": "b1", "status": state, "activity": None}


def _framed(run_id: str, thread_id: str, step_no: int = 1) -> dict:
    return {**_frame(run_id=run_id, step_no=step_no), "thread_id": thread_id}


def test_a_finished_run_is_kept_per_chat_for_the_snapshot():
    steps = ComputerSteps()
    steps.listen("u1", {**_framed("r1", "t1"), "seq": 4})
    steps.listen("u1", _framed("r1", "t1", step_no=2))
    assert steps.kept_for_user("u1") == {}                       # still running: not kept yet
    steps.listen("u1", _status("resting"))
    kept = steps.kept_for_user("u1")["b1"]
    assert [[f["step"] for f in run] for run in kept] == [[1, 2]]
    assert "seq" not in kept[0][0] and steps.for_user("u1") == {}


def test_a_new_run_keeps_the_last_one_and_a_chat_keeps_only_its_newest():
    steps = ComputerSteps()
    steps.listen("u1", _framed("r1", "t1"))
    steps.listen("u1", _framed("r2", "t2"))                      # r1 ended when r2 began
    steps.listen("u1", _status("resting"))
    steps.listen("u1", _framed("r3", "t1"))
    steps.listen("u1", _status("resting"))
    kept = steps.kept_for_user("u1")["b1"]
    assert [run[0]["run_id"] for run in kept] == ["r2", "r3"]   # oldest first, one per chat


def test_kept_runs_are_capped_per_bot():
    steps = ComputerSteps()
    for n in range(COMPUTER_KEPT_RUNS_PER_BOT + 2):
        steps.listen("u1", _framed(f"r{n}", f"t{n}"))
        steps.listen("u1", _status("resting"))
    kept = steps.kept_for_user("u1")["b1"]
    assert len(kept) == COMPUTER_KEPT_RUNS_PER_BOT
    assert kept[-1][0]["run_id"] == f"r{COMPUTER_KEPT_RUNS_PER_BOT + 1}"


def test_kept_runs_are_per_user_and_go_with_a_retired_bot():
    steps = ComputerSteps()
    steps.listen("u1", _framed("r1", "t1"))
    steps.listen("u1", _status("resting"))
    assert steps.kept_for_user("u2") == {}
    steps.listen("u1", _framed("r2", "t2"))
    steps.listen("u1", {"type": "bot_removed", "bot_id": "b1"})
    assert steps.kept_for_user("u1") == {} and steps.for_user("u1") == {}


def test_computer_step_is_live_only():
    assert {"text_delta", "computer_step"} <= LIVE_ONLY_TYPES


@pytest.fixture
async def rig():
    config = load_config()
    await init_db(config)
    return await make_cu_rig(config)


def _steps(rig) -> list[dict]:
    return [frame for _, frame in rig.events.frames if frame.get("type") == "computer_step"]


async def test_a_run_publishes_one_numbered_step_per_screen_tool(rig):
    cu = rig.computer(run_id="run-7")
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    await step(cu, "type", text="blue wool socks size 42", source={"from": "message"}, expect="saved")
    frames = _steps(rig)
    assert [f["step"] for f in frames] == [1, 2, 3]
    assert [f["kind"] for f in frames] == ["look", "click", "type"]
    assert frames[1]["line"] == "Clicked 'Note'" and frames[2]["line"].startswith("Typed into 'Note'")
    for frame in frames:
        assert set(frame) == _KEYS and frame["run_id"] == "run-7" and frame["thread_id"] == rig.thread_id
        assert frame["host"] == "shop.example" and "wool" not in str(frame)


async def test_a_refused_act_publishes_no_step(rig):
    cu = rig.computer()
    await step(cu, "click", target={"text": "Jobs"}, expect="jobs")      # no look first: refused
    assert _steps(rig) == []


async def test_open_page_on_a_linux_computer_is_a_step(rig):
    runner = rig.tool_runner()
    caught: list[dict] = []
    runner._computer._events.add_listener(lambda _user, frame: caught.append(frame))   # the runner's own hub
    await run_step(runner, "open_page", url="https://shop.example/jobs")
    frames = [frame for frame in caught if frame.get("type") == "computer_step"]
    assert frames[0]["line"] == "Opened shop.example"
    assert [f["kind"] for f in frames] == ["open_page"] and frames[0]["host"] == "shop.example"
