"""The bot works with the whole browser and follows the tab in front (owner request 2026-10-22).

A fake CDP browser holds tabs, each visible or not and focused or not, as a real Brave reports them in an
isolated world (proved on a real ``roost-computer:dev``: ``Target.getTargets`` keeps creation order, newest
first, whichever tab is in front). Nothing starts a browser."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import pytest

from roost.computer_use.fence import SiteFence
from roost.desk.browser import DeskBrowserPage
from roost.desk.browser_guards import BrowserGuards
from roost.desk.cdp import CdpReplyError
from roost.desk.control import ControlLock, ControlMark
from roost.desk.front_tab import FRONT_WORLD, front_tab


@dataclass(frozen=True)
class FakeTab:
    target_id: str
    url: str
    visible: bool = False
    focused: bool = False
    readable: bool = True


class TabBrowser:
    """A browser of tabs in ``Target.getTargets`` order. Each attach gets its own session id."""

    is_open = True                        # a live socket (``CdpClient.is_open``)

    def __init__(self, *tabs: FakeTab, others: tuple[dict, ...] = ()) -> None:
        self.tabs = list(tabs)
        self.others = list(others)
        self.calls: list[tuple[str, dict, str | None]] = []
        self.sessions: dict[str, str] = {}
        self.detached: list[str] = []
        self.listeners: list = []

    async def send(self, method, params=None, session_id=None):
        params = params or {}
        self.calls.append((method, params, session_id))
        if method == "Target.getTargets":
            infos = [{"targetId": t.target_id, "type": "page", "url": t.url, "title": t.target_id} for t in self.tabs]
            return {"result": {"targetInfos": [*infos, *self.others]}}
        if method == "Target.createTarget":
            self.tabs.insert(0, FakeTab("NEW", "about:blank", visible=True, focused=True))
            return {"result": {"targetId": "NEW"}}
        if method == "Target.attachToTarget":
            sid = f"s{len(self.sessions) + 1}-{params['targetId']}"
            self.sessions[sid] = params["targetId"]
            return {"result": {"sessionId": sid}}
        if method == "Target.detachFromTarget":
            self.detached.append(params["sessionId"])
            return {"result": {}}
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "F-" + self.sessions.get(session_id, "BOT")}}}}
        if method == "Page.createIsolatedWorld":
            tab = self._tab(session_id)
            if not tab.readable:
                raise CdpReplyError("Cannot create an isolated world here")
            return {"result": {"executionContextId": 7}}
        if method == "Runtime.evaluate":
            tab = self._tab(session_id)
            return {"result": {"result": {"value": [tab.visible, tab.focused]}}}
        return {"result": {}}

    def _tab(self, session_id):
        return next(t for t in self.tabs if t.target_id == self.sessions[session_id])

    def sent(self, method):
        return [(params, sid) for name, params, sid in self.calls if name == method]

    def show(self, target_id: str) -> None:
        """The owner brings ``target_id`` to the front of the focused window."""
        self.tabs = [replace(t, visible=t.target_id == target_id, focused=t.target_id == target_id) for t in self.tabs]

    def listen(self, methods):
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.append(queue)
        return queue

    def unlisten(self, queue):
        self.listeners = [q for q in self.listeners if q is not queue]


# -- which tab is in front ---------------------------------------------------------------------------------


async def test_the_focused_windows_visible_tab_wins_whatever_the_target_order():
    browser = TabBrowser(
        FakeTab("C", "https://c.example/", visible=True),                 # another window's tab: visible, no focus
        FakeTab("B", "https://b.example/"),
        FakeTab("A", "https://mail.example/", visible=True, focused=True),
    )
    front = await front_tab(browser)
    assert front is not None and front.target_id == "A" and front.url == "https://mail.example/"
    worlds = browser.sent("Page.createIsolatedWorld")
    assert worlds and all(p["worldName"] == FRONT_WORLD for p, _ in worlds)
    assert sorted(browser.detached) == sorted(browser.sessions)          # every probe session is let go


async def test_with_no_focused_window_the_visible_tab_wins_and_unreadable_tabs_count_as_hidden():
    browser = TabBrowser(
        FakeTab("X", "chrome://newtab/", readable=False),
        FakeTab("B", "https://b.example/", visible=True),
        others=({"targetId": "W", "type": "service_worker", "url": "https://b.example/sw.js"},
                {"targetId": "D", "type": "page", "url": "devtools://devtools/inspector.html"}),
    )
    front = await front_tab(browser)
    assert front is not None and front.target_id == "B"
    attached = [p["targetId"] for p, _ in browser.sent("Target.attachToTarget")]
    assert "W" not in attached and "D" not in attached


async def test_no_tab_reads_as_in_front_the_first_listed_one_is_used_and_none_open_is_none():
    browser = TabBrowser(FakeTab("N", "https://n.example/"), FakeTab("O", "https://o.example/"))
    assert (await front_tab(browser)).target_id == "N"
    assert await front_tab(TabBrowser()) is None


# -- the bot's tab is the tab in front ------------------------------------------------------------------------


async def test_the_bot_attaches_to_the_tab_in_front_and_opens_no_new_tab():
    browser = TabBrowser(FakeTab("BOT", "about:blank"), FakeTab("GMAIL", "https://mail.example/", True, True))
    page = DeskBrowserPage(browser)  # type: ignore[arg-type]
    client, session = await page.page_session()
    assert browser.sessions[session] == "GMAIL"
    assert browser.sent("Target.createTarget") == []


async def _no_wait(_seconds: float) -> None:
    return None


async def test_a_tab_is_made_only_when_none_is_open():
    browser = TabBrowser()
    page = DeskBrowserPage(browser, sleep=_no_wait)  # type: ignore[arg-type]
    _, session = await page.page_session()
    assert browser.sessions[session] == "NEW" and len(browser.sent("Target.createTarget")) == 1


async def test_a_brave_that_just_started_gets_a_moment_to_show_its_own_first_tab():
    """D5: Brave starts on the first DevTools bytes, so its window may come a moment after the first listing.
    Making a tab then would leave two: the desk waits for Brave's own tab instead."""
    browser = TabBrowser()
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 2:
            browser.tabs.append(FakeTab("FIRST", "about:blank", visible=True, focused=True))

    page = DeskBrowserPage(browser, sleep=sleep)  # type: ignore[arg-type]
    _, session = await page.page_session()
    assert browser.sessions[session] == "FIRST"
    assert browser.sent("Target.createTarget") == []
    assert len(waits) == 2


async def test_following_the_front_tab_moves_the_session_and_the_armed_guards():
    browser = TabBrowser(FakeTab("BOT", "https://shop.example/", True, True), FakeTab("SIGNIN", "https://id.example/"))
    page = DeskBrowserPage(browser)  # type: ignore[arg-type]
    _, first = await page.page_session()
    guards = await page.guards()
    await guards.arm(SiteFence(frozenset({"shop.example"})))
    assert await page.follow_front_tab() is False                      # still in front: nothing changes
    browser.show("SIGNIN")
    assert await page.follow_front_tab() is True
    _, second = await page.page_session()
    assert browser.sessions[second] == "SIGNIN" and first in browser.detached
    assert [sid for _, sid in browser.sent("Fetch.enable")] == [first, second]
    assert [sid for _, sid in browser.sent("Fetch.disable")] == [first]
    assert guards.armed
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "BOT", "type": "page", "url": "https://shop.example/"}}})
    assert browser.sent("Target.closeTarget") == []                     # tabs open before the switch stay
    await guards.disarm()


async def test_the_address_for_which_account_is_the_front_tabs():
    browser = TabBrowser(FakeTab("NEWEST", "https://ads.example/"), FakeTab("G", "https://accounts.google.com/", True))
    assert await DeskBrowserPage(browser).current_url() == "https://accounts.google.com/"  # type: ignore[arg-type]


# -- the guards leave the owner's hands alone -----------------------------------------------------------------


async def test_while_you_hold_control_your_new_tabs_and_navigations_are_left_alone():
    browser = TabBrowser(FakeTab("BOT", "https://shop.example/", True, True))
    held = {"now": True}
    guards = BrowserGuards(browser, "S", "BOT", hands_off=lambda: held["now"])
    await guards.arm(SiteFence(frozenset({"shop.example"})))
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "YOURS", "type": "page", "url": "https://accounts.google.com/"}}})
    await guards.handle({"method": "Fetch.requestPaused", "sessionId": "S", "params": {
        "requestId": "R1", "request": {"url": "https://accounts.google.com/"}, "frameId": "F-BOT"}})
    assert browser.sent("Target.closeTarget") == [] and browser.sent("Fetch.failRequest") == []
    held["now"] = False                                                  # given back: a page's popup is closed again
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "POP", "type": "page", "url": "https://ads.example/"}}})
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "YOURS", "type": "page", "url": "https://accounts.google.com/"}}})
    assert [p["targetId"] for p, _ in browser.sent("Target.closeTarget")] == ["POP"]
    await guards.disarm()


# -- the desk follows the front tab once you give the computer back ---------------------------------------------


def test_the_control_mark_counts_takes_and_holds():
    lock = ControlLock()
    assert lock.mark("b") == ControlMark(epoch=0, held=False)
    lock.take("b")
    assert lock.mark("b") == ControlMark(epoch=1, held=True)
    lock.give_back("b")
    assert lock.mark("b") == ControlMark(epoch=1, held=False)


class _FollowPage:
    def __init__(self) -> None:
        self.follows = 0
        self.closed = False

    async def follow_front_tab(self) -> bool:
        self.follows += 1
        return True

    async def read_page(self):
        return "page"

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def linux_config(tmp_path):
    from roost.config import RoostConfig

    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "d", desks_dir=tmp_path / "k",
                       keeper_secret="k" * 32)


async def test_the_desk_follows_the_front_tab_after_you_give_it_back(linux_config):
    from roost.desk.client import KeeperDesk

    lock, page = ControlLock(), _FollowPage()

    async def connect(relay_url, token):
        return page

    async def started():
        return {"cdp_token": "t"}

    desk = KeeperDesk(linux_config, "b", computer="linux", connect_page=connect,
                      control_mark=lambda: lock.mark("b"))
    desk._start_browser_session = started
    await desk.read_page()
    assert page.follows == 0                         # a fresh page already starts on the front tab
    lock.take("b")
    await desk.read_page()
    assert page.follows == 0                         # never while you hold it
    lock.give_back("b")
    await desk.read_page()
    await desk.read_page()
    assert page.follows == 1                         # once, after you give it back
    lock.take("b")
    lock.give_back("b")
    await desk.read_page()
    assert page.follows == 2
