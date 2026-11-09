"""D5 (owner decision 2026-10-23): a run's tabs don't pile up. Tabs that existed before the run stay; the ones the
run opened close at its end (the bot's own tab stays), and a run never holds more than ``CU_RUN_TABS_MAX``."""

from __future__ import annotations

from roost.computer_use.run_tabs import RunTabs
from roost.constants import CU_RUN_TABS_MAX
from roost.desk.tabs import TabView


class _Tabs:
    def __init__(self, ids: list[str], mine: str) -> None:
        self.ids = list(ids)
        self.mine = mine
        self.closed: list[str] = []
        self.fail = False
        self.listed = 0
        self.windows: tuple = ((0, 0, 1280, 800),)

    async def browser_windows(self) -> tuple:
        return self.windows

    async def tabs(self) -> tuple[TabView, ...]:
        self.listed += 1
        if self.fail:
            raise RuntimeError("browser gone")
        return tuple(TabView(i + 1, t, f"https://{t}.example/", t, t == self.mine) for i, t in enumerate(self.ids))

    async def close_tab(self, target_id: str) -> str:
        self.ids.remove(target_id)
        self.closed.append(target_id)
        return "closed"


async def test_tabs_the_run_opened_close_at_its_end_but_the_old_ones_and_its_own_stay():
    desk = _Tabs(["old"], mine="old")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.ids += ["a", "b"]
    desk.mine = "b"
    await run.cleanup()
    assert desk.closed == ["a"]
    assert desk.ids == ["old", "b"]


async def test_a_run_that_never_saw_the_browser_closes_nothing():
    desk = _Tabs(["old", "x"], mine="old")
    await RunTabs(desk, held=lambda: False).cleanup()
    assert desk.closed == []


async def test_the_snapshot_is_taken_once():
    desk = _Tabs(["old"], mine="old")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.ids.append("a")
    await run.snapshot()                       # a second arm in the same run: "a" is still the run's
    await run.cleanup()
    assert desk.closed == ["a"]


async def test_nothing_closes_while_you_hold_the_computer():
    desk = _Tabs(["old"], mine="old")
    held = [False]
    run = RunTabs(desk, held=lambda: held[0])
    await run.snapshot()
    desk.ids.append("yours")
    held[0] = True
    await run.cleanup()
    await run.trim()
    assert desk.closed == []


async def test_trim_closes_the_oldest_tab_this_run_opened_past_the_cap():
    desk = _Tabs(["old"], mine="old")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    for n in range(CU_RUN_TABS_MAX):
        desk.ids.append(f"t{n}")
        await run.trim()
    desk.mine = f"t{CU_RUN_TABS_MAX - 1}"
    assert len(desk.ids) == CU_RUN_TABS_MAX
    assert desk.closed == ["t0"]               # the first one this run opened; "old" is never touched
    assert "old" in desk.ids


async def test_trim_never_closes_the_bots_tab_or_an_old_one():
    desk = _Tabs(["o1", "o2", "o3", "o4", "o5"], mine="o1")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.ids.append("mine-now")
    desk.mine = "mine-now"
    await run.trim()
    assert desk.closed == []


async def test_a_closed_brave_is_not_started_again_just_to_tidy():
    """Listing tabs speaks DevTools, which starts Brave on demand: with no Brave window, nothing is asked."""
    desk = _Tabs(["old"], mine="old")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.windows = ()
    listed = desk.listed
    await run.trim()
    await run.cleanup()
    assert desk.listed == listed and desk.closed == []


async def test_no_snapshot_without_a_brave_window():
    desk = _Tabs(["x"], mine="x")
    desk.windows = ()
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.windows = ((0, 0, 1, 1),)
    await run.cleanup()
    assert desk.listed == 0 and desk.closed == []    # never snapshotted: nothing is the run's to close


async def test_a_browser_that_went_away_is_never_an_error():
    desk = _Tabs(["old"], mine="old")
    run = RunTabs(desk, held=lambda: False)
    await run.snapshot()
    desk.fail = True
    await run.trim()
    await run.cleanup()
    assert desk.closed == []
