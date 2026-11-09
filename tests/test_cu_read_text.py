"""Fast pages, slice 3: read_text reads the page's or one area's text (scrolled-out text included) as escaped,
untrusted text that taints the run, within a budget and with a cursor, instead of dozens of scrolls."""

from __future__ import annotations

import html

import pytest

from roost.computer_use.read_text import find_lines, text_window
from roost.computer_use.texts import NO_AREA_TEXT, STALE_AREA_TEXT
from roost.config import load_config
from roost.constants import CU_READ_TEXT_CHARS
from roost.db.connection import init_db
from roost.desk.fake_chats import APPOINTMENT_LINE, FAKE_CHATS

from cu_run_helpers import make_cu_rig, run_step, step

MESSAGE = "Find my appointment with Francis on WhatsApp"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    rig = await make_cu_rig(cfg, MESSAGE, screen=FAKE_CHATS)
    rig.page.state_name = "chat"
    return rig


# -- the pure parts ---------------------------------------------------------------------------------------------


def test_a_window_ends_on_a_line_and_says_where_to_go_on():
    text = "\n".join(f"line {n}" for n in range(100))
    chunk, end = text_window(text, 0, 50)
    assert chunk.endswith("line 6") and end == len(chunk) + 1
    rest, last = text_window(text, end, 10_000)
    assert rest.startswith("line 7") and last == len(text)
    assert text_window(text, len(text) + 5, 50) == ("", len(text))


def test_find_shows_each_hit_with_its_neighbours_case_and_accents_aside():
    text = "a\nb\nCita en la Clínica\nc\nd\ne\nf\nanother clinica line"
    found = find_lines(text, "clinica", context=1, limit=5)
    assert found == ["b", "Cita en la Clínica", "c", "…", "f", "another clinica line"]
    assert find_lines(text, "nowhere", context=1, limit=5) == []


# -- in the loop -----------------------------------------------------------------------------------------------


async def test_look_lists_the_areas_read_text_can_read(rig):
    cu = rig.computer()
    looked = html.unescape((await step(cu, "look", picture=False)).text)
    assert 'area 1: grid "Chat list"' in looked and 'area 2: application "Messages"' in looked


async def test_read_text_of_an_area_reads_text_far_out_of_view_and_taints(rig):
    runner = rig.tool_runner(tainted=False)
    await run_step(runner, "look", picture=False)
    runner.tainted = False
    first = await run_step(runner, "read_text", area=2)
    assert runner.tainted and first.startswith("<untrusted_page") and "characters 0–" in first
    assert "Francis: reminder 0," in first and "Contact 3" not in first and len(first) < CU_READ_TEXT_CHARS + 600
    assert "read_text area=2 start=" in first
    found = await run_step(runner, "read_text", area=2, find="appointment")
    assert html.escape(APPOINTMENT_LINE, quote=True) in found


async def test_read_text_of_the_whole_page_needs_no_area(rig):
    cu = rig.computer()
    await step(cu, "look", picture=False)
    whole = await step(cu, "read_text", find="Thursday 14 November")
    assert whole.looked and "Thursday 14 November" in whole.text


async def test_read_text_never_moves_the_screen(rig):
    cu = rig.computer()
    await step(cu, "look", picture=False)
    await step(cu, "read_text", area=1)
    assert rig.desk.inputs == ()
    done = await step(cu, "click", index=2, expect="the chat opens")    # the look's numbers still hold
    assert "Clicked 'Francis Dentist'" in done.text


async def test_an_area_the_look_did_not_list_or_that_is_gone_is_refused(rig):
    cu = rig.computer()
    await step(cu, "look", picture=False)
    assert (await step(cu, "read_text", area=7)).text == NO_AREA_TEXT.format(index=7)
    rig.page.state_name = "home"                                         # the messages pane is gone
    assert (await step(cu, "read_text", area=2)).text == STALE_AREA_TEXT.format(index=2)
