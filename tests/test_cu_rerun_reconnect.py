"""An approved Yes and a silent browser (2026-10-27 incident): "My browser didn't answer, so I didn't touch anything."

Before any input goes out, a dead connection gets one more try (the page is resolved again, the same control and the
same draft still guard it). Once an input went out, nothing is sent again, and the bot never claims it touched
nothing: it says the click or keys went out and that it should look to check."""

from __future__ import annotations

import pytest

from roost.computer_use.texts import BROWSER_SILENT_TEXT, SENT_THEN_SILENT_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.cdp import CdpClientError

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


def _clicks(rig) -> int:
    return sum(1 for verb, *_ in rig.desk.inputs if verb == "click")


def _silent_geometry_once(rig, monkeypatch) -> None:
    real, left = rig.page.geometry, [1]

    async def geometry():
        if left[0] > 0:
            left[0] -= 1
            raise CdpClientError("not connected")
        return await real()

    monkeypatch.setattr(rig.page, "geometry", geometry)


def _silent_after_the_click(rig, monkeypatch) -> None:
    real_send, real_url = rig.desk.send_input, rig.page.url
    clicked = [False]

    async def send_input(action, *, held=False):
        await real_send(action, held=held)
        clicked[0] = clicked[0] or action.verb == "click"

    async def url():
        if clicked[0]:
            raise CdpClientError("connection closed")
        return await real_url()

    monkeypatch.setattr(rig.desk, "send_input", send_input)
    monkeypatch.setattr(rig.page, "url", url)


async def test_a_dead_connection_before_any_input_tries_once_more_and_clicks_once(rig, monkeypatch):
    parked = await _parked(rig)
    _silent_geometry_once(rig, monkeypatch)
    outcome = await rig.computer("card:1").rerun(parked)
    assert outcome.ok, outcome.text
    assert _clicks(rig) == 1


async def test_a_dead_connection_after_the_click_never_clicks_again_and_says_it_was_sent(rig, monkeypatch):
    parked = await _parked(rig)
    _silent_after_the_click(rig, monkeypatch)
    outcome = await rig.computer("card:1").rerun(parked)
    assert _clicks(rig) == 1
    assert outcome.ok is True                      # it ran: the card is not marked failed
    assert outcome.text == SENT_THEN_SILENT_TEXT.format(what="click")
    assert "didn't touch" not in outcome.text


async def test_a_browser_silent_twice_before_any_input_says_nothing_was_touched(rig, monkeypatch):
    parked = await _parked(rig)

    async def geometry():
        raise CdpClientError("not connected")

    monkeypatch.setattr(rig.page, "geometry", geometry)
    outcome = await rig.computer("card:1").rerun(parked)
    assert not outcome.ok
    assert outcome.text == BROWSER_SILENT_TEXT
    assert _clicks(rig) == 0


async def test_a_live_click_whose_browser_goes_silent_after_the_input_says_it_was_sent(rig, monkeypatch):
    cu = rig.computer()
    await step(cu, "look")
    _silent_after_the_click(rig, monkeypatch)
    outcome = await step(cu, "click", target={"text": "Jobs"}, expect="jobs")
    assert _clicks(rig) == 1
    assert outcome.text == SENT_THEN_SILENT_TEXT.format(what="click")
    await cu.close()
