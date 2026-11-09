"""A bot wakes its own computer: a screen call on a sleeping computer starts it once and carries on, instead of
asking you to open it (owner, 2026-10-23: "it can't wake up its computer by itself")."""

from __future__ import annotations

import pytest

from roost.computer_use.runner import ASLEEP_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import FrontWindow

from cu_run_helpers import make_cu_rig, step


@pytest.fixture
async def rig():
    config = load_config()
    await init_db(config)
    return await make_cu_rig(config)


async def test_open_app_on_a_sleeping_computer_wakes_it_and_opens_the_app(rig):
    await rig.desk.stop_browser()
    cu = rig.computer()
    opened = await step(cu, "open_app", app="browser")
    assert ASLEEP_TEXT not in opened.text
    assert (await rig.desk.status()).browser == "running"
    assert rig.desk.opened_apps == ("browser",)


async def test_a_look_on_a_sleeping_computer_wakes_it_and_looks(rig):
    await rig.desk.stop_browser()
    rig.desk.script_front(FrontWindow("other"), FrontWindow("other"))
    looked = await step(rig.computer(), "look")
    assert ASLEEP_TEXT not in looked.text
    assert looked.looked


async def test_no_free_computer_says_so_plainly(rig):
    from roost.constants import COMPUTERS_BUSY_TEXT
    await rig.desk.stop_browser()
    rig.desk.force_busy = True
    opened = await step(rig.computer(), "open_app", app="browser")
    assert opened.text == COMPUTERS_BUSY_TEXT
