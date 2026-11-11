"""A browser that stops answering heals itself (owner, 2026-11-10, docs/plans/2026-11-10-roost-self-healing.md).

Bot 1016fb46's Chromium tab froze: ``Page.enable`` timed out after 30 s, every ``open_page`` then raised
``DeskUnavailable``, and a page watch failed for half an hour, while ``Browser.getVersion`` still answered, so the
hung-browser restart of 2026-11-06 never fired. Now ``DESK_UNANSWERED_STREAK`` page calls that fail within
``DESK_UNANSWERED_WINDOW_S`` count as a hung browser too: the computer restarts through the same path, under the same
cooldown, the call runs once more, and the desk tells its ``on_healed`` hook once. A success resets the streak."""

from __future__ import annotations

import httpx
import pytest

from roost.config import RoostConfig
from roost.constants import (
    BROWSER_RESTARTED_TEXT, COMPUTER_HUNG_RESTART_COOLDOWN_S, DESK_UNANSWERED_STREAK, DESK_UNANSWERED_WINDOW_S,
)
from roost.desk import DeskUnavailable, PageText
from roost.desk.cdp import CdpReplyError
from roost.desk.client import KeeperDesk
from roost.desk.control import ControlMark

_BOT_ID = "00000000-0000-4000-8000-000000000001"
_TIMED_OUT = "timed out after 30s waiting for a reply to 'Page.enable'"
_URL = "https://www.upwork.com/"


@pytest.fixture
def config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret="k" * 32)


class _Keeper:
    def __init__(self) -> None:
        self.stops = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/computer/stop"):
            self.stops += 1
            return httpx.Response(200, json={"computer": "stopped"})
        return httpx.Response(200, json={"cdp_token": "t", "computer": "running", "workspace": "running"})


class _Page:
    """A page whose browser answers the probe but whose tab times out ``fails`` times, then reads."""

    def __init__(self, reads: list[Exception | None]) -> None:
        self.reads = reads
        self.closed = False

    def forget_session(self) -> None:
        pass

    async def tab_crashed(self) -> bool:
        return False

    async def browser_answers(self) -> bool:
        return True

    async def read_page(self) -> PageText:
        error = self.reads.pop(0) if self.reads else None
        if error is not None:
            raise error
        return PageText(url=_URL, title="Upwork", text="jobs", truncated=False)

    async def close(self) -> None:
        self.closed = True


class _Rig:
    def __init__(self, config: RoostConfig, pages: list[_Page], *, computer: str = "linux") -> None:
        self.keeper, self.now, self.healed = _Keeper(), [1000.0], 0
        queue = list(pages)

        async def connect(relay_url: str, token: str) -> _Page:
            return queue.pop(0)

        async def healed() -> None:
            self.healed += 1

        self.desk = KeeperDesk(
            config, _BOT_ID, transport=httpx.MockTransport(self.keeper), computer=computer,  # type: ignore[arg-type]
            connect_page=connect, control_mark=lambda: ControlMark(epoch=1, held=False),  # type: ignore[arg-type]
            clock=lambda: self.now[0], on_healed=healed)

    async def fail_once(self) -> None:
        with pytest.raises(DeskUnavailable):
            await self.desk.read_page()


def _timeouts(count: int) -> list[Exception | None]:
    return [CdpReplyError(_TIMED_OUT) for _ in range(count)]


async def test_a_streak_of_unanswered_calls_restarts_the_computer_and_says_so_once(config):
    rig = _Rig(config, [_Page(_timeouts(DESK_UNANSWERED_STREAK)), _Page([None])])
    for _ in range(DESK_UNANSWERED_STREAK - 1):
        await rig.fail_once()
    assert rig.keeper.stops == 0 and rig.healed == 0

    result = await rig.desk.read_page()      # the call that completes the streak restarts and runs again

    assert result.text == "jobs" and result.notice == BROWSER_RESTARTED_TEXT
    assert rig.keeper.stops == 1 and rig.healed == 1


async def test_a_success_resets_the_streak(config):
    rig = _Rig(config, [_Page([*_timeouts(DESK_UNANSWERED_STREAK - 1), None, *_timeouts(DESK_UNANSWERED_STREAK - 1)])])
    for _ in range(DESK_UNANSWERED_STREAK - 1):
        await rig.fail_once()
    assert (await rig.desk.read_page()).text == "jobs"
    for _ in range(DESK_UNANSWERED_STREAK - 1):
        await rig.fail_once()
    assert rig.keeper.stops == 0 and rig.healed == 0


async def test_failures_further_apart_than_the_window_do_not_count_together(config):
    rig = _Rig(config, [_Page(_timeouts(DESK_UNANSWERED_STREAK))])
    for _ in range(DESK_UNANSWERED_STREAK):
        await rig.fail_once()
        rig.now[0] += DESK_UNANSWERED_WINDOW_S + 1
    assert rig.keeper.stops == 0 and rig.healed == 0


async def test_the_streak_restart_keeps_the_cooldown(config):
    hung_again = _Page(_timeouts(1 + DESK_UNANSWERED_STREAK * 2))    # the fresh browser hangs too
    rig = _Rig(config, [_Page(_timeouts(DESK_UNANSWERED_STREAK)), hung_again, _Page([None])])
    for _ in range(DESK_UNANSWERED_STREAK - 1):
        await rig.fail_once()
    await rig.fail_once()        # the streak restarts; the call's one more try on the fresh browser fails too
    assert rig.keeper.stops == 1 and rig.healed == 1
    for _ in range(DESK_UNANSWERED_STREAK):
        await rig.fail_once()    # a second streak inside the cooldown: no second restart, no second line
    assert rig.keeper.stops == 1 and rig.healed == 1
    rig.now[0] += COMPUTER_HUNG_RESTART_COOLDOWN_S + 1
    for _ in range(DESK_UNANSWERED_STREAK):      # after the cooldown, a streak restarts again within one streak
        try:
            page = await rig.desk.read_page()
        except DeskUnavailable:
            continue
        assert page.notice == BROWSER_RESTARTED_TEXT
        break
    assert rig.keeper.stops == 2 and rig.healed == 2


async def test_mac_brave_never_restarts_and_never_says_so(config):
    rig = _Rig(config, [_Page(_timeouts(DESK_UNANSWERED_STREAK))], computer="mac_brave")
    for _ in range(DESK_UNANSWERED_STREAK):
        await rig.fail_once()
    assert rig.keeper.stops == 0 and rig.healed == 0


async def test_a_healed_hook_that_fails_never_breaks_the_page_call(config):
    rig = _Rig(config, [_Page(_timeouts(DESK_UNANSWERED_STREAK)), _Page([None])])

    async def boom() -> None:
        raise RuntimeError("no chat to tell")

    rig.desk._on_healed = boom      # noqa: SLF001 — the hook is private wiring
    for _ in range(DESK_UNANSWERED_STREAK - 1):
        await rig.fail_once()
    assert (await rig.desk.read_page()).notice == BROWSER_RESTARTED_TEXT


def test_a_five_minute_watch_alone_can_fill_the_streak():
    """Live, 2026-11-10: a 5-minute watch was the only caller, so 3 failures never fell inside a 10-minute window and
    the frozen browser waited 35 minutes for its restart."""
    from roost.constants import WATCH_EVERY_MIN_MINUTES

    span = (DESK_UNANSWERED_STREAK - 1) * WATCH_EVERY_MIN_MINUTES * 60
    assert DESK_UNANSWERED_WINDOW_S >= span + WATCH_EVERY_MIN_MINUTES * 60
