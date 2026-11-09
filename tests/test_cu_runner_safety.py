"""C3 security review (a) after Task 12: Take control stops an act right up to the send, a key or typing is
re-checked against the focused control before it is sent, contact and secret flags are judged on all the text
typed into one field in the run, and every refusal of an act writes one audit row."""

from __future__ import annotations

import json

import pytest

from roost.computer_use.refusal_keys import refusal_key
from roost.computer_use.runner import FOCUS_MOVED_TEXT, HELD_TEXT
from roost.computer_use.texts import COVERED_TEXT, MISS_TEXT, STALE_MARK_TEXT
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.computer_use.session import BUSY_TEXT, LOOK_FIRST_TEXT
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk.fake_cu import FakeScreenState, fake_target, script
from roost.talk.instructions import CONTROL_HELD_TEXT

from cu_run_helpers import make_cu_rig, run_step, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


async def _audit(cfg, user_id: str) -> list[tuple[str, str, str]]:
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT action, decision, reason FROM audit WHERE user_id = ? ORDER BY id", (user_id,))).fetchall()
    return [(row["action"], row["decision"], row["reason"]) for row in rows]


def _take_during_ready(cu, rig, *, give_back: bool = False):
    async def ready(*_args, **_kwargs) -> str:
        rig.control.take(rig.bot.id)
        if give_back:
            rig.control.give_back(rig.bot.id)
        return "ready"
    return ready


# -- Take control during an act -----------------------------------------------------------------------------

async def test_take_control_while_the_page_settles_stops_the_click(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    monkeypatch.setattr(cu, "_ready", _take_during_ready(cu, rig))
    done = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert done.text == HELD_TEXT
    assert rig.desk.inputs == () and rig.page.state_name == "shop"


async def test_take_and_give_back_while_the_page_settles_still_stops_the_click(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    monkeypatch.setattr(cu, "_ready", _take_during_ready(cu, rig, give_back=True))
    done = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert done.text == HELD_TEXT and rig.desk.inputs == ()


async def test_take_control_while_the_page_settles_stops_approved_typing(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    monkeypatch.setattr(cu, "_ready", _take_during_ready(cu, rig))
    done = await step(cu, "type", text="blue wool socks", source={"from": "message"}, expect="saved")
    assert done.text == HELD_TEXT and rig.desk._screen_page.pasted_lengths == ()


async def test_every_input_tells_the_keeper_whether_you_hold_the_computer(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    held = {"now": None}
    real_decide = rig.gate.decide

    async def decide(*args, **kwargs):
        verdict = await real_decide(*args, **kwargs)
        held["now"] = object()            # you hold it from here on, with no new epoch: only the keeper can tell
        return verdict

    monkeypatch.setattr(rig.gate, "decide", decide)
    monkeypatch.setattr(rig.control, "held", lambda bot_id: held["now"])
    done = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert done.text == HELD_TEXT and rig.desk.inputs == ()


# -- focus re-checked before a key or typing ---------------------------------------------------------------

def _focus_moves_to(rig, monkeypatch, target) -> None:
    real = rig.page.focused
    calls = {"n": 0}

    async def focused():
        calls["n"] += 1
        return await real() if calls["n"] == 1 else target

    monkeypatch.setattr(rig.page, "focused", focused)


async def test_a_key_is_not_pressed_when_focus_moved_after_the_verdict(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    await step(cu, "look")
    buy = next(t for t in rig.page.state.targets if t.text == "Buy now")
    _focus_moves_to(rig, monkeypatch, buy)
    done = await step(cu, "press_key", key="Tab", expect="next field")
    assert done.text == FOCUS_MOVED_TEXT
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click"]   # only the earlier click


async def test_approved_typing_is_not_sent_when_focus_moved_to_another_box(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Note"}, expect="focused")
    other = fake_target("field", "Shipping address", 100, 500, width=300, tag="input", input_type="text")
    _focus_moves_to(rig, monkeypatch, other)
    done = await step(cu, "type", text="blue wool socks", source={"from": "message"}, expect="saved")
    assert done.text == FOCUS_MOVED_TEXT and rig.desk._screen_page.pasted_lengths == ()


# -- contact and secret on the field's whole text ---------------------------------------------------------

_CHAT = script([
    ("chat", FakeScreenState(url="https://shop.example/help", title="Help",
                             targets=(fake_target("field", "Message", 100, 100, width=400, tag="textarea"),
                                      fake_target("button", "Send", 520, 100, tag="button")))),
])


async def test_a_phone_number_typed_in_pieces_still_asks(cfg):
    rig = await make_cu_rig(cfg, "Ask them to call my office please")   # a number you never gave the bot
    rig.desk.serve_screen(_CHAT)
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Message"}, expect="focused")
    first = await step(cu, "type", text="612 345", source={"from": "message"}, expect="typed")
    assert first.parked is None and rig.desk._screen_page.pasted_lengths == (7,)
    await step(cu, "look")
    second = await step(cu, "type", text="678", source={"from": "message"}, expect="typed")
    assert second.parked is not None and second.parked.floor == "contact"
    assert rig.desk._screen_page.pasted_lengths == (7,)


async def test_pieces_in_different_fields_are_judged_apart(cfg):
    two = script([
        ("form", FakeScreenState(url="https://shop.example/f", title="F", targets=(
            fake_target("field", "Street", 100, 100, width=300, tag="input", input_type="text"),
            fake_target("field", "Flat", 100, 200, width=300, tag="input", input_type="text"),
        ))),
    ])
    rig = await make_cu_rig(cfg, "Street 612 345 and flat 678")
    rig.desk.serve_screen(two)
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Street"}, expect="focused")
    assert (await step(cu, "type", text="612 345", source={"from": "message"}, expect="t")).parked is None
    await step(cu, "look")
    await step(cu, "click", target={"text": "Flat"}, expect="focused")
    assert (await step(cu, "type", text="678", source={"from": "message"}, expect="t")).parked is None
    assert rig.desk._screen_page.pasted_lengths == (7, 3)


# -- one audit row per act decision ------------------------------------------------------------------------

async def test_a_look_first_refusal_writes_one_never_row(rig, cfg):
    cu = rig.computer()
    assert (await step(cu, "click", target={"text": "Jobs"}, expect="jobs")).text == LOOK_FIRST_TEXT
    assert await _audit(cfg, rig.user_id) == [("click", "never", "loop_refused")]


async def test_a_busy_computer_refusal_writes_one_never_row(rig, cfg):
    rig.leases.acquire(rig.bot.id, "another-run")
    cu = rig.computer()
    assert (await step(cu, "click", target={"text": "Jobs"}, expect="jobs")).text == BUSY_TEXT
    assert await _audit(cfg, rig.user_id) == [("click", "never", "loop_refused")]


async def test_a_miss_writes_one_never_row(rig, cfg):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Nothing like this"}, expect="x")
    assert await _audit(cfg, rig.user_id) == [("click", "never", "loop_refused")]


async def test_a_gated_act_still_writes_exactly_one_row(rig, cfg):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert await _audit(cfg, rig.user_id) == [("click", "do", "allowed")]


async def test_a_held_refusal_after_the_verdict_adds_no_second_row(rig, cfg, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    monkeypatch.setattr(cu, "_ready", _take_during_ready(cu, rig))
    await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert await _audit(cfg, rig.user_id) == [("click", "never", "loop_refused")]


async def test_holding_the_computer_writes_a_never_row_for_an_act(rig, cfg):
    runner = rig.tool_runner()
    await run_step(runner, "look")
    rig.control.take(rig.bot.id)
    assert await run_step(runner, "click", target={"text": "Jobs"}, expect="jobs") == CONTROL_HELD_TEXT
    rows = await _audit(cfg, rig.user_id)
    assert rows[-1] == ("click", "never", "loop_refused")
    assert [r for r in rows if r[0] == "click"] == [("click", "never", "loop_refused")]


# -- why an act was refused (owner, 2026-11-04: the logs said loop_refused and nothing more) ----------------

async def _refused_keys(cfg, user_id: str) -> list[str]:
    dek = await get_user_dek(cfg, user_id)
    async with db_session(cfg) as db:
        rows = await (await db.execute("SELECT detail FROM audit WHERE user_id = ? AND reason = 'loop_refused' "
                                       "ORDER BY id", (user_id,))).fetchall()
    return [json.loads(decrypt(r["detail"], dek, user_aad(user_id, "audit:detail"))).get("refused", "")
            for r in rows]


async def test_a_refused_act_names_why_in_its_audit_row(rig, cfg, monkeypatch):
    cu = rig.computer()
    await step(cu, "click", target={"text": "Jobs"}, expect="jobs")                   # no look yet
    await step(cu, "look")
    await step(cu, "click", target={"text": "Nothing like this"}, expect="x")          # a miss
    monkeypatch.setattr(cu, "_ready", _take_during_ready(cu, rig))
    await step(cu, "look")
    await step(cu, "click", target={"text": "Jobs"}, expect="jobs")                    # you took it
    assert await _refused_keys(cfg, rig.user_id) == ["look_first", "miss", "held"]


async def test_holding_the_computer_names_held_in_the_row(rig, cfg):
    runner = rig.tool_runner()
    await run_step(runner, "look")
    rig.control.take(rig.bot.id)
    await run_step(runner, "click", target={"text": "Jobs"}, expect="jobs")
    assert await _refused_keys(cfg, rig.user_id) == ["held"]


def test_every_refusal_text_has_its_own_key():
    assert refusal_key(COVERED_TEXT.format(label="'Yes'", dialog="Terms", how="")) == "covered"
    assert refusal_key(MISS_TEXT.format(aim="'Apply'")) == "miss"
    assert refusal_key(STALE_MARK_TEXT.format(index=4)) == "stale_mark"
    assert refusal_key(LOOK_FIRST_TEXT) == "look_first" and refusal_key(BUSY_TEXT) == "busy"
    assert refusal_key("Some words nobody wrote") == "other"


async def test_take_control_while_an_approved_click_waits_stops_it(rig, cfg, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    parked = (await step(cu, "click", target={"text": "Buy now"}, expect="paid")).parked
    assert parked is not None
    await cu.close()
    yes = rig.computer("card:1")
    monkeypatch.setattr(yes, "_ready", _take_during_ready(yes, rig))
    outcome = await yes.rerun(parked)
    assert not outcome.ok and outcome.text == HELD_TEXT
    assert rig.desk.inputs == () and rig.page.state_name == "shop"
    assert (await _audit(cfg, rig.user_id))[-1] == ("click", "never", "loop_refused")
