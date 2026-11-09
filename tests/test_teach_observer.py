"""The control socket's teach observer: it records only while teaching and never stops the socket."""

from __future__ import annotations

import asyncio
import struct

from roost.desk.fake_cu import FAKE_GEOMETRY, FakeComputerPage, FakeScreenState, fake_target
from roost.desk.rfb import RfbMessage
from roost.teach.models import TeachStep
from roost.teach.observer import TeachObserver

TOP = FAKE_GEOMETRY.page_top
SEND = fake_target("button", "Send", 100, 100)
TO = fake_target("field", "To", 100, 200, width=300)
PAGE = FakeScreenState(url="https://mail.example/compose", title="Compose", targets=(SEND, TO))


class FakeTeach:
    def __init__(self, on: bool = True) -> None:
        self.on = on
        self.steps: list[TeachStep] = []

    def recording(self, bot_id: str) -> bool:
        return self.on

    async def record(self, bot_id: str, step: TeachStep) -> bool:
        self.steps.append(step)
        return True


def pointer(mask: int, x: int, y: int) -> RfbMessage:
    return RfbMessage("pointer", struct.pack(">BBHH", 5, mask, x, y), True)


def key(keysym: int) -> RfbMessage:
    return RfbMessage("key", struct.pack(">BBxxI", 4, 1, keysym), True)


async def _feed(observer, *messages) -> None:
    for message in messages:
        await observer(message)


async def test_clicks_and_typing_become_steps():
    page, teach = FakeComputerPage({"compose": PAGE}), FakeTeach()
    observer = TeachObserver(teach, "b1", page)
    await _feed(observer, pointer(1, 120, 110 + TOP), pointer(0, 120, 110 + TOP))
    page._focused = TO
    await _feed(observer, key(ord("h")), key(ord("i")), key(0xff0d))
    assert [s.kind for s in teach.steps] == ["click", "type", "key"]
    assert teach.steps[0].label == "Send" and teach.steps[1].label == "To" and teach.steps[2].key == "Enter"
    assert page.geometry_calls == 1                # read once per socket


async def test_typing_after_the_toolbar_is_the_address_bar_until_enter():
    page, teach = FakeComputerPage({"compose": PAGE}), FakeTeach()
    observer = TeachObserver(teach, "b1", page)
    await _feed(observer, pointer(1, 300, 10), pointer(0, 300, 10), key(ord("a")), key(0xff0d))
    page._focused = TO
    await _feed(observer, key(ord("b")))
    assert [(s.kind, s.host) for s in teach.steps] == [
        ("browser", ""), ("type", ""), ("key", "mail.example"), ("type", "mail.example")]


async def test_nothing_is_read_while_not_teaching_or_without_a_page():
    page, teach = FakeComputerPage({"compose": PAGE}), FakeTeach(on=False)
    await _feed(TeachObserver(teach, "b1", page), pointer(1, 120, 110 + TOP))
    assert teach.steps == [] and page.geometry_calls == 0
    on = FakeTeach()
    await _feed(TeachObserver(on, "b1", None), pointer(1, 120, 110 + TOP))
    assert on.steps == []


class SlowPage(FakeComputerPage):
    async def node_at(self, x: int, y: int):
        await asyncio.sleep(5)


class BrokenPage(FakeComputerPage):
    async def geometry(self):
        raise RuntimeError("cdp gone")


async def test_a_slow_or_broken_page_records_nothing_and_never_raises(monkeypatch):
    monkeypatch.setattr("roost.teach.observer.TEACH_CAPTURE_TIMEOUT_S", 0.01)
    teach = FakeTeach()
    await _feed(TeachObserver(teach, "b1", SlowPage({"compose": PAGE})), pointer(1, 120, 110 + TOP))
    await _feed(TeachObserver(teach, "b1", BrokenPage({"compose": PAGE})), pointer(1, 120, 110 + TOP))
    assert teach.steps == []
