"""Resolve a click, typing or key press from the live page into a frozen ``ActResolution`` (C3 design §6.1).

The gate judges only what this returns, never the model's arguments: the control comes from the page (found by its
words and kind, or the node at a point), and so do its box, its class (``commit_class``), the host a link would go
to, whether a dialog covers it, and the crop for the card. Typed text is checked against the approved sources here
(``text_ok``) and flagged for contact details and secrets (``text_flags``)."""

from __future__ import annotations

from roost.computer_use.commit_words import commit_class, is_text_box
from roost.computer_use.gate_rules import ACT_TEXTS
from roost.computer_use.look import crop_for, mask_fields
from roost.computer_use.models import ActResolution, ClickIn, PageTarget, PressKeyIn, TypeIn
from roost.computer_use.text_source import ApprovedTexts, text_flags, text_is_approved
from roost.computer_use.texts import INDEX_KEY_TEXT
from roost.desk.stuck import host_of_url

FILE_PICKER_TEXT = "That opens a file picker, and I don't upload files."
OUTSIDE_TEXT = "That point is outside the page, so I didn't touch it."
_FILE_INPUT = "file"


def _refusal_for(target: PageTarget | None) -> str:
    if target is None:
        return ""
    if target.card_field:
        return ACT_TEXTS.card
    if target.secret_field:
        return ACT_TEXTS.password
    if target.input_type == _FILE_INPUT:
        return FILE_PICKER_TEXT
    return ""


async def _crop(page, target: PageTarget | None) -> bytes:
    """The card's picture of the control; card and password boxes near it are painted grey (Pay card, P7)."""
    if target is None:
        return b""
    secret = [t.box for t in await page.targets() if t.secret_field]
    shot = await page.screenshot()
    return crop_for(mask_fields(shot, secret) if secret else shot, target.box)


async def _inside_view(page, point: tuple[int, int]) -> bool:
    geo = await page.geometry()
    return 0 <= point[0] < geo.inner_w and 0 <= point[1] < geo.inner_h


async def resolve_click(page, args: ClickIn, url: str, aimed: PageTarget | None = None) -> ActResolution:
    """``aimed``: the live control a look's number named (``roost/computer_use/aim.py``), None when it is gone."""
    host = host_of_url(url)
    if args.index is not None:
        target = aimed
        point = target.box.center() if target is not None else None
    elif args.target is not None:
        # A card's re-run names its stored control (``aimed``); else the words find it.
        target = aimed or await page.find(args.target.text, args.target.kind, args.target.nth)
        point = target.box.center() if target is not None else None
    else:
        point = (int(args.x or 0), int(args.y or 0))
        if not await _inside_view(page, point):
            return ActResolution("click", url, host, None, point, "", "", "unknown", refusal=OUTSIDE_TEXT)
        target = await page.node_at(*point)
    if target is None:
        return ActResolution("click", url, host, None, point, "", "", "unknown")
    covered = await page.covering(target)
    return ActResolution(
        tool="click", url=url, host=host, target=target, point=point, covered_by=covered,
        nav_host=target.link_host, commit=commit_class(target), refusal=_refusal_for(target),
        crop=await _crop(page, target),
    )


async def _typing_target(page, index: int | None, aimed: PageTarget | None) -> PageTarget | None:
    """The box an index named (clicked first when it lacks the focus), else the focused control."""
    return aimed if index is not None else await page.focused()


async def _covered(page, target: PageTarget | None, index: int | None) -> str:
    """An indexed box is clicked first, so a dialog over it is a miss, as for a click."""
    return await page.covering(target) if index is not None and target is not None else ""


async def resolve_type(page, args: TypeIn, url: str, texts: ApprovedTexts,
                       aimed: PageTarget | None = None) -> ActResolution:
    target = await _typing_target(page, args.index, aimed)
    approved = args.source is not None and text_is_approved(args.text, args.source, texts)
    return ActResolution(
        tool="type", url=url, host=host_of_url(url), target=target,
        point=target.box.center() if target is not None else None,
        covered_by=await _covered(page, target, args.index), nav_host="",
        commit="unknown" if target is None else "browsing",
        text_ok=approved, text_flags=text_flags(args.text, texts.contacts),
        refusal=_refusal_for(target), crop=await _crop(page, target),
    )


def _key_refusal(target: PageTarget | None, index: int | None) -> str:
    if index is not None and target is not None and not target.secret_field and not is_text_box(target):
        return INDEX_KEY_TEXT
    return _refusal_for(target)


async def resolve_key(page, args: PressKeyIn, url: str, aimed: PageTarget | None = None) -> ActResolution:
    target = await _typing_target(page, args.index, aimed)
    return ActResolution(
        tool="press_key", url=url, host=host_of_url(url), target=target,
        point=target.box.center() if target is not None else None,
        covered_by=await _covered(page, target, args.index), nav_host="",
        commit=commit_class(target, key=args.key), refusal=_key_refusal(target, args.index),
        crop=await _crop(page, target),
    )
