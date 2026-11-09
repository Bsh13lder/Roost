"""Sign-in card: clearing one site's cookies and storage in a bot's Chromium (``roost/desk/site_data.py``).

Fixed CDP only, the host validated first: a cookie of the host or a subdomain goes, any other site's stays."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from roost.config import load_config
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperDesk
from roost.desk.fake import FakeDesk
from roost.desk.site_data import (
    BadHost, SiteCleared, clear_site, cookie_belongs, origins_for, valid_host,
)


class FakeCdp:
    """Answers ``Storage.getCookies`` from a jar and records every other call."""

    def __init__(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies = cookies
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        self.calls.append((method, dict(params or {}), session_id))
        if method == "Storage.getCookies":
            return {"id": 1, "result": {"cookies": self.cookies}}
        return {"id": 1, "result": {}}


def _cookie(name: str, domain: str, path: str = "/") -> dict[str, Any]:
    return {"name": name, "domain": domain, "path": path, "value": "secret-value"}


@pytest.mark.parametrize("text, host", [
    ("example.com", "example.com"), ("Accounts.Example.COM", "accounts.example.com"),
    ("upwork.com.", "upwork.com"), ("my-site.co", "my-site.co"),
])
def test_valid_host_accepts_a_plain_dns_name(text: str, host: str) -> None:
    assert valid_host(text) == host


@pytest.mark.parametrize("text", [
    "", "localhost", "com", "https://example.com", "example.com/path", "example.com:443", "1.2.3.4",
    "exa mple.com", "-bad.com", "bad-.com", "a..com", "*.example.com", "co.uk", "x" * 64 + ".com",
    "example.com\n", "exämple.com",
])
def test_valid_host_refuses_anything_else(text: str) -> None:
    with pytest.raises(BadHost):
        valid_host(text)


def test_a_cookie_belongs_to_its_host_and_its_subdomains_only() -> None:
    assert cookie_belongs(".example.com", "example.com")
    assert cookie_belongs("example.com", "example.com")
    assert cookie_belongs("accounts.example.com", "example.com")
    assert cookie_belongs(".www.example.com", "example.com")
    assert not cookie_belongs("notexample.com", "example.com")
    assert not cookie_belongs("example.com.evil.net", "example.com")
    assert not cookie_belongs("com", "example.com")
    assert not cookie_belongs("", "example.com")


def test_origins_cover_the_host_and_every_subdomain_its_cookies_named() -> None:
    origins = origins_for("example.com", (".example.com", "accounts.example.com", "accounts.example.com"))
    assert origins == (
        "https://example.com", "http://example.com",
        "https://accounts.example.com", "http://accounts.example.com",
    )


async def test_clear_site_deletes_only_the_sites_cookies_and_clears_its_storage() -> None:
    cdp = FakeCdp([_cookie("sid", ".example.com"), _cookie("a", "accounts.example.com", "/x"),
                   _cookie("keep", "other.org"), _cookie("trick", "notexample.com")])
    cleared = await clear_site(cdp, "S1", "example.com")
    deletes = [(params, sid) for method, params, sid in cdp.calls if method == "Network.deleteCookies"]
    assert deletes == [
        ({"name": "sid", "domain": ".example.com", "path": "/"}, "S1"),
        ({"name": "a", "domain": "accounts.example.com", "path": "/x"}, "S1"),
    ]
    storage = [params for method, params, _ in cdp.calls if method == "Storage.clearDataForOrigin"]
    assert [p["origin"] for p in storage] == [
        "https://example.com", "http://example.com", "https://accounts.example.com", "http://accounts.example.com",
    ]
    assert {p["storageTypes"] for p in storage} == {"all"}
    assert cleared.host == "example.com" and cleared.cookies == 2
    assert "secret-value" not in repr(cleared)


async def test_clear_site_refuses_a_bad_host_before_any_cdp_call() -> None:
    cdp = FakeCdp([])
    with pytest.raises(BadHost):
        await clear_site(cdp, "S1", "https://example.com")
    assert cdp.calls == []


async def test_the_fake_desk_clears_a_hosts_cookies_on_a_linux_computer() -> None:
    desk = FakeDesk("b1", computer="linux")
    desk.cookie_domains = (".example.com", "accounts.example.com", "other.org")
    cleared = await desk.clear_site_data("example.com")
    assert cleared.cookies == 2
    assert desk.cookie_domains == ("other.org",)
    assert desk.cleared_hosts == ("example.com",)


async def test_the_fake_desk_refuses_mac_brave_and_a_bad_host() -> None:
    with pytest.raises(DeskUnavailable):
        await FakeDesk("b1").clear_site_data("example.com")
    with pytest.raises(BadHost):
        await FakeDesk("b1", computer="linux").clear_site_data("co.uk")


# --- KeeperDesk: the real desk sends the clear over its tab, Linux only, host first ----------------------------

class _ClearingPage:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def clear_site(self, host: str) -> SiteCleared:
        self.hosts.append(host)
        return SiteCleared(host=host, cookies=3, origins=())

    async def close(self) -> None: ...


def _keeper_desk(computer: str, started: list[str]) -> tuple[KeeperDesk, _ClearingPage]:
    def handler(request: httpx.Request) -> httpx.Response:
        started.append(request.url.path)
        return httpx.Response(200, json={"cdp_token": "t", "computer": "running", "workspace": "absent"})

    page = _ClearingPage()

    async def connect(relay_url: str, token: str) -> _ClearingPage:
        return page

    desk = KeeperDesk(load_config(), "b1", computer=computer, transport=httpx.MockTransport(handler),
                      connect_page=connect)
    return desk, page


async def test_the_keeper_desk_clears_a_site_on_its_linux_computer() -> None:
    started: list[str] = []
    desk, page = _keeper_desk("linux", started)
    cleared = await desk.clear_site_data("Example.com")
    assert page.hosts == ["example.com"] and cleared.cookies == 3
    assert started == ["/desks/b1/computer/start"]


async def test_the_keeper_desk_refuses_a_bad_host_or_mac_brave_without_waking_anything() -> None:
    started: list[str] = []
    desk, page = _keeper_desk("linux", started)
    with pytest.raises(BadHost):
        await desk.clear_site_data("example.com/../x")
    mac, _ = _keeper_desk("mac_brave", started)
    with pytest.raises(DeskUnavailable):
        await mac.clear_site_data("example.com")
    assert started == [] and page.hosts == []
