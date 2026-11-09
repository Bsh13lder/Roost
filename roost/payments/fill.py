"""Typing a card into the page's own card boxes (the Pay card, P5, P8).

``card_boxes`` reads what the page asks for: each card part once, in page order, or ``FRAMED_TEXT`` when the page
has no card box of its own but a cross-origin frame (Stripe, Adyen…), which Roost can't type into. ``fill_card``
clicks each box, checks the focus is that same box, selects what it holds, types the part through the keeper's input
route (text on stdin only) and reads the box back: the digits (or the name) must be what was typed. Values stay in
this call's arguments: never logged, stored or put in an event. Errors are ``PayRefused`` with fixed words."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.computer_use.commit_words import normalise
from roost.computer_use.models import PageTarget
from roost.desk import ScreenInput
from roost.desk.page_geometry import viewport_to_screen
from roost.desk.page_targets import FRAME_KIND
from roost.desk.stuck import host_of_url
from roost.payments.texts import (
    FRAMED_TEXT, LIST_BOX_TEXT, MISSING_TEXT, NO_BOXES_TEXT, NOT_TYPED_TEXT, PART_WORDS, WRONG_PAGE_TEXT,
)

_LIST_TAG = "select"
_ERASE_KEY = "BackSpace"
_FOUR_DIGIT_YEAR = ("yyyy", "aaaa")


class PayRefused(Exception):
    """Nothing more was typed, and ``detail`` says why in fixed words."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class CardValues:
    """Checked values (``checks.py``): number digits, MM/YY, the name, the security code."""

    number: str
    exp: str
    name: str
    cvc: str

    def __repr__(self) -> str:                      # a traceback or a log line can never show a card
        return "CardValues(…)"


def card_boxes(targets: tuple[PageTarget, ...]) -> tuple[PageTarget, ...]:
    """Each card part's first box, in page order; ``PayRefused`` for a framed card box or a list box."""
    seen: dict[str, PageTarget] = {}
    for target in targets:
        if target.card_field and not target.cross_origin_frame and target.card_field not in seen:
            seen[target.card_field] = target
    boxes = tuple(seen.values())
    if not boxes and any(t.kind == FRAME_KIND or t.cross_origin_frame for t in targets):
        raise PayRefused(FRAMED_TEXT)
    if any(box.tag == _LIST_TAG for box in boxes):
        raise PayRefused(LIST_BOX_TEXT)
    return boxes


def part_value(box: PageTarget, values: CardValues) -> str:
    month, year = values.exp.split("/") if "/" in values.exp else ("", "")
    four = any(word in normalise(box.text).replace(" ", "") for word in _FOUR_DIGIT_YEAR)
    value = {"number": values.number, "exp": values.exp, "exp_month": month,
             "exp_year": f"20{year}" if four and year else year, "cvc": values.cvc, "name": values.name}[box.card_field]
    if not value:
        raise PayRefused(MISSING_TEXT.format(part=PART_WORDS[box.card_field]))
    return value


def _same(held: str | None, value: str, part: str) -> bool:
    if held is None:
        return False
    if part == "name":
        return " ".join(held.split()).casefold() == " ".join(value.split()).casefold()
    return "".join(c for c in held if c.isdigit()) == "".join(c for c in value if c.isdigit())


async def _focus(page: Any, desk: Any, box: PageTarget, host: str) -> Any:
    """Click the box and check the focus is that same card box on ``host``; returns the window geometry."""
    geo = await page.geometry()
    x, y = viewport_to_screen(box.box.center(), geo)
    await desk.send_input(ScreenInput("move", x, y, window=geo.window_rect))
    await desk.send_input(ScreenInput("click", x, y, window=geo.window_rect))
    now = await page.focused()
    if now is None or now.node_id != box.node_id or now.card_field != box.card_field:
        raise PayRefused(NOT_TYPED_TEXT)
    if host_of_url(await page.url()).lower() != host.lower():        # a redirect between boxes: type nothing more
        raise PayRefused(WRONG_PAGE_TEXT.format(host=host))
    await page.select_box(box.node_id)
    return geo


async def _fill_box(page: Any, desk: Any, box: PageTarget, value: str, host: str) -> None:
    geo = await _focus(page, desk, box, host)
    await desk.send_input(ScreenInput("type", text=value, window=geo.window_rect))
    if not _same(await page.box_text(box.node_id), value, box.card_field):
        raise PayRefused(NOT_TYPED_TEXT)


async def fill_card(page: Any, desk: Any, values: CardValues, host: str) -> tuple[str, ...]:
    """Type every card part the page asks for on ``host``; returns the parts typed (for the audit)."""
    boxes = card_boxes(await page.targets())
    typed: list[str] = []
    for box in boxes:
        await _fill_box(page, desk, box, part_value(box, values), host)
        typed.append(box.card_field)
    return tuple(typed)


async def clear_card(page: Any, desk: Any, host: str) -> int:
    """Empty every card box on ``host`` that holds text (a Pay that didn't click, or a fill that stopped), so a card
    never stays in the page for the bot to see or send. Returns how many boxes were emptied."""
    if page is None or host_of_url(await page.url()).lower() != host.lower():
        return 0
    emptied = 0
    for box in (t for t in await page.targets() if t.card_field and not t.cross_origin_frame):
        if not await page.box_text(box.node_id):
            continue
        geo = await _focus(page, desk, box, host)
        await desk.send_input(ScreenInput("key", key=_ERASE_KEY, window=geo.window_rect))
        emptied += 1
    return emptied


def needs_card(targets: tuple[PageTarget, ...]) -> tuple[str, ...]:
    """The parts the Pay card shows fields for (``exp_month``/``exp_year`` show as one expiry)."""
    try:
        boxes = card_boxes(targets)
    except PayRefused:
        return ()
    parts = {"exp" if box.card_field.startswith("exp") else box.card_field for box in boxes}
    return tuple(part for part in ("number", "exp", "name", "cvc") if part in parts)


__all__ = ["CardValues", "PayRefused", "card_boxes", "clear_card", "fill_card", "needs_card", "part_value",
           "NO_BOXES_TEXT"]
