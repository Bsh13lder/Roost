"""B1 (owner decision 2026-10-23): ``list_tabs``, ``switch_tab`` and ``close_tab`` for a bot on its Linux computer.

The fake desk's tabs (``roost/desk/fake_tabs.py``): the scripted page is the bot's tab; a test adds others."""

from __future__ import annotations

import pytest

from roost.computer_use import tabs as tab_texts
from roost.computer_use.session import LOOK_FIRST_TEXT
from roost.config import load_config
from roost.constants import CU_FREE_ACT_TOOLS, CU_TOOLS
from roost.db.connection import init_db
from roost.talk.tool_catalog import CATALOG

from cu_run_helpers import make_cu_rig, run_step, step


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def rig(cfg):
    made = await make_cu_rig(cfg)
    made.desk.fake_tabs.add("NEWS", "https://news.example/today", "Today's <b>news</b> & more")
    made.desk.fake_tabs.add("MAIL", "https://mail.example/", "Inbox")
    return made


def test_the_tab_tools_are_screen_tools_and_switch_and_close_are_free():
    assert {"list_tabs", "switch_tab", "close_tab"} <= set(CU_TOOLS)
    assert {"switch_tab", "close_tab"} <= CU_FREE_ACT_TOOLS
    assert CATALOG["list_tabs"].kind == "read"
    assert CATALOG["switch_tab"].kind == "act" and CATALOG["close_tab"].kind == "act"


async def test_list_tabs_numbers_every_tab_marks_the_bots_and_escapes_titles(rig):
    listed = await step(rig.computer(), "list_tabs")
    assert listed.looked                                     # titles are page words: the run is tainted
    assert listed.text.startswith("<untrusted_page") and "&lt;b&gt;news&lt;/b&gt; &amp; more" in listed.text
    assert "1. shop.example (your tab)" in listed.text
    assert "2. news.example" in listed.text and "3. mail.example" in listed.text


async def test_switch_tab_brings_it_up_makes_it_the_bots_and_needs_a_look_before_acting(rig):
    cu = rig.computer()
    await step(cu, "look")
    await step(cu, "list_tabs")
    switched = await step(cu, "switch_tab", index=3)
    assert switched.text == tab_texts.SWITCHED_TEXT.format(index=3, host="mail.example")
    assert rig.desk.fake_tabs.mine == "MAIL"
    clicked = await step(cu, "click", target={"text": "Jobs"}, expect="jobs show")
    assert clicked.text == LOOK_FIRST_TEXT


async def test_a_tab_number_needs_a_listing_and_a_tab_that_is_still_there(rig):
    cu = rig.computer()
    assert (await step(cu, "switch_tab", index=2)).text == tab_texts.LIST_FIRST_TEXT
    await step(cu, "list_tabs")
    rig.desk.fake_tabs.remove("NEWS")                        # the page closed it meanwhile
    assert (await step(cu, "switch_tab", index=2)).text == tab_texts.GONE_TEXT.format(index=2)
    assert (await step(cu, "close_tab", index=9)).text == tab_texts.GONE_TEXT.format(index=9)
    assert rig.desk.fake_tabs.mine == rig.desk.fake_tabs.BOT


async def test_the_tabs_a_run_opened_close_when_it_ends_and_the_older_ones_stay(rig):
    """D5: "spamming tabs and not closing". NEWS and MAIL were open before the run; POP opened during it."""
    cu = rig.computer()
    await step(cu, "look")                                   # the run reaches the browser: its tabs are noted
    rig.desk.fake_tabs.add("POP", "https://shop.example/help", "Help")
    await cu.close()
    left = [v.target_id for v in rig.desk.fake_tabs.views(("", ""))]
    assert left == [rig.desk.fake_tabs.BOT, "NEWS", "MAIL"]


async def test_close_tab_closes_another_tab_and_never_the_last(rig):
    cu = rig.computer()
    await step(cu, "list_tabs")
    closed = await step(cu, "close_tab", index=2)
    assert closed.text == tab_texts.CLOSED_TEXT.format(index=2, host="news.example")
    assert [v.target_id for v in rig.desk.fake_tabs.views(("", ""))] == [rig.desk.fake_tabs.BOT, "MAIL"]
    rig.desk.fake_tabs.remove("MAIL")
    await step(cu, "list_tabs")
    assert (await step(cu, "close_tab", index=1)).text == tab_texts.BLANKED_TEXT
    assert rig.desk.fake_tabs.blanked == 1


async def test_the_tool_runner_lets_switch_and_close_through_without_a_card(rig):
    runner = rig.tool_runner(mode="ask", tainted=True)
    await run_step(runner, "list_tabs")
    result = await run_step(runner, "close_tab", index=3)
    assert result == tab_texts.CLOSED_TEXT.format(index=3, host="mail.example") and runner.parked is None


async def test_a_look_says_a_kept_sign_in_tab_opened(rig):
    cu = rig.computer()
    await step(cu, "look")
    rig.desk.fake_guards.kept = ("https://accounts.google.com/signin",)
    cu.new_step()
    looked = await step(cu, "look")
    assert "A new tab opened: accounts.google.com. Use list_tabs and switch_tab to work in it." in looked.text
