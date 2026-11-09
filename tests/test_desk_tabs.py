"""B1 (owner decision 2026-10-23): the bot sees, switches and closes its browser's tabs.

The same fake CDP browser as ``tests/test_front_tab.py``, plus ``Target.activateTarget`` and
``Target.closeTarget``. Nothing starts a browser."""

from __future__ import annotations

from roost.computer_use.fence import SiteFence
from roost.desk.browser import DeskBrowserPage
from roost.desk.tabs import TabView, tab_for_site, tab_views

from test_front_tab import FakeTab, TabBrowser


class ClosingBrowser(TabBrowser):
    async def send(self, method, params=None, session_id=None):
        if method == "Target.closeTarget":
            self.calls.append((method, params or {}, session_id))
            self.tabs = [t for t in self.tabs if t.target_id != params["targetId"]]
            return {"result": {"success": True}}
        if method == "Target.activateTarget":
            self.calls.append((method, params or {}, session_id))
            self.show(params["targetId"])
            return {"result": {}}
        return await super().send(method, params, session_id)


def _browser() -> ClosingBrowser:
    return ClosingBrowser(
        FakeTab("A", "https://shop.example/", visible=True, focused=True),
        FakeTab("B", "https://news.example/"),
        FakeTab("C", "https://mail.example/"),
    )


async def _page(browser) -> DeskBrowserPage:
    page = DeskBrowserPage(browser)
    await page.page_session()                    # the bot's tab: the one in front, A
    return page


def test_tab_views_number_from_one_and_mark_the_bots_tab():
    views = tab_views((("A", "https://shop.example/", "Shop"), ("B", "https://b.example/x", "B")), "B")
    assert views == (TabView(1, "A", "https://shop.example/", "Shop", False),
                     TabView(2, "B", "https://b.example/x", "B", True))
    assert views[1].host == "b.example"


async def test_the_tab_list_holds_every_page_and_the_bots_own_mark():
    page = await _page(_browser())
    views = await page.tab_list()
    assert [(v.index, v.target_id, v.mine) for v in views] == [(1, "A", True), (2, "B", False), (3, "C", False)]


async def test_switching_brings_the_tab_up_and_makes_it_the_bots():
    browser = _browser()
    page = await _page(browser)
    old_session = page._session_id
    await page.attach_tab("C")
    assert browser.sent("Target.activateTarget")[-1][0] == {"targetId": "C"}
    assert page._target_id == "C" and old_session in browser.detached
    assert browser.sent("Page.bringToFront")[-1][1] == page._session_id
    assert [v.target_id for v in await page.tab_list() if v.mine] == ["C"]


async def test_switching_moves_armed_guards_onto_the_new_tab():
    browser = _browser()
    page = await _page(browser)
    guards = await page.guards()
    await guards.arm(SiteFence(frozenset({"shop.example"})))
    await page.attach_tab("B")
    fetch_sessions = [sid for _, sid in browser.sent("Fetch.enable")]
    assert fetch_sessions[-1] == page._session_id and guards.armed


async def test_closing_another_tab_closes_it():
    browser = _browser()
    page = await _page(browser)
    assert await page.close_tab("B") == "closed"
    assert [t.target_id for t in browser.tabs] == ["A", "C"] and page._target_id == "A"


async def test_closing_the_bots_own_tab_moves_it_to_the_tab_in_front():
    browser = _browser()
    page = await _page(browser)
    browser.show("C")
    assert await page.close_tab("A") == "closed"
    assert page._target_id == "C" and [t.target_id for t in browser.tabs] == ["B", "C"]


async def test_the_last_tab_is_never_closed_it_goes_blank():
    browser = ClosingBrowser(FakeTab("A", "https://shop.example/", visible=True, focused=True))
    page = await _page(browser)
    assert await page.close_tab("A") == "blanked"
    assert browser.sent("Target.closeTarget") == []
    assert browser.sent("Page.navigate")[-1][0] == {"url": "about:blank"}


class _TabPage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def tab_list(self):
        return (TabView(1, "A", "https://a.example/", "A", True),)

    async def attach_tab(self, target_id):
        self.calls.append(("switch", target_id))

    async def close_tab(self, target_id):
        self.calls.append(("close", target_id))
        return "closed"

    async def close(self):
        return None


async def test_the_keeper_desk_lists_switches_and_closes_tabs_on_linux_only(tmp_path):
    import pytest

    from roost.config import RoostConfig
    from roost.desk import DeskUnavailable
    from roost.desk.client import KeeperDesk

    config = RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "d", desks_dir=tmp_path / "k",
                         keeper_secret="k" * 32)
    page = _TabPage()

    async def connect(relay_url, token):
        return page

    async def started():
        return {"cdp_token": "t"}

    desk = KeeperDesk(config, "b", computer="linux", connect_page=connect)
    desk._start_browser_session = started
    assert [v.target_id for v in await desk.tabs()] == ["A"]
    await desk.switch_tab("A")
    assert await desk.close_tab("A") == "closed"
    assert page.calls == [("switch", "A"), ("close", "A")]
    with pytest.raises(DeskUnavailable):
        await KeeperDesk(config, "b", computer="mac_brave").tabs()


# -- owner, 2026-10-27: a site already in a tab is that tab, not loaded again ----------------------------------


def test_a_sites_front_page_is_the_tab_that_shows_it():
    tabs = tab_views((("A", "https://shop.example/", "Shop"), ("B", "https://web.whatsapp.com/", "WhatsApp"),
                      ("C", "https://web.whatsapp.com/", "WhatsApp")), "C")
    assert tab_for_site(tabs, "https://web.whatsapp.com/").target_id == "C"          # the bot's own first
    assert tab_for_site(tabs, "https://web.whatsapp.com").target_id == "C"
    others = tab_views((("A", "https://web.whatsapp.com/", "W"), ("B", "https://news.example/", "N")), "B")
    assert tab_for_site(others, "https://web.whatsapp.com/").target_id == "A"
    assert tab_for_site(tabs, "https://web.whatsapp.com/send?phone=1") is None        # a deeper address navigates
    assert tab_for_site(tabs, "https://mail.example/") is None


async def test_opening_a_site_another_tab_shows_switches_to_it_without_loading():
    browser = _browser()
    page = await _page(browser)
    await page.open_page("https://news.example/", reuse_tab=True)
    assert browser.sent("Target.activateTarget")[-1][0] == {"targetId": "B"}
    assert not browser.sent("Page.navigate")
    assert [v.target_id for v in await page.tab_list() if v.mine] == ["B"]
