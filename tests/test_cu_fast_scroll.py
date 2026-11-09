"""Fast pages, slice 6: bigger scrolls (up to 25 notches, 5 by default), a scroll inside one area from the newest
look, the blind-scroll cap unchanged, and a screen prompt that steers to search boxes, read_text, numbers and
text-only looks."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from roost.bots.models import Avatar, Bot, BotStatus
from roost.computer_use.models import ScrollIn
from roost.computer_use.runner import BLIND_SCROLL_TEXT
from roost.computer_use.texts import AREA_OFF_SCREEN_TEXT, NO_AREA_TEXT
from roost.config import load_config
from roost.constants import CU_BLIND_SCROLLS_MAX, CU_SCROLL_MAX_NOTCHES, CU_SCROLL_NOTCHES_PER_INPUT
from roost.db.connection import init_db
from roost.desk.fake_chats import FAKE_CHATS, MESSAGES
from roost.desk.fake_cu import screen_point
from roost.keeper.computer_input import ScrollAction as ScrollInput
from roost.talk.instructions import build_instructions

from cu_run_helpers import make_cu_rig, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def test_scroll_takes_up_to_25_notches_five_by_default_and_one_place():
    assert CU_SCROLL_MAX_NOTCHES == 25 and CU_BLIND_SCROLLS_MAX == 3
    assert ScrollIn.model_validate({"direction": "down"}).amount == 5
    assert ScrollIn.model_validate({"direction": "down", "amount": 25, "area": 2}).area == 2
    for bad in ({"direction": "down", "amount": 26}, {"direction": "down", "area": 1, "at": {"x": 1, "y": 1}}):
        with pytest.raises(ValidationError):
            ScrollIn.model_validate(bad)


async def test_a_scroll_inside_an_area_scrolls_at_its_middle(cfg):
    rig = await make_cu_rig(cfg, "Find it", screen=FAKE_CHATS)
    rig.page.state_name = "chat"
    cu = rig.computer()
    await step(cu, "look", picture=False)
    done = await step(cu, "scroll", direction="up", amount=20, area=2)
    assert "Scrolled up" in done.text and "read_text" in done.text
    x, y = MESSAGES.area.box.center()
    assert rig.desk.inputs[-1][1:] == screen_point(x, y)
    assert (await step(cu, "scroll", direction="up", area=7)).text == NO_AREA_TEXT.format(index=7)


async def test_a_big_scroll_goes_out_in_pieces_the_computer_takes(cfg, monkeypatch):
    """The computer's roost-input takes at most 10 notches per input (no image change): 25 is sent as 10 + 10 + 5."""
    rig = await make_cu_rig(cfg, "Find it", screen=FAKE_CHATS)
    cu = rig.computer()
    sent: list[int] = []
    original = rig.desk.send_input

    async def spy(action, *, held: bool = False):
        if action.verb == "scroll":
            sent.append(action.notches)
        await original(action, held=held)

    monkeypatch.setattr(rig.desk, "send_input", spy)
    await step(cu, "look", picture=False)
    await step(cu, "scroll", direction="down", amount=25)
    assert sent == [10, 10, 5]
    await step(cu, "look", picture=False)
    await step(cu, "scroll", direction="up", amount=12)
    assert sent[3:] == [-10, -2]


def test_one_scroll_input_is_what_the_keeper_and_the_computer_accept():
    image = (Path(__file__).parents[1] / "docker" / "computer" / "roost_input.py").read_text()
    assert re.search(rf"^MAX_NOTCHES = {CU_SCROLL_NOTCHES_PER_INPUT}\b", image, re.M)
    with pytest.raises(ValidationError):
        ScrollInput.model_validate({"verb": "scroll", "x": 1, "y": 1, "notches": CU_SCROLL_NOTCHES_PER_INPUT + 1})


async def test_an_area_out_of_view_is_not_scrolled(cfg, monkeypatch):
    rig = await make_cu_rig(cfg, "Find it", screen=FAKE_CHATS)
    rig.page.state_name = "chat"
    cu = rig.computer()
    original = rig.page.areas

    async def hidden():
        return tuple(replace(a, box=None) for a in await original())

    monkeypatch.setattr(rig.page, "areas", hidden)
    await step(cu, "look", picture=False)
    assert (await step(cu, "scroll", direction="up", area=2)).text == AREA_OFF_SCREEN_TEXT.format(index=2)
    assert rig.desk.inputs == ()


async def test_the_blind_scroll_cap_still_holds_and_points_to_read_text(cfg):
    rig = await make_cu_rig(cfg, "Find it", screen=FAKE_CHATS)
    cu = rig.computer()
    await step(cu, "look", picture=False)
    for _ in range(CU_BLIND_SCROLLS_MAX):
        await step(cu, "scroll", direction="down", amount=25)
    assert (await step(cu, "scroll", direction="down")).text == BLIND_SCROLL_TEXT
    assert "read_text" in BLIND_SCROLL_TEXT


def test_the_screen_prompt_steers_to_search_read_text_numbers_and_text_looks():
    bot = Bot(id="b1", user_id="u1", name="Gela", job="helps", instructions="",
              avatar=Avatar("round", "#22c55e", "none"), template_id=None, status=BotStatus.RESTING,
              model_override=None, created_at="2026-10-26T00:00:00+00:00", updated_at="2026-10-26T00:00:00+00:00",
              computer="linux")
    text = build_instructions(bot)
    for words in ("search box", "read_text", "read_pdf", "number", "picture=false", "instead of scrolling"):
        assert words in text, words
