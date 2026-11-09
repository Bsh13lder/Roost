"""C3 Task 8: the scripted fake page a fake Linux computer serves (tests and the E2E)."""

from __future__ import annotations

import pytest

from roost.desk import ScreenInput
from roost.desk.fake import FakeDesk
from roost.desk.fake_cu import FAKE_GEOMETRY, FakeComputerPage, FakeScreenState, fake_target, screen_point, script

SEARCH = fake_target("field", "Search", 100, 100, 400, 40)
GO = fake_target("button", "Go", 520, 100, 60, 40)
NEWS = fake_target("button", "No thanks", 600, 400, in_dialog="Join our newsletter")
SCRIPT = script([
    ("home", FakeScreenState(url="https://wiki.example/", title="Wiki", targets=(SEARCH, GO),
                             on_click={"Go": "results"}, on_type="typed", on_key={"Enter": "results"})),
    ("typed", FakeScreenState(url="https://wiki.example/", title="Wiki", targets=(SEARCH, GO),
                              on_key={"Enter": "results"})),
    ("results", FakeScreenState(url="https://wiki.example/search?q=roost", title="Results", text="3 results",
                                targets=(GO, NEWS), dialog="Join our newsletter", on_click={"No thanks": "home"})),
])


def _click(x, y) -> ScreenInput:
    sx, sy = screen_point(x, y)
    return ScreenInput(verb="click", x=sx, y=sy, window=FAKE_GEOMETRY.window_rect)


async def test_fake_page_moves_to_the_next_state_on_click():
    page = FakeComputerPage(SCRIPT)
    assert (await page.url()) == "https://wiki.example/"
    await page.apply(_click(550, 120))
    assert page.state_name == "results" and (await page.facts()).text == "3 results"
    await page.apply(_click(10, 10))                      # nothing there: no change
    assert page.state_name == "results"
    await page.apply(_click(650, 415))
    assert page.state_name == "home"


async def test_typing_and_keys_move_the_script_and_keep_only_lengths():
    page = FakeComputerPage(SCRIPT)
    await page.apply(ScreenInput(verb="type", text="secret words"))   # nothing focused: no move
    assert page.state_name == "home"
    await page.apply(_click(300, 120))
    assert (await page.focused()).text == "Search"
    await page.apply(ScreenInput(verb="type", text="kettle"))
    assert page.state_name == "typed" and page.typed_lengths == (12, 6)
    assert "secret words" not in repr(vars(page))            # typed with nothing focused: kept nowhere
    # 2026-10-27: like a real page, the box holds what was typed (box_text reads it back); nothing else keeps it
    assert tuple(page._boxes.values()) == ("kettle",)
    assert "kettle" not in repr({k: v for k, v in vars(page).items() if k != "_boxes"})
    await page.apply(ScreenInput(verb="key", key="Return"))
    assert page.state_name == "results"
    await page.apply(ScreenInput(verb="scroll", x=1, y=200, notches=2))
    assert page.state_name == "results"


async def test_a_dialog_covers_what_is_not_in_it():
    page = FakeComputerPage(SCRIPT)
    await page.apply(_click(550, 120))
    go = await page.find("go", "button", 1)
    assert await page.covering(go) == "Join our newsletter"
    assert await page.covering(await page.find("No thanks", "any", 1)) == ""
    assert (await page.node_at(650, 415)).text == "No thanks"
    assert await page.find("Go", "link", 1) is None


async def test_screenshots_are_real_jpegs_and_the_window_is_restored():
    page = FakeComputerPage(SCRIPT, minimized=True)
    assert (await page.screenshot())[:2] == b"\xff\xd8"
    assert len(await page.screenshot(probe=True)) < len(await page.screenshot())
    assert await page.geometry() == FAKE_GEOMETRY and not page.minimized
    assert (await page.lifecycle()).navigating is False and await page.busy_marks() == 0


def test_a_script_must_lead_somewhere_real():
    with pytest.raises(ValueError):
        FakeComputerPage({})
    with pytest.raises(ValueError):
        FakeComputerPage({"a": FakeScreenState(url="u", title="t", on_click={"x": "nowhere"})})


async def test_a_linux_fake_desk_serves_the_screen_and_its_input_drives_it():
    desk = FakeDesk("b", computer="linux")
    assert desk.page() is None
    page = desk.serve_screen(SCRIPT)
    assert desk.page() is page
    await desk.start_browser()
    await desk.send_input(_click(550, 120))
    assert page.state_name == "results"
    with pytest.raises(ValueError):
        FakeDesk("m").serve_screen(SCRIPT)
