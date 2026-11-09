"""Lessons, §1 L1 and §2 (docs/plans/2026-10-31-roost-lessons.md): the in-memory signal registry, and the screen
loop's two producers. An act that leaves the page as it was is ``expect_missed``; a second Ask card for the same
control is ``asked_again``; a page that moved records nothing. Signals hold the kind, host and class only."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.models import ApprovalDraft
from roost.approvals.store import ApprovalStore
from roost.computer_use.reruns import card_signal_key
from roost.computer_use.runner import ComputerUse, CuRun
from roost.computer_use.runner_lessons import LessonWatch, page_mark, page_moves
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.lessons.constants import LESSON_SIGNAL_RUNS_KEPT, LESSON_SIGNALS_PER_RUN_MAX
from roost.lessons.signals import LessonSignal, LessonSignals

from cu_run_helpers import make_cu_rig, no_sleep, step

_HOST = "shop.example"


# -- the registry ---------------------------------------------------------------------------------------------

def test_the_same_kind_host_and_action_add_to_one_count():
    signals = LessonSignals()
    signals.record("r1", LessonSignal("expect_missed", _HOST, "browsing"))
    signals.record("r1", LessonSignal("expect_missed", _HOST, "browsing"))
    signals.record("r1", LessonSignal("expect_missed", _HOST, "submit"))
    assert signals.take("r1") == (LessonSignal("expect_missed", _HOST, "browsing", 2),
                                  LessonSignal("expect_missed", _HOST, "submit"))


def test_a_run_keeps_at_most_the_cap_of_distinct_signals():
    signals = LessonSignals()
    for n in range(LESSON_SIGNALS_PER_RUN_MAX + 3):
        signals.record("r1", LessonSignal("asked_again", f"h{n}.example", "submit"))
    kept = signals.take("r1")
    assert len(kept) == LESSON_SIGNALS_PER_RUN_MAX
    assert kept[0].host == "h0.example"


def test_take_hands_over_once_and_forgets():
    signals = LessonSignals()
    signals.record("r1", LessonSignal("declined", _HOST, "click"))
    assert signals.take("r1") == (LessonSignal("declined", _HOST, "click"),)
    assert signals.take("r1") == ()
    assert signals.take("never") == ()


def test_the_oldest_run_is_dropped_past_the_runs_kept():
    signals = LessonSignals()
    for n in range(LESSON_SIGNAL_RUNS_KEPT + 1):
        signals.record(f"r{n}", LessonSignal("expect_missed", _HOST, "browsing"))
    assert signals.take("r0") == ()
    assert signals.take("r1") != ()
    assert signals.take(f"r{LESSON_SIGNAL_RUNS_KEPT}") != ()


def test_an_empty_run_id_is_ignored():
    signals = LessonSignals()
    signals.record("", LessonSignal("expect_missed", _HOST, "browsing"))
    assert signals.take("") == ()


# -- the producers --------------------------------------------------------------------------------------------

_CONTROLS = (
    fake_target("field", "Note", 100, 100, width=300, tag="input", input_type="text"),
    fake_target("link", "Jobs", 450, 100, tag="a", link_host=_HOST),
    fake_target("link", "More", 450, 200, tag="a", link_host=_HOST),
    fake_target("button", "Submit proposal", 450, 300, width=160, tag="button"),
)
_PAGE = script([
    ("job", FakeScreenState(url="https://shop.example/job#top", title="Job", targets=_CONTROLS,
                            text="A job post", on_click={"Jobs": "jobs"}, on_type="job")),
    ("jobs", FakeScreenState(url="https://shop.example/jobs", title="Jobs", text="No jobs today")),
])


@pytest.fixture
async def cfg(monkeypatch):
    monkeypatch.setattr("roost.desk.ready.CU_READY_STABLE_MS", 0)
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg, screen=_PAGE)


def _computer(rig, signals, run_id: str = "run-1") -> ComputerUse:
    return ComputerUse(CuRun(rig.cfg, rig.user_id, rig.bot.id, rig.thread_id, run_id), desk=rig.desk,
                       gate=rig.gate, events=rig.events, leases=rig.leases, control=rig.control,
                       announce=rig.announce, sleep=no_sleep, signals=signals)


async def test_a_click_that_leaves_the_page_as_it_was_is_expect_missed(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    done = await step(cu, "click", target={"text": "More"}, expect="the proposal form opens")
    assert "Clicked 'More'" in done.text
    await step(cu, "click", target={"text": "More"}, expect="the proposal form opens")
    assert signals.take("run-1") == (LessonSignal("expect_missed", _HOST, "browsing", 2),)


async def test_a_click_that_moves_the_page_records_nothing(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    await step(cu, "click", target={"text": "Jobs"}, expect="the jobs list shows")
    assert rig.page.state_name == "jobs"
    assert signals.take("run-1") == ()


async def test_look_and_scroll_never_record(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    await step(cu, "scroll", direction="down")
    await step(cu, "look")
    assert signals.take("run-1") == ()


async def test_typing_the_box_holds_records_nothing_and_a_box_that_refuses_is_missed(rig, monkeypatch):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="the note box is focused")
    typed = await step(cu, "type", text="blue wool socks size 42", source={"from": "message"}, expect="saved")
    assert rig.desk._screen_page.pasted_lengths == (23,) and "Typed into 'Note'" in " ".join(rig.lines)
    assert signals.take("run-1") == ()          # focusing a box and typing it holds is no miss

    async def refuses(_node):
        return "x"

    monkeypatch.setattr(rig.page, "box_text", refuses)
    await step(cu, "look")
    await step(cu, "type", text="blue wool socks size 42", source={"from": "message"}, expect="saved")
    (signal,) = signals.take("run-1")
    assert (signal.kind, signal.host) == ("expect_missed", _HOST) and "blue" not in typed.text


async def test_a_key_meant_to_move_the_page_is_checked_and_a_focus_key_is_not(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    await step(cu, "press_key", key="Tab", expect="the next box has focus")
    assert signals.take("run-1") == ()
    await step(cu, "press_key", key="Back", expect="the last page shows")
    (signal,) = signals.take("run-1")
    assert (signal.kind, signal.host) == ("expect_missed", _HOST)


def test_only_clicks_and_moving_keys_compare_the_page():
    assert page_moves("click", {}) and page_moves("press_key", {"key": "Enter"})
    assert not page_moves("press_key", {"key": "Tab"}) and not page_moves("type", {"text": "x"})


async def test_no_registry_records_nothing_and_acts_the_same(rig):
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "click", target={"text": "More"}, expect="the proposal form opens")
    assert "Clicked 'More'" in done.text


async def test_a_registry_that_fails_never_reaches_the_loop(rig, caplog):
    class Broken(LessonSignals):
        def record(self, run_id, signal):
            raise RuntimeError("full")

    cu = _computer(rig, Broken())
    await step(cu, "look")
    done = await step(cu, "click", target={"text": "More"}, expect="the proposal form opens")
    assert "Clicked 'More'" in done.text
    assert "RuntimeError" in caplog.text and "proposal" not in caplog.text


async def test_a_second_card_for_the_same_control_in_one_run_is_asked_again(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    first = await step(cu, "click", target={"text": "Submit proposal"}, expect="it is sent")
    assert first.parked is not None
    assert signals.take("run-1") == ()
    second = await step(cu, "click", target={"text": "Submit proposal"}, expect="it is sent")
    assert second.parked is not None
    assert signals.take("run-1") == (LessonSignal("asked_again", _HOST, "submit"),)


async def test_a_card_of_this_chat_for_the_same_control_makes_the_next_run_asked_again(rig):
    first = _computer(rig, LessonSignals(), "run-1")
    await step(first, "look")
    parked = (await step(first, "click", target={"text": "Submit proposal"}, expect="it is sent")).parked
    await first.close()
    await ApprovalStore(rig.cfg).open(rig.user_id, ApprovalDraft(
        bot_id=rig.bot.id, thread_id=rig.thread_id, work_item_id=None, kind="ask", steps=(parked,),
        request="Submit proposal", tainted=True))
    signals = LessonSignals()
    second = _computer(rig, signals, "run-2")
    await step(second, "look")
    assert (await step(second, "click", target={"text": "Submit proposal"}, expect="sent")).parked is not None
    assert signals.take("run-2") == (LessonSignal("asked_again", _HOST, "submit"),)


async def test_another_controls_card_is_not_asked_again(rig):
    first = _computer(rig, LessonSignals(), "run-1")
    await step(first, "look")
    parked = (await step(first, "click", target={"text": "Submit proposal"}, expect="it is sent")).parked
    await first.close()
    other = replace(parked, act={**parked.act, "url": "https://other.example/"})
    await ApprovalStore(rig.cfg).open(rig.user_id, ApprovalDraft(
        bot_id=rig.bot.id, thread_id=rig.thread_id, work_item_id=None, kind="ask", steps=(other,),
        request="Submit proposal", tainted=True))
    signals = LessonSignals()
    second = _computer(rig, signals, "run-2")
    await step(second, "look")
    assert (await step(second, "click", target={"text": "Submit proposal"}, expect="sent")).parked is not None
    assert signals.take("run-2") == ()


async def test_an_approved_rerun_that_leaves_the_page_is_expect_missed_under_the_cards_key(rig):
    cu = _computer(rig, LessonSignals())
    await step(cu, "look")
    parked = (await step(cu, "click", target={"text": "Submit proposal"}, expect="the form opens")).parked
    await cu.close()
    signals = LessonSignals()
    rerun = _computer(rig, signals, card_signal_key("c1"))
    outcome = await rerun.rerun(parked)
    assert outcome.ok and "Clicked 'Submit proposal'" in outcome.text
    assert signals.take(card_signal_key("c1")) == (LessonSignal("expect_missed", _HOST, "submit"),)


async def test_a_signal_never_holds_page_words_typed_text_or_expect(rig):
    signals = LessonSignals()
    cu = _computer(rig, signals)
    await step(cu, "look")
    await step(cu, "click", target={"text": "More"}, expect="the proposal form opens")
    await step(cu, "click", target={"text": "Submit proposal"}, expect="it is sent")
    await step(cu, "click", target={"text": "Submit proposal"}, expect="it is sent")
    shown = repr(signals.take("run-1"))
    for word in ("More", "Submit proposal", "proposal form", "A job post", "it is sent"):
        assert word not in shown


async def test_the_page_mark_drops_the_fragment_and_a_failing_page_has_none(rig):
    mark = await page_mark(rig.page)
    assert mark is not None and mark[0] == "https://shop.example/job"

    class Gone:
        async def url(self):
            raise RuntimeError("closed")

    assert await page_mark(Gone()) is None
    assert await page_mark(None) is None


def test_the_watch_is_mixed_into_the_loop():
    assert issubclass(ComputerUse, LessonWatch)

