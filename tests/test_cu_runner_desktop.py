"""Full computer, Step 1: the runner asks what is in front before every look and act. Brave in front: today's
page loop, unchanged. Anything else: a whole-screen look with Brave blacked out, free acts anywhere but in Brave,
and open_app. The front is faked; nothing reaches a real computer."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from roost.apps.store import AppStore
from roost.computer_use import desktop
from roost.constants import CU_TRIES_PER_TARGET
from roost.computer_use.runner import ComputerUse, CuRun
from roost.computer_use.session import LOOK_FIRST_TEXT, ONE_ACTION_TEXT
from roost.config import load_config
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.desk import FrontWindow
from roost.desk.fake import FakeDesk
from roost.llm.types import SCREENSHOT_SHOWN
from roost.talk.instructions import CONTROL_HELD_TEXT

from cu_run_helpers import make_cu_rig, no_sleep, run_step, step

OTHER = FrontWindow("other")
SECRET_WORDS = "please send me a free sample"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    made = await make_cu_rig(cfg)
    made.desk.visible_browsers = ((0, 0, 400, 300),)      # Brave sits in the top-left corner, under another app
    return made


def _desktop(rig, steps: int = 4) -> None:
    rig.desk.script_front(*(OTHER,) * steps)


async def test_a_desktop_look_shows_the_whole_screen_with_brave_black_and_no_page_text(rig):
    _desktop(rig)
    cu = rig.computer()
    looked = await step(cu, "look")
    assert looked.looked and SCREENSHOT_SHOWN in looked.text
    assert "screen: desktop" in looked.text and "front window: another app" in looked.text
    assert "browser windows blacked out: 1" in looked.text
    assert "Socks for sale" not in looked.text and "shop.example" not in looked.text
    assert rig.page.geometry_calls == 0                     # Brave was never brought to the front
    with Image.open(io.BytesIO(cu.newest_image())) as shown:
        assert shown.format == "JPEG" and shown.convert("RGB").getpixel((10, 10)) == (0, 0, 0)
    assert rig.desk.screens and rig.desk.screens[-1].received_input == 0
    assert "Looked at the screen" in rig.lines


async def test_brave_in_front_keeps_today_s_look(rig):
    cu = rig.computer()
    looked = await step(cu, "look")
    assert "Socks for sale" in looked.text and rig.page.geometry_calls == 1
    assert "screen: desktop" not in looked.text


async def test_a_screen_click_lands_anywhere_but_brave_and_needs_no_card(rig):
    _desktop(rig)
    cu = rig.computer()
    await step(cu, "look")
    done = await step(cu, "click", x=600, y=500, expect="the terminal is focused")
    assert done.parked is None and "Clicked the screen" in done.text
    assert rig.desk.inputs == (("move", 600, 500), ("click", 600, 500)) and rig.desk.screen_inputs == 2
    assert rig.page.state_name == "shop"
    assert [p["kind"] for p in rig.events.pointers()] == ["click"]


async def test_screen_acts_keep_the_look_first_and_one_action_rules(rig):
    _desktop(rig, 6 + 3 * (CU_TRIES_PER_TARGET - 2))
    cu = rig.computer()
    assert (await step(cu, "click", x=600, y=500, expect="x")).text == LOOK_FIRST_TEXT
    await step(cu, "look")
    cu.new_step()
    from cu_run_helpers import call, ctx

    await cu.handle(call("click", x=600, y=500, expect="x"), ctx())
    assert (await cu.handle(call("press_key", key="Enter", expect="x"), ctx())).text == ONE_ACTION_TEXT
    assert len(rig.desk.inputs) == 2


async def test_words_are_no_aim_on_the_desktop(rig):
    _desktop(rig)
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "click", target={"text": "Buy now"}, expect="x")
    assert refused.text == desktop.TARGET_TEXT and rig.desk.inputs == ()


async def test_typing_on_the_desktop_is_free_and_never_shown(rig, cfg):
    _desktop(rig)
    cu = rig.computer()
    await step(cu, "look")
    typed = await step(cu, "type", text=SECRET_WORDS, source={"from": "message"}, expect="the words show")
    assert typed.parked is None and rig.desk.typed_lengths == (len(SECRET_WORDS),)
    assert SECRET_WORDS not in typed.text and all(SECRET_WORDS not in line for line in rig.lines)
    assert f"Typed on the screen ({len(SECRET_WORDS)} characters)" in rig.lines
    dek = await get_user_dek(cfg, rig.user_id)
    async with db_session(cfg) as db:
        rows = await (await db.execute("SELECT decision, detail FROM audit WHERE user_id = ? AND action = 'type'",
                                       (rig.user_id,))).fetchall()
    details = [json.loads(decrypt(r["detail"], dek, user_aad(rig.user_id, "audit:detail"))) for r in rows]
    assert [r["decision"] for r in rows] == ["do"] and details[0]["space"] == "screen"
    assert SECRET_WORDS not in json.dumps(details)


async def test_line_breaks_are_never_typed_on_the_desktop(rig):
    """Owner, 2026-11-01: only a page takes a paste; another app gets keys, where a line break would press Enter."""
    _desktop(rig)
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "type", text="one\ntwo", expect="the words show")
    assert refused.text == desktop.LINE_BREAKS_TEXT and rig.desk.inputs == ()


async def test_a_point_on_brave_is_refused_and_twice_is_stuck(rig):
    _desktop(rig, 6 + 3 * (CU_TRIES_PER_TARGET - 2))
    cu = rig.computer()
    await step(cu, "look")
    first = await step(cu, "click", x=100, y=100, expect="x")
    assert first.text == desktop.IN_BROWSER_TEXT and first.block is None
    for _ in range(CU_TRIES_PER_TARGET - 2):          # owner, 2026-11-03: four tries in all
        await step(cu, "look")
        assert (await step(cu, "click", x=100, y=100, expect="x")).block is None
    await step(cu, "look")
    second = await step(cu, "click", x=100, y=100, expect="x")
    assert second.block is not None and second.block.note == desktop.IN_BROWSER_NOTE
    assert rig.desk.inputs == ()


async def test_open_app_opens_a_fixed_app_without_a_look(rig):
    cu = rig.computer()
    opened = await step(cu, "open_app", app="files", why="find the report")
    assert opened.text.startswith("Opened Files") and rig.desk.opened_apps == ("files",)
    assert "Opened Files" in rig.lines
    assert (await step(cu, "click", x=600, y=500, expect="x")).text == LOOK_FIRST_TEXT


async def test_open_app_takes_only_an_installed_package(rig, cfg):
    cu = rig.computer()
    refused = await step(cu, "open_app", app="geany")
    assert refused.text == desktop.NOT_INSTALLED_TEXT.format(app="geany") and rig.desk.opened_apps == ()
    await AppStore(cfg).add(rig.user_id, rig.bot.id, "geany", tainted=False)
    assert (await step(cu, "open_app", app="geany")).text.startswith("Opened geany")
    assert "Opened geany" in rig.lines and rig.desk.opened_apps == ("geany",)
    assert "Refused" in (await step(cu, "open_app", app="Geany; rm")).text


async def test_open_app_runs_through_the_gate_and_stops_while_you_hold_control(rig):
    runner = rig.tool_runner()
    assert (await run_step(runner, "open_app", app="terminal")).startswith("Opened Terminal")
    rig.control.take(rig.bot.id)
    assert await run_step(runner, "open_app", app="terminal") == CONTROL_HELD_TEXT
    assert rig.desk.opened_apps == ("terminal",)


async def test_look_and_open_app_work_with_brave_closed(rig):
    closed = FakeDesk(rig.bot.id, computer="linux")
    await closed.start_browser()                            # the computer runs; no page is served
    cu = ComputerUse(CuRun(rig.cfg, rig.user_id, rig.bot.id, rig.thread_id, "run-9"), desk=closed, gate=rig.gate,
                     events=rig.events, leases=rig.leases, control=rig.control, announce=rig.announce,
                     sleep=no_sleep)
    looked = await step(cu, "look")
    assert looked.looked and "screen: desktop" in looked.text and "blacked out" not in looked.text
    assert (await step(cu, "open_app", app="browser")).text.startswith("Opened the browser")
    assert not closed.guards_armed
    await cu.close()


async def test_desktop_wait_and_scroll(rig):
    _desktop(rig)
    cu = rig.computer()
    assert (await step(cu, "wait_ready")).text == desktop.WAITED_TEXT
    scrolled = await step(cu, "scroll", direction="down", amount=2, at={"x": 1280, "y": 700})
    assert scrolled.text.startswith("Scrolled down")
    assert rig.desk.inputs == (("scroll", 1279, 700),)


async def test_a_point_off_the_screen_and_a_key_on_the_desktop(rig):
    _desktop(rig, 6 + 3 * (CU_TRIES_PER_TARGET - 2))
    cu = rig.computer()
    await step(cu, "look")
    assert (await step(cu, "click", x=1280, y=10, expect="x")).text == desktop.OUTSIDE_SCREEN_TEXT
    pressed = await step(cu, "press_key", key="Enter", expect="the command runs")
    assert pressed.text.startswith("Pressed Enter") and rig.desk.inputs == (("key", 0, 0),)


async def test_an_app_with_no_window_says_so(rig, cfg):
    await AppStore(cfg).add(rig.user_id, rig.bot.id, "fonts-noto", tainted=False)
    rig.desk.no_window_apps = ("fonts-noto",)
    opened = await step(rig.computer(), "open_app", app="fonts-noto")
    assert opened.text == desktop.NO_WINDOW_TEXT.format(app="fonts-noto") and rig.desk.opened_apps == ()


async def test_page_numbers_areas_and_reads_are_refused_on_the_desktop(rig):
    """Fast pages: a look's numbers and areas name page controls, never the desktop's; there is no page to read."""
    _desktop(rig, steps=6)
    cu = rig.computer()
    await step(cu, "look")
    assert (await step(cu, "click", index=1, expect="x")).text == desktop.TARGET_TEXT
    assert (await step(cu, "type", index=1, text="hello", expect="x")).text == desktop.TARGET_TEXT
    assert (await step(cu, "scroll", direction="down", area=1)).text == desktop.TARGET_TEXT
    read = await step(cu, "read_text")
    assert "open_app browser" in read.text and not read.looked
    assert "open_app browser" in (await step(cu, "read_pdf")).text
    assert rig.desk.inputs == ()
