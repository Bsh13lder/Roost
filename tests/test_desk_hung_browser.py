"""A hung browser restarts its computer (owner, 2026-11-06: "prevent that problem next time"). Gela's Brave had run for
7½ days; every CDP command then timed out (30 s each), so every page open took ~90 s and every routine watch check
failed, and the owner's message sat behind them. Now a command that times out, on a tab that is not merely crashed,
has the browser itself probed (``Browser.getVersion`` within ``CDP_CRASH_PROBE_TIMEOUT_S``); a browser that does not
answer, or a page that keeps crashing, gets the Linux computer stopped and started again (the profile and its kept
sign-ins stay) and the call runs once more on the fresh browser, its result saying so. Never while you hold the
computer, never on Mac Brave, and at most once per ``COMPUTER_HUNG_RESTART_COOLDOWN_S``."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from roost.config import RoostConfig
from roost.constants import (
    BROWSER_RESTARTED_TEXT,
    CDP_CRASH_PROBE_TIMEOUT_S,
    COMPUTER_HUNG_RESTART_COOLDOWN_S,
)
from roost.desk import DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpReplyError
from roost.desk.client import KeeperDesk
from roost.desk.control import ControlMark

_BOT_ID = "00000000-0000-4000-8000-000000000001"
_TIMED_OUT = "timed out after 30s waiting for a reply to 'Page.navigate'"
_URL = "https://www.alsa.es/"


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret="k" * 32)


class _Keeper:
    """The keeper's computer routes: counts the stops."""

    def __init__(self) -> None:
        self.stops = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/computer/stop"):
            self.stops += 1
            return httpx.Response(200, json={"computer": "stopped"})
        return httpx.Response(200, json={"cdp_token": "t", "computer": "running", "workspace": "running"})


class _Page:
    """A page stand-in: ``reads`` scripts each read; ``answers`` is what the browser probe says."""

    def __init__(self, reads: list[Exception | None], *, answers: bool, crashed: bool = False) -> None:
        self.reads, self.answers, self.crashed = reads, answers, crashed
        self.closed = False
        self.reopened = 0

    def forget_session(self) -> None:
        pass

    async def tab_crashed(self) -> bool:
        return self.crashed

    async def reopen_crashed_tab(self) -> str | None:
        self.reopened += 1
        return _URL

    async def browser_answers(self) -> bool:
        return self.answers

    async def read_page(self) -> PageText:
        error = self.reads.pop(0) if self.reads else None
        if error is not None:
            raise error
        return PageText(url=_URL, title="ALSA", text="buses", truncated=False)

    async def close(self) -> None:
        self.closed = True


def _desk(keeper: _Keeper, pages: list[_Page], *, config: RoostConfig, held: bool = False,
          computer: str = "linux", clock=lambda: 1000.0) -> KeeperDesk:
    queue = list(pages)

    async def connect(relay_url: str, token: str) -> _Page:
        return queue.pop(0)

    return KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(keeper), computer=computer,  # type: ignore[arg-type]
                      connect_page=connect, control_mark=lambda: ControlMark(epoch=1, held=held),  # type: ignore[arg-type]
                      clock=clock)


async def test_a_browser_that_does_not_answer_restarts_the_computer_and_the_call_runs_again(config):
    keeper = _Keeper()
    hung, fresh = _Page([CdpReplyError(_TIMED_OUT)], answers=False), _Page([None], answers=True)
    result = await _desk(keeper, [hung, fresh], config=config).read_page()
    assert result.text == "buses" and result.notice == BROWSER_RESTARTED_TEXT
    assert keeper.stops == 1 and hung.closed is True
    assert BROWSER_RESTARTED_TEXT.startswith("The browser had stopped answering")


async def test_a_page_that_keeps_crashing_restarts_the_computer_too(config):
    keeper = _Keeper()
    crashing = _Page([CdpReplyError(_TIMED_OUT), CdpReplyError(_TIMED_OUT)], answers=True, crashed=True)
    fresh = _Page([None], answers=True)
    result = await _desk(keeper, [crashing, fresh], config=config).read_page()
    assert crashing.reopened == 1 and keeper.stops == 1 and result.notice == BROWSER_RESTARTED_TEXT


async def test_a_slow_command_on_a_browser_that_answers_is_still_that_commands_failure(config):
    keeper = _Keeper()
    page = _Page([CdpReplyError(_TIMED_OUT)], answers=True)
    with pytest.raises(DeskUnavailable) as raised:
        await _desk(keeper, [page], config=config).read_page()
    assert "did not answer" in str(raised.value) and keeper.stops == 0


async def test_while_you_hold_the_computer_it_is_never_restarted(config):
    keeper = _Keeper()
    page = _Page([CdpReplyError(_TIMED_OUT)], answers=False)
    with pytest.raises(DeskUnavailable):
        await _desk(keeper, [page], config=config, held=True).read_page()
    assert keeper.stops == 0


async def test_mac_brave_is_never_restarted(config):
    keeper = _Keeper()
    page = _Page([CdpReplyError(_TIMED_OUT)], answers=False)
    with pytest.raises(DeskUnavailable):
        await _desk(keeper, [page], config=config, computer="mac_brave").read_page()
    assert keeper.stops == 0


async def test_one_restart_per_cooldown_and_another_after_it(config):
    keeper, now = _Keeper(), [1000.0]
    pages = [_Page([CdpReplyError(_TIMED_OUT)], answers=False),
             _Page([CdpReplyError(_TIMED_OUT), CdpReplyError(_TIMED_OUT)], answers=False), _Page([None], answers=True)]
    desk = _desk(keeper, pages, config=config, clock=lambda: now[0])
    with pytest.raises(DeskUnavailable):          # restarted once; the fresh browser hangs too: no second restart
        await desk.read_page()
    assert keeper.stops == 1
    now[0] += COMPUTER_HUNG_RESTART_COOLDOWN_S + 1
    assert (await desk.read_page()).notice == BROWSER_RESTARTED_TEXT
    assert keeper.stops == 2


class _Cdp:
    """A CDP client stand-in: ``reply`` answers, raises or hangs; every call is recorded with its session."""

    is_open = True

    def __init__(self, reply) -> None:
        self.reply = reply
        self.sent: list[tuple[str, str | None]] = []

    async def send(self, method, params=None, session_id=None):
        self.sent.append((method, session_id))
        return await self.reply()


async def _answer():
    return {"id": 1, "result": {"product": "Chrome/1"}}


async def _boom():
    raise CdpReplyError("CDP error")


async def _never():
    await asyncio.sleep(CDP_CRASH_PROBE_TIMEOUT_S * 10)


async def test_browser_answers_probes_the_browser_not_the_tab():
    cdp = _Cdp(_answer)
    assert await DeskBrowserPage(cdp).browser_answers() is True  # type: ignore[arg-type]
    assert cdp.sent == [("Browser.getVersion", None)]


async def test_browser_answers_is_false_when_the_probe_fails_or_hangs(monkeypatch):
    assert await DeskBrowserPage(_Cdp(_boom)).browser_answers() is False  # type: ignore[arg-type]
    monkeypatch.setattr("roost.desk.browser.CDP_CRASH_PROBE_TIMEOUT_S", 0.01)
    assert await DeskBrowserPage(_Cdp(_never)).browser_answers() is False  # type: ignore[arg-type]
