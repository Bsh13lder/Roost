"""A Sign-in card's I'm done saves a Vault login only when the bot's computer looks signed in (owner, 2026-10-23, A1).

Signed in means: the sign-in page detector no longer sees a sign-in page on the bot's front tab, and the browser
holds at least one cookie for the card's host or a parent domain (fixed CDP, the host validated). Otherwise nothing
is saved, the card stays open and the answer says so. Mac Brave bots: unchanged."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from roost.config import load_config
from roost.desk import DeskAsleep, DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.client import KeeperDesk
from roost.desk.fake import FakeDesk
from roost.desk.site_data import BadHost, SignInSignals, cookie_covers, count_site_cookies
from roost.signin.check import NotSignedInYet, SignInCheck, looks_signed_in
from roost.signin.texts import not_signed_in_text
from roost.stuck.models import CardState
from test_signin_cards import ORIGIN, SHOP, WALL, _app_with_card, _signed_in, cfg  # noqa: F401


class FakeCdp:
    def __init__(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies = cookies
        self.calls: list[str] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        self.calls.append(method)
        return {"id": 1, "result": {"cookies": self.cookies}}


ACCOUNT = PageText(url="https://shop.example/orders", title="Your orders", text="Order 1", truncated=False)


# --- the pure parts -----------------------------------------------------------------------------------------------

def test_a_cookie_covers_its_own_host_and_the_host_under_it_never_a_suffix_or_another_site() -> None:
    assert cookie_covers(".shop.example", "shop.example")
    assert cookie_covers("shop.example", "accounts.shop.example")      # a parent domain's cookie
    assert not cookie_covers("other.example", "shop.example")
    assert not cookie_covers("accounts.shop.example", "shop.example")  # a subdomain's cookie is not the site's
    assert not cookie_covers(".co.uk", "shop.co.uk")                   # a public suffix never counts
    assert not cookie_covers("com", "shop.com")
    assert not cookie_covers("", "shop.example")


async def test_count_site_cookies_reads_the_jar_and_never_returns_a_value() -> None:
    cdp = FakeCdp([{"name": "sid", "domain": ".shop.example", "value": "secret"},
                   {"name": "x", "domain": "other.example", "value": "secret"}])
    assert await count_site_cookies(cdp, "accounts.shop.example") == 1
    assert cdp.calls == ["Storage.getCookies"]


async def test_count_site_cookies_validates_the_host_before_any_call() -> None:
    cdp = FakeCdp([])
    with pytest.raises(BadHost):
        await count_site_cookies(cdp, "1.2.3.4")
    assert cdp.calls == []


def test_looks_signed_in_needs_no_sign_in_page_and_a_cookie() -> None:
    assert looks_signed_in(ACCOUNT, 1)
    assert not looks_signed_in(ACCOUNT, 0)
    assert not looks_signed_in(WALL, 3)


async def test_the_fake_desk_reads_the_front_page_and_counts_the_hosts_cookies() -> None:
    desk = FakeDesk("b1", "linux")
    desk.cookie_domains = (".shop.example", "other.example")
    signals = await desk.sign_in_signals("shop.example")
    assert signals.cookies == 1 and signals.page.url == "about:blank"
    desk.force_unavailable = True
    with pytest.raises(Exception):
        await desk.sign_in_signals("shop.example")


# --- I'm done on a Sign-in card ------------------------------------------------------------------------------------

async def test_no_cookie_saves_nothing_and_keeps_the_card_open(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me@shop", "keep": True}, headers=ORIGIN)
    assert r.status_code == 409
    assert r.json()["detail"] == not_signed_in_text("shop.example")
    assert not_signed_in_text("shop.example") == "You don't look signed in to shop.example yet, so nothing was saved."
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()
    assert (await app.state.stuck.get(user.id, card.id)).state is CardState.OPEN


async def test_a_sign_in_page_still_in_front_saves_nothing_even_with_a_cookie(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.cookie_domains = (".shop.example",)
    desk.serve(SHOP, WALL)
    await desk.open_page(SHOP)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"keep": False}, headers=ORIGIN)
    assert r.status_code == 409
    assert await app.state.vault_store.list_for_bot(user.id, bot.id) == ()


async def test_a_parent_domain_cookie_and_an_ordinary_page_save_the_login(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg)
    desk = app.state.desks.for_bot(bot.id, "linux")
    desk.cookie_domains = ("example",) + ("shop.example",)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me", "keep": True}, headers=ORIGIN)
    assert r.status_code == 200
    [login] = await app.state.vault_store.list_for_bot(user.id, bot.id)
    assert login.host == "shop.example"


async def test_check_again_without_an_answer_needs_no_sign_in(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"how": "try_again"}, headers=ORIGIN)
    assert r.status_code == 200


async def test_an_unreachable_computer_is_a_503_and_the_card_stays_open(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg)
    app.state.desks.for_bot(bot.id, "linux").force_unavailable = True
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"keep": True}, headers=ORIGIN)
    assert r.status_code == 503
    assert (await app.state.stuck.get(user.id, card.id)).state is CardState.OPEN


async def test_a_bot_now_on_mac_brave_is_unchanged(cfg):  # noqa: F811
    app, user, bot, thread, card = await _app_with_card(cfg, linux=False)
    async with _signed_in(app) as c:
        r = await c.post(f"/api/stuck/{card.id}/clear", json={"account": "me", "keep": True}, headers=ORIGIN)
    assert r.status_code == 200
    assert len(await app.state.vault_store.list_for_bot(user.id, bot.id)) == 1


# --- the real desk and its page -------------------------------------------------------------------------------------

class _SignalPage:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def sign_in_signals(self, host: str) -> SignInSignals:
        self.hosts.append(host)
        return SignInSignals(page=ACCOUNT, cookies=2)

    async def close(self) -> None: ...


def _keeper(computer: str) -> tuple[KeeperDesk, _SignalPage]:
    page = _SignalPage()

    async def connect(relay_url: str, token: str) -> _SignalPage:
        return page

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cdp_token": "t", "computer": "running", "workspace": "absent"})

    return KeeperDesk(load_config(), "b1", computer=computer, transport=httpx.MockTransport(handler),
                      connect_page=connect), page


async def test_the_keeper_desk_reads_the_signals_on_its_linux_computer_only() -> None:
    desk, page = _keeper("linux")
    signals = await desk.sign_in_signals("Shop.example")
    assert page.hosts == ["shop.example"] and signals.cookies == 2
    mac, _ = _keeper("mac_brave")
    with pytest.raises(DeskUnavailable):
        await mac.sign_in_signals("shop.example")
    with pytest.raises(BadHost):
        await desk.sign_in_signals("1.2.3.4")


async def test_the_browser_page_follows_the_front_tab_then_reads_page_and_cookies() -> None:
    page = object.__new__(DeskBrowserPage)
    page._client = FakeCdp([{"name": "sid", "domain": ".shop.example", "value": "v"}])
    steps: list[str] = []

    async def follow() -> bool:
        steps.append("front")
        return True

    async def read() -> PageText:
        steps.append("read")
        return ACCOUNT

    page.follow_front_tab = follow
    page.read_page = read
    signals = await page.sign_in_signals("shop.example")
    assert steps == ["front", "read"] and signals.cookies == 1 and signals.page is ACCOUNT


async def test_a_sleeping_computer_saves_nothing() -> None:
    class Bots:
        async def get(self, user_id: str, bot_id: str) -> Any:
            return type("B", (), {"computer": "linux"})()

    class Asleep:
        async def sign_in_signals(self, host: str) -> Any:
            raise DeskAsleep("asleep")

    class Desks:
        def for_bot(self, bot_id: str, computer: str) -> Any:
            return Asleep()

    with pytest.raises(NotSignedInYet):
        await SignInCheck(Bots(), Desks()).require("u", "b", "shop.example")
