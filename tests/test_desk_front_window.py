"""Full computer, Step 1: a Linux desk asks what is in front, lists Brave's windows, opens apps and sends screen
acts (no window) through the keeper. The keeper's real app runs in-process; nothing starts docker or xdotool."""

from __future__ import annotations

import pytest

from roost.desk import DeskAsleep, DeskUnavailable, FrontWindow, InputRefusedByComputer, ScreenInput
from roost.desk.client import input_body
from roost.desk.fake import FakeDesk
from roost.desk.fake_cu import FakeScreenState, script
from roost.keeper.workspaces import _RunOutcome

from test_desk_send_input import BOT, SECRET_TEXT, _desk
from test_desk_send_input import config, docker, keeper_app, runner  # noqa: F401 - fixtures

SCREEN_CLICK = ScreenInput(verb="click", x=10, y=20, screen=True)


def test_a_screen_body_has_the_flag_and_no_window():
    assert input_body(SCREEN_CLICK, held=False) == {
        "action": {"verb": "click", "x": 10, "y": 20, "count": 1}, "held": False, "screen": True}
    with pytest.raises(ValueError):
        input_body(ScreenInput(verb="click", x=1, y=2), held=False)          # neither a window nor the screen


async def test_front_window_reads_brave_or_other(config, keeper_app, runner):  # noqa: F811
    await keeper_app.state.room.admit(BOT, frozenset())
    desk = _desk(config, keeper_app)
    runner.answer = _RunOutcome(0, b"brave 0 40 1280 760\n", b"", False)
    assert await desk.front_window() == FrontWindow("brave", (0, 40, 1280, 760))
    runner.answer = _RunOutcome(0, b"other\n", b"", False)
    assert await desk.front_window() == FrontWindow("other")
    assert [argv[7:] for argv, _ in runner.calls] == [["front"], ["front"]]


async def test_browser_windows_are_rects(config, keeper_app, runner):  # noqa: F811
    await keeper_app.state.room.admit(BOT, frozenset())
    runner.answer = _RunOutcome(0, b"0 40 1280 760\n-5 0 300 200\n", b"", False)
    assert await _desk(config, keeper_app).browser_windows() == ((0, 40, 1280, 760), (-5, 0, 300, 200))


async def test_open_app_and_its_refusal(config, keeper_app, runner):  # noqa: F811
    await keeper_app.state.room.admit(BOT, frozenset())
    desk = _desk(config, keeper_app)
    await desk.open_app("files")
    assert runner.calls[-1][0][7:] == ["open", "files"]
    runner.answer = _RunOutcome(3, b"", b"no_window\n", False)
    with pytest.raises(InputRefusedByComputer) as caught:
        await desk.open_app("geany")
    assert caught.value.word == "no_window"


async def test_a_screen_act_and_in_browser(config, keeper_app, runner):  # noqa: F811
    await keeper_app.state.room.admit(BOT, frozenset())
    desk = _desk(config, keeper_app)
    await desk.send_input(ScreenInput(verb="type", text=SECRET_TEXT, screen=True))
    assert runner.calls[-1] == ([*runner.calls[-1][0][:7], "type", "--screen"], SECRET_TEXT.encode())
    runner.answer = _RunOutcome(3, b"", b"in_browser\n", False)
    with pytest.raises(InputRefusedByComputer) as caught:
        await desk.send_input(SCREEN_CLICK)
    assert caught.value.word == "in_browser"


async def test_asleep_and_mac_brave(config, keeper_app, runner):  # noqa: F811
    desk = _desk(config, keeper_app)
    with pytest.raises(DeskAsleep):
        await desk.front_window()
    mac = _desk(config, keeper_app, computer="mac_brave")
    for call in (mac.front_window(), mac.browser_windows(), mac.open_app("files")):
        with pytest.raises(DeskUnavailable):
            await call
    assert runner.calls == []


async def test_fake_desk_front_is_brave_with_a_page_else_other_and_can_be_scripted():
    desk = FakeDesk(BOT, computer="linux")
    with pytest.raises(DeskAsleep):
        await desk.front_window()
    await desk.start_browser()
    assert await desk.front_window() == FrontWindow("other")
    assert await desk.browser_windows() == ()
    desk.serve_screen(script([("a", FakeScreenState(url="https://a.example/", title="A"))]))
    front = await desk.front_window()
    assert front.kind == "brave" and front.window is not None
    assert await desk.browser_windows() == (front.window,)
    desk.script_front(FrontWindow("other"))
    assert await desk.front_window() == FrontWindow("other")       # one scripted answer, then back to the page
    assert (await desk.front_window()).kind == "brave"


async def test_fake_desk_opens_apps_and_records_screen_acts_without_text():
    desk = FakeDesk(BOT, computer="linux")
    await desk.start_browser()
    await desk.open_app("terminal")
    await desk.send_input(ScreenInput(verb="type", text=SECRET_TEXT, screen=True))
    await desk.send_input(SCREEN_CLICK)
    assert desk.opened_apps == ("terminal",)
    assert desk.inputs == (("type", 0, 0), ("click", 10, 20))
    assert desk.screen_inputs == 2
    assert "hunter2" not in repr(vars(desk))
    mac = FakeDesk(BOT)
    await mac.start_browser()
    with pytest.raises(DeskUnavailable):
        await mac.front_window()
