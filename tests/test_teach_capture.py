"""Turning one teach intent into a step from the live page: the control under a press, the focused field."""

from __future__ import annotations

from roost.desk.fake_cu import FAKE_GEOMETRY, FakeComputerPage, FakeScreenState, fake_target
from roost.desk.page_targets import CdpPageDriver
from roost.teach.capture import capture
from roost.teach.input import NamedKey, Paste, Press, Typing
from roost.teach.models import TeachStep
from cu_page_helpers import FakeCdp, load_fixture, session_of

TOP = FAKE_GEOMETRY.page_top          # screen y of the page's top edge

SEND = fake_target("button", "Send", 100, 100)
TO = fake_target("field", "To", 100, 200, width=300)
PASSWORD = fake_target("field", "Password", 100, 300, width=300, secret_field=True)
PAGE = FakeScreenState(url="https://mail.example/compose?to=a@b.c", title="Compose", targets=(SEND, TO, PASSWORD))


def _page() -> FakeComputerPage:
    return FakeComputerPage({"compose": PAGE})


async def _focus(page: FakeComputerPage, target) -> None:
    page._focused = target           # the fake keeps focus in memory; the real page reads it from Chromium


async def test_a_press_on_a_button_records_its_kind_label_and_page():
    page = _page()
    step = await capture(page, Press(120, 110 + TOP), FAKE_GEOMETRY)
    assert step == TeachStep(kind="click", host="mail.example", path="/compose", title="Compose", role="button",
                             label="Send")


async def test_a_press_on_nothing_and_a_press_on_the_toolbar():
    page = _page()
    nothing = await capture(page, Press(900, 600 + TOP), FAKE_GEOMETRY)
    assert nothing.kind == "click" and nothing.label == "" and nothing.host == "mail.example"
    toolbar = await capture(page, Press(300, 20), FAKE_GEOMETRY)
    assert toolbar == TeachStep(kind="browser")


async def test_typing_records_the_field_label_never_the_text():
    page = _page()
    await _focus(page, TO)
    step = await capture(page, Typing(), FAKE_GEOMETRY)
    assert step.kind == "type" and step.label == "To" and step.role == "field"


async def test_a_password_field_is_typed_a_password():
    page = _page()
    await _focus(page, PASSWORD)
    step = await capture(page, Typing(), FAKE_GEOMETRY)
    assert step.kind == "password" and step.label == "Password"
    assert (await capture(page, Paste(), FAKE_GEOMETRY)).kind == "password"


async def test_typing_after_the_toolbar_is_the_address_bar():
    page = _page()
    step = await capture(page, Typing(), FAKE_GEOMETRY, address_bar=True)
    assert step == TeachStep(kind="type")
    pasted = await capture(page, Paste(), FAKE_GEOMETRY, address_bar=True)
    assert pasted == TeachStep(kind="paste")


async def test_a_named_key_and_a_paste_with_no_focus():
    page = _page()
    key = await capture(page, NamedKey("Enter"), FAKE_GEOMETRY)
    assert key.kind == "key" and key.key == "Enter" and key.title == "Compose"
    paste = await capture(page, Paste(), FAKE_GEOMETRY)
    assert paste.kind == "paste" and paste.label == ""
    unknown = await capture(page, NamedKey("F5"), FAKE_GEOMETRY)
    assert unknown.kind == "key" and unknown.key == ""


async def test_the_real_driver_reads_the_title_from_history():
    fixture = {**load_fixture("search"), "title": "Search · Example"}
    driver = CdpPageDriver(session_of(FakeCdp(fixture)), None)
    assert await driver.title() == "Search · Example"
    assert await driver.url() == fixture["url"]
