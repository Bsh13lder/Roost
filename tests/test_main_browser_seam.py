"""The gateway's seam to "Use my main Brave" (stuck flow, Task 6; design R8).

``make_main_browser`` picks ``KeeperMainBrowser`` in keeper mode and the
recording ``FakeMainBrowser`` in fake mode, so no test or E2E run ever
reaches a keeper or a real Brave. ``KeeperMainBrowser`` is run here against
the real keeper app over ``httpx.ASGITransport``, with a recording runner
in place of ``/usr/bin/open``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.desk.main_browser import FakeMainBrowser, KeeperMainBrowser, MainBrowser, make_main_browser
from roost.desk.url_policy import UrlBlocked
from roost.keeper.app import create_app
from roost.keeper.main_browser import MainBrowserOpener

_BOT_ID = "77777777-7777-4777-8777-777777777777"
_SECRET = "k" * 32
_URL = "https://example.com/"
_OVERLONG_URL = "https://example.com/" + "a" * MAIN_BROWSER_URL_MAX_CHARS


class _FakeOpenRunner:
    """Stands in for ``/usr/bin/open``. It records each argv and answers
    exit code 0. It never runs anything."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        return 0


def _config(tmp_path: Path, desk_mode: str) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
        desk_mode=desk_mode,
    )


def _keeper_main_browser(config: RoostConfig, runner: _FakeOpenRunner) -> KeeperMainBrowser:
    keeper = create_app(config)
    keeper.state.main_browser = MainBrowserOpener(runner=runner)
    client = KeeperClient(config, transport=httpx.ASGITransport(app=keeper))
    return KeeperMainBrowser(config, client=client)


def test_fake_mode_gets_the_recording_fake(tmp_path: Path):
    assert isinstance(make_main_browser(_config(tmp_path, "fake")), FakeMainBrowser)


def test_keeper_mode_gets_the_keeper_main_browser(tmp_path: Path):
    browser: MainBrowser = make_main_browser(_config(tmp_path, "keeper"))
    assert isinstance(browser, KeeperMainBrowser)


async def test_the_fake_records_each_open_in_a_new_tuple():
    fake = FakeMainBrowser()
    before = fake.opened
    await fake.open("bot-1", _URL)
    after_first = fake.opened
    await fake.open("bot-2", "https://login.example/")
    assert before == ()
    assert after_first == (("bot-1", _URL),)
    assert fake.opened == (("bot-1", _URL), ("bot-2", "https://login.example/"))


async def test_the_fake_records_the_canonical_address():
    fake = FakeMainBrowser()
    await fake.open("bot-1", "https://EXAMPLE.com/Path")
    assert fake.opened == (("bot-1", "https://example.com/Path"),)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1/"])
async def test_the_fake_refuses_what_the_keeper_refuses(url: str):
    fake = FakeMainBrowser()
    with pytest.raises(UrlBlocked):
        await fake.open("bot-1", url)
    assert fake.opened == ()


async def test_a_failing_fake_is_desk_unavailable():
    fake = FakeMainBrowser(fail=True)
    with pytest.raises(DeskUnavailable):
        await fake.open("bot-1", _URL)
    assert fake.opened == ()


async def test_the_fakes_fail_flag_can_be_switched_on_later():
    """API tests flip it through ``app.state`` the way they flip ``FakeDesk.force_unavailable``."""
    fake = FakeMainBrowser()
    fake.fail = True
    with pytest.raises(DeskUnavailable):
        await fake.open("bot-1", _URL)


async def test_the_keeper_main_browser_opens_through_the_signed_keeper_route(tmp_path: Path):
    runner = _FakeOpenRunner()
    await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, _URL)
    assert runner.calls == [["/usr/bin/open", "-a", "Brave Browser", _URL]]


async def test_the_keeper_main_browser_passes_on_a_refusal_as_url_blocked(tmp_path: Path):
    runner = _FakeOpenRunner()
    with pytest.raises(UrlBlocked):
        await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, "javascript:alert(1)")
    assert runner.calls == []


async def test_the_keeper_main_browser_with_the_keeper_down_is_desk_unavailable(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    config = _config(tmp_path, "keeper")
    browser = KeeperMainBrowser(config, client=KeeperClient(config, transport=httpx.MockTransport(handler)))
    with pytest.raises(DeskUnavailable):
        await browser.open(_BOT_ID, _URL)


async def test_the_keeper_main_browser_refuses_an_overlong_address_as_url_blocked(tmp_path: Path):
    """The keeper answers an over-long body 422, which ``KeeperClient`` turns into
    ``DeskUnavailable`` (503). The seam refuses it first, so the user sees a 400."""
    runner = _FakeOpenRunner()
    with pytest.raises(UrlBlocked):
        await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, _OVERLONG_URL)
    assert runner.calls == []


async def test_the_fake_refuses_an_overlong_address_like_the_keeper_seam():
    fake = FakeMainBrowser()
    with pytest.raises(UrlBlocked):
        await fake.open("bot-1", _OVERLONG_URL)
    assert fake.opened == ()
