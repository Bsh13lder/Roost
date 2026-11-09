"""The approved re-run brings Brave up first (owner, 2026-10-23): after a fresh computer start Chief's Yes said
"I couldn't bring my browser window up" and did nothing. It now opens the browser when another window is in front,
and tries once more after a ``not_chromium`` refusal, still only on the same control."""

from __future__ import annotations

import pytest

from roost.computer_use.runner import _INPUT_WORDS
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import FrontWindow, InputRefusedByComputer

from cu_run_helpers import make_cu_rig, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    return await make_cu_rig(cfg)


async def _parked(rig):
    cu = rig.computer()
    await step(cu, "look")
    parked = (await step(cu, "click", target={"text": "Buy now"}, expect="paid")).parked
    assert parked is not None
    await cu.close()
    return parked


def _refuse_clicks(rig, monkeypatch, times: int) -> None:
    real, left = rig.desk.send_input, [times]

    async def send_input(action, *, held=False):
        if action.verb == "click" and left[0] > 0:
            left[0] -= 1
            raise InputRefusedByComputer("not_chromium")
        await real(action, held=held)

    monkeypatch.setattr(rig.desk, "send_input", send_input)


def _clicks(rig) -> int:
    return sum(1 for verb, *_ in rig.desk.inputs if verb == "click")


async def test_another_window_in_front_brings_the_browser_up_before_the_approved_click(rig):
    parked = await _parked(rig)
    rig.desk.script_front(FrontWindow("other"))
    outcome = await rig.computer("card:1").rerun(parked)
    assert outcome.ok, outcome.text
    assert rig.desk.opened_apps == ("browser",)
    assert _clicks(rig) == 1


async def test_brave_in_front_opens_nothing(rig):
    parked = await _parked(rig)
    outcome = await rig.computer("card:1").rerun(parked)
    assert outcome.ok, outcome.text
    assert rig.desk.opened_apps == ()


async def test_one_not_chromium_refusal_is_tried_once_more(rig, monkeypatch):
    parked = await _parked(rig)
    _refuse_clicks(rig, monkeypatch, 1)
    outcome = await rig.computer("card:1").rerun(parked)
    assert outcome.ok, outcome.text
    assert rig.desk.opened_apps == ("browser",)
    assert _clicks(rig) == 1


async def test_a_second_refusal_says_so_and_clicks_nothing(rig, monkeypatch):
    parked = await _parked(rig)
    _refuse_clicks(rig, monkeypatch, 2)
    outcome = await rig.computer("card:1").rerun(parked)
    assert not outcome.ok
    assert outcome.text == _INPUT_WORDS["not_chromium"]
    assert _clicks(rig) == 0
