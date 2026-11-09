"""Crashed tab recovery (docs/plans/2026-10-30-roost-voice.md §4): Gela's Brave tab was OOM-killed while opening
WhatsApp Web; the tab never answered CDP again, ``open_page`` said the browser "did not answer" and nothing opened it
again. Now a tab that crashed (``Inspector.targetCrashed`` seen, or a command that timed out and a 3-second
``Runtime.evaluate("1")`` probe that fails too) is closed, a fresh tab opens the same address and the call runs once
more; the result says so. A fresh tab that fails too says the page keeps crashing, never "unavailable"."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest
from cu_page_helpers import FakeCdp, load_fixture

from roost.config import RoostConfig
from roost.constants import CDP_CRASH_EVENT, CDP_CRASH_PROBE_TIMEOUT_S, CRASHED_TAB_KEEPS_CRASHING_TEXT, CRASHED_TAB_RECOVERED_TEXT
from roost.desk import DeskUnavailable, PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpReplyError
from roost.desk.client import KeeperDesk
from roost.desk.control import ControlMark
from roost.desk.crash import CrashWatch, PageKeepsCrashing
from roost.talk.tool_runner import page_result_text

_BOT_ID = "00000000-0000-4000-8000-000000000001"
_TIMED_OUT = "timed out after 30s waiting for a reply to 'Accessibility.getFullAXTree'"
_URL = "https://web.whatsapp.com/"


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret="k" * 32)


@pytest.fixture
def transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"cdp_token": "t"}))


# -- the watch ----------------------------------------------------------------------------------------------------


class _Client:
    """A CDP client whose ``Runtime.evaluate`` hangs for ``hang`` seconds (or errors), with a crash-event queue."""

    def __init__(self, *, hang: float = 0.0, error: bool = False) -> None:
        self.hang, self.error = hang, error
        self.queue: asyncio.Queue[dict[str, Any]] | None = None
        self.calls: list[tuple[str, str | None]] = []

    def listen(self, methods: frozenset[str]) -> asyncio.Queue[dict[str, Any]]:
        assert methods == frozenset({CDP_CRASH_EVENT})
        self.queue = asyncio.Queue()
        return self.queue

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        self.calls.append((method, session_id))
        if self.hang:
            await asyncio.sleep(self.hang)
        if self.error:
            raise CdpReplyError(_TIMED_OUT)
        return {"id": 1, "result": {"result": {"value": 1}}}


class _DeafClient:
    """A client with no standing listener (a page stand-in): only the probe can tell."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        self.calls.append((method, session_id))
        return {"id": 1, "result": {"result": {"value": 1}}}


async def test_a_crash_event_on_the_tabs_session_means_it_crashed():
    client = _Client()
    watch = CrashWatch(client)
    client.queue.put_nowait({"method": CDP_CRASH_EVENT, "sessionId": "S-other"})
    assert await watch.crashed("S1") is False      # another tab's crash is not ours: the probe ran and answered
    assert client.calls == [("Runtime.evaluate", "S1")]
    client.queue.put_nowait({"method": CDP_CRASH_EVENT, "sessionId": "S1"})
    assert await watch.crashed("S1") is True
    assert len(client.calls) == 1                   # a seen crash needs no probe


async def test_a_probe_that_errors_or_hangs_means_the_tab_crashed(monkeypatch):
    assert CDP_CRASH_PROBE_TIMEOUT_S == 3.0
    assert await CrashWatch(_Client(error=True)).crashed("S1") is True
    monkeypatch.setattr("roost.desk.crash.CDP_CRASH_PROBE_TIMEOUT_S", 0.05)
    assert await CrashWatch(_Client(hang=1.0)).crashed("S1") is True
    assert await CrashWatch(_Client()).crashed("S1") is False


async def test_a_client_that_cannot_listen_still_probes():
    client = _DeafClient()
    assert await CrashWatch(client).crashed("S1") is False
    assert client.calls == [("Runtime.evaluate", "S1")]


# -- the page: close the dead tab, open the address again in a fresh one ------------------------------------------


class _TabCdp(FakeCdp):
    def __init__(self) -> None:
        super().__init__(load_fixture("login"))
        self.targets = {"T-dead": _URL}
        self.made = 0

    def listen(self, methods: frozenset[str]) -> asyncio.Queue[dict[str, Any]]:
        return asyncio.Queue()

    async def wait_event(self, method: str, session_id: str | None = None, timeout: float = 0.0,
                         predicate: Any = None) -> dict | None:
        return None                      # the navigation's load event never comes in the fake: the wait is short

    def _Target_getTargets(self, params):
        return {"targetInfos": [{"targetId": tid, "type": "page", "url": url, "title": "", "attached": True}
                                for tid, url in self.targets.items()]}

    def _Target_getTargetInfo(self, params):
        return {"targetInfo": {"targetId": params["targetId"], "type": "page", "url": self.targets[params["targetId"]]}}

    def _Target_createTarget(self, params):
        self.made += 1
        tid = f"T-new{self.made}"
        self.targets[tid] = params["url"]
        return {"targetId": tid}

    def _Target_closeTarget(self, params):
        self.targets.pop(params["targetId"], None)
        return {"success": True}

    def _Target_attachToTarget(self, params):
        return {"sessionId": "S-" + params["targetId"]}

    def _Page_getFrameTree(self, params):
        return {"frameTree": {"frame": {"id": "F"}}}

    def _Page_navigate(self, params):
        return {"frameId": "F"}


async def _no_wait(_s: float) -> None:
    return None


async def test_reopen_closes_the_crashed_tab_and_opens_a_fresh_one_at_the_same_address(monkeypatch):
    monkeypatch.setattr("roost.desk.browser.PAGE_LOAD_EVENT_TIMEOUT_S", 0.01)
    client = _TabCdp()
    page = DeskBrowserPage(client, sleep=_no_wait)  # type: ignore[arg-type]
    await page._attach("T-dead")
    assert ("Inspector.enable", {}) in client.calls          # the crash event is on for the bot's tab
    reopened = await page.reopen_crashed_tab()
    assert reopened == _URL
    assert "T-dead" not in client.targets and client.targets == {"T-new1": "about:blank"}
    assert ("Target.closeTarget", {"targetId": "T-dead"}) in client.calls
    assert ("Page.navigate", {"url": _URL}) in client.calls
    assert page._target_id == "T-new1" and page._session_id == "S-T-new1"


async def test_tab_crashed_asks_the_watch_about_the_bots_own_session():
    client = _TabCdp()
    page = DeskBrowserPage(client, sleep=_no_wait)  # type: ignore[arg-type]
    assert await page.tab_crashed() is False                 # no session yet: nothing to have crashed
    await page._attach("T-dead")
    assert await page.tab_crashed() is False                 # the fake answers Runtime.evaluate
    assert ("Runtime.evaluate", {"expression": "1", "returnByValue": True}) in client.calls


# -- the keeping: the call runs once more on the fresh tab, and the result says so ---------------------------------


class _Page:
    """A page stand-in: ``reads`` scripts each read's outcome; ``crashed`` says what the watch would say."""

    def __init__(self, reads: list[Exception | None], *, crashed: bool = True, reopen_fails: bool = False) -> None:
        self.reads = list(reads)
        self.crashed, self.reopen_fails = crashed, reopen_fails
        self.reopened = 0
        self.closed = False
        self.client = type("C", (), {"is_open": True})()

    async def page_session(self):
        return self.client, "S1"

    def forget_session(self) -> None:
        pass

    async def tab_crashed(self) -> bool:
        return self.crashed

    async def reopen_crashed_tab(self) -> str | None:
        self.reopened += 1
        if self.reopen_fails:
            raise CdpReplyError("CDP error replying to 'Target.createTarget': {'message': 'boom'}")
        return _URL

    async def read_page(self) -> PageText:
        error = self.reads.pop(0) if self.reads else None
        if error is not None:
            raise error
        return PageText(url=_URL, title="WhatsApp", text="chats", truncated=False)

    async def close(self) -> None:
        self.closed = True


def _desk(config, transport, page: _Page, *, held: bool = False) -> KeeperDesk:
    async def connect(relay_url: str, token: str) -> _Page:
        return page

    desk = KeeperDesk(config, _BOT_ID, transport=transport, computer="linux", connect_page=connect,
                      control_mark=lambda: ControlMark(epoch=1, held=held))

    async def started() -> dict:
        return {"cdp_token": "t"}

    desk._start_browser_session = started
    return desk


def _just_restarted(desk: KeeperDesk) -> KeeperDesk:
    """The computer was restarted for a hung browser a moment ago (tests/test_desk_hung_browser.py): within the
    cooldown, a page that keeps crashing says so instead of restarting it again."""
    desk._last_hung_restart = time.monotonic()
    return desk


async def test_a_timed_out_command_on_a_crashed_tab_reopens_it_and_the_result_carries_the_notice(config, transport):
    page = _Page([CdpReplyError(_TIMED_OUT), None])
    desk = _desk(config, transport, page)
    result = await desk.read_page()
    assert result.text == "chats" and result.notice == CRASHED_TAB_RECOVERED_TEXT
    assert page.reopened == 1 and page.closed is False
    assert CRASHED_TAB_RECOVERED_TEXT.startswith("The page had crashed")


async def test_a_timed_out_command_on_a_live_tab_is_still_that_commands_failure(config, transport):
    page = _Page([CdpReplyError(_TIMED_OUT)], crashed=False)
    desk = _desk(config, transport, page)
    with pytest.raises(DeskUnavailable) as raised:
        await desk.read_page()
    assert "did not answer" in str(raised.value) and page.reopened == 0


async def test_while_you_hold_the_computer_no_tab_is_closed_or_opened_again(config, transport):
    """Take control: the tab you are looking at (a crashed one you may want to refresh yourself) stays yours."""
    page = _Page([CdpReplyError(_TIMED_OUT)])
    desk = _desk(config, transport, page, held=True)
    with pytest.raises(DeskUnavailable) as raised:
        await desk.read_page()
    assert "did not answer" in str(raised.value) and page.reopened == 0


async def test_a_fresh_tab_that_fails_too_says_the_page_keeps_crashing(config, transport):
    page = _Page([CdpReplyError(_TIMED_OUT), CdpReplyError(_TIMED_OUT)])
    desk = _just_restarted(_desk(config, transport, page))
    with pytest.raises(PageKeepsCrashing) as raised:
        await desk.read_page()
    assert str(raised.value) == CRASHED_TAB_KEEPS_CRASHING_TEXT and "unavailable" not in str(raised.value)
    assert isinstance(raised.value, DeskUnavailable) and page.reopened == 1


async def test_a_reopen_that_fails_says_the_page_keeps_crashing(config, transport):
    page = _Page([CdpReplyError(_TIMED_OUT)], reopen_fails=True)
    with pytest.raises(PageKeepsCrashing):
        await _just_restarted(_desk(config, transport, page)).read_page()


def test_the_tool_result_starts_with_the_notice():
    page = PageText(url=_URL, title="WhatsApp", text="chats", truncated=False, notice=CRASHED_TAB_RECOVERED_TEXT)
    text = page_result_text(page, "<untrusted_page>chats</untrusted_page>")
    assert text.startswith(CRASHED_TAB_RECOVERED_TEXT) and text.endswith("</untrusted_page>")
    plain = PageText(url=_URL, title="WhatsApp", text="chats", truncated=False)
    assert page_result_text(plain, "x") == "x"
