"""``list_tabs``, ``switch_tab`` and ``close_tab`` (B1, owner decision 2026-10-23;
``docs/plans/2026-10-23-roost-tabs-signin-flow.md``).

A tab's number is the one the run's last ``list_tabs`` showed: the listing's target ids are kept in memory
(``TabRun.listed``), and a switch or close first lists again to find that tab still there, so a tab that closed
meanwhile is a plain "There's no tab N" and never another tab. Titles are the page's own words: the listing is
escaped and wrapped as ``<untrusted_page>`` and taints the run. Switching and closing are free acts (D1)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import CU_LABEL_SHOWN_CHARS, CU_TABS_MAX
from roost.desk.tabs import TabView

TAB_TOOLS = frozenset({"list_tabs", "switch_tab", "close_tab"})

LIST_FIRST_TEXT = "List the tabs first (list_tabs), then use a number from that list."
GONE_TEXT = "There's no tab {index} any more. List the tabs again."
SWITCHED_TEXT = "Switched to tab {index} ({host}). Look before your next click."
CLOSED_TEXT = "Closed tab {index} ({host})."
BLANKED_TEXT = "That was the last tab, so I left it open on a blank page."
_BLANK_HOST = "a blank page"


class TabIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=1, le=CU_TABS_MAX)


@dataclass(frozen=True)
class TabOutcome:
    text: str
    listed: tuple[str, ...]        # the target ids of the newest listing, in order
    looked: bool = False           # page words (titles) reached the model
    moved: bool = False            # the bot's tab or the screen changed: the next act looks first


def _line(view: TabView) -> str:
    where = view.host or _BLANK_HOST
    mine = " (your tab)" if view.mine else ""
    title = " ".join(view.title.split())[:CU_LABEL_SHOWN_CHARS]
    return f'{view.index}. {where}{mine}: "{title}"'


def tabs_text(views: tuple[TabView, ...]) -> str:
    """The listing, escaped, in one ``<untrusted_page>`` wrapper: titles are data, never instructions."""
    lines = ["Tabs:", *(_line(view) for view in views[:CU_TABS_MAX])] if views else ["Tabs: none open"]
    return f'<untrusted_page kind="tabs">{html.escape(chr(10).join(lines), quote=True)}</untrusted_page>'


def _host(view: TabView) -> str:
    return view.host or _BLANK_HOST


async def list_tabs(desk: Any) -> TabOutcome:
    views = await desk.tabs()
    return TabOutcome(tabs_text(views), tuple(v.target_id for v in views), looked=True)


async def _still_there(desk: Any, listed: tuple[str, ...], index: int) -> tuple[TabView | None, str]:
    """The tab the listing numbered ``index``, as the browser has it now, or the sentence why not."""
    if not listed:
        return None, LIST_FIRST_TEXT
    wanted = listed[index - 1] if index <= len(listed) else ""
    view = next((v for v in await desk.tabs() if wanted and v.target_id == wanted), None)
    return (view, "") if view is not None else (None, GONE_TEXT.format(index=index))


async def switch_tab(desk: Any, listed: tuple[str, ...], args: TabIn) -> TabOutcome:
    view, why = await _still_there(desk, listed, args.index)
    if view is None:
        return TabOutcome(why, listed)
    await desk.switch_tab(view.target_id)
    return TabOutcome(SWITCHED_TEXT.format(index=args.index, host=_host(view)), listed, moved=True)


async def close_tab(desk: Any, listed: tuple[str, ...], args: TabIn) -> TabOutcome:
    view, why = await _still_there(desk, listed, args.index)
    if view is None:
        return TabOutcome(why, listed)
    if await desk.close_tab(view.target_id) == "blanked":
        return TabOutcome(BLANKED_TEXT, listed, moved=True)
    left = tuple(target for target in listed if target != view.target_id)
    return TabOutcome(CLOSED_TEXT.format(index=args.index, host=_host(view)), left, moved=True)
