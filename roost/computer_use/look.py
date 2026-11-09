"""``look``: what the model sees of its page (C3 Task 8, design §3).

- **The picture** is the page viewport only (no desktop, no address bar) as a JPEG. Every editable field's box is
  painted over (``mask_fields``) before the model gets it: what you typed under Take control, autofill and passwords
  never reach the model. ``fit_jpeg`` keeps it within ``CU_VIEW_MAX_*`` and ``CU_IMAGE_MAX_BYTES``.
- **The summary** is one ``<untrusted_page>`` wrapper, escaped like ``read_page``'s: facts first (URL, title, ready,
  an open dialog, a cookie notice and its buttons, the fields the bot typed into as "holds what you typed: yes/no",
  then "You expected: … Check it now."), then the controls, numbered for the act tools' ``index``
  (``[3] kind "text" at (x, y)``, ``· focused`` for the control with the keyboard focus, ``· commits`` when the
  commit test says so), then the page text cut to ``CU_LOOK_TEXT_CHARS``. It never holds a field's value.
- **The numbers** (fast pages, slice 2) ride back as ``PageMarks``; ``picture=False`` skips the screenshot, and
  ``glance`` is the text-only summary an act's result ends with (a shorter page text), read after the page settled.
- **Every look runs the stuck detector** (``detect_block``): a sign-in page, a code check or a human check is a block.
- Before the screenshot, ``page.geometry()`` brings Chromium's window up (a minimized one is restored), so the page
  the bot sees is the page it clicks (amendment 2026-10-21).
"""

from __future__ import annotations

import html
import io
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PIL import Image, ImageDraw

from roost.computer_use.commit_words import commit_class
from roost.computer_use.marks import PageArea, PageMarks
from roost.desk.card_redact import hide_card_numbers
from roost.computer_use.models import Box, PageTarget
from roost.constants import (
    CU_CROP_MAX_BYTES,
    CU_CROP_MAX_H,
    CU_CROP_MAX_W,
    CU_CROP_PAD_PX,
    CU_GLANCE_TARGETS_MAX,
    CU_GLANCE_TEXT_CHARS,
    CU_IMAGE_MAX_BYTES,
    CU_JPEG_QUALITY,
    CU_LABEL_SHOWN_CHARS,
    CU_LOOK_TARGETS_MAX,
    CU_LOOK_TEXT_CHARS,
    CU_MASK_FILL,
    CU_VIEW_MAX_H,
    CU_VIEW_MAX_W,
)
from roost.desk import PageText
from roost.desk.ready import ready_now
from roost.desk.stuck import Block, detect_block

if TYPE_CHECKING:
    from roost.desk.page_targets import PageDriver

_QUALITY_STEP = 10
_QUALITY_FLOOR = 20
_SHRINK = 0.75
_NOT_COMMITTING = frozenset({"browsing", "consent"})
_READY, _CHANGING = "ready", "still changing"


@dataclass(frozen=True)
class LookResult:
    text: str
    image: bytes | None              # None: a text-only look or a glance
    url: str
    block: Block | None
    marks: PageMarks = PageMarks.empty()


class LookState(Protocol):
    """What ``look`` reads of the loop's state (``LoopState``, Task 11)."""

    @property
    def expect(self) -> str: ...
    @property
    def typed(self) -> Mapping[str, str]: ...          # field label -> sha256 of what the bot typed there


# Says whether the field still holds what the bot typed (compared by hash inside the page; the value never leaves).
HoldsTyped = Callable[[str, str], Awaitable[bool]]


def _save(image: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=quality)
    return out.getvalue()


def _squeeze(image: Image.Image, max_w: int, max_h: int, max_bytes: int) -> bytes:
    """Within ``max_w`` x ``max_h`` and ``max_bytes``: quality steps down first, then the picture shrinks."""
    image = image.copy()
    image.thumbnail((max_w, max_h))
    while True:
        for quality in range(CU_JPEG_QUALITY, _QUALITY_FLOOR - 1, -_QUALITY_STEP):
            data = _save(image, quality)
            if len(data) <= max_bytes:
                return data
        image = image.resize((max(1, int(image.width * _SHRINK)), max(1, int(image.height * _SHRINK))))


def mask_fields(jpeg: bytes, boxes: Sequence[Box]) -> bytes:
    """Paint ``CU_MASK_FILL`` over every box (viewport px = screenshot px at device scale 1)."""
    with Image.open(io.BytesIO(jpeg)) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle((box.x, box.y, box.x + box.width, box.y + box.height), fill=CU_MASK_FILL)
    return _save(image, CU_JPEG_QUALITY)


def fit_jpeg(jpeg: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as opened:
        return _squeeze(opened.convert("RGB"), CU_VIEW_MAX_W, CU_VIEW_MAX_H, CU_IMAGE_MAX_BYTES)


def crop_for(jpeg: bytes, box: Box) -> bytes:
    """The control and ``CU_CROP_PAD_PX`` around it, for the Ask card; within the crop's size and byte caps."""
    with Image.open(io.BytesIO(jpeg)) as opened:
        image = opened.convert("RGB")
    left, top = max(0, int(box.x) - CU_CROP_PAD_PX), max(0, int(box.y) - CU_CROP_PAD_PX)
    right = min(image.width, int(box.x + box.width) + CU_CROP_PAD_PX)
    bottom = min(image.height, int(box.y + box.height) + CU_CROP_PAD_PX)
    if right <= left or bottom <= top:
        left, top, right, bottom = 0, 0, min(image.width, CU_CROP_MAX_W), min(image.height, CU_CROP_MAX_H)
    return _squeeze(image.crop((left, top, right, bottom)), CU_CROP_MAX_W, CU_CROP_MAX_H, CU_CROP_MAX_BYTES)


CARD_BOX_MARK = " · card box (never type here; the owner pays on the Pay card)"


def _quote(text: str) -> str:
    return '"' + " ".join(text.split())[:CU_LABEL_SHOWN_CHARS] + '"'


def _target_line(index: int, target: PageTarget) -> str:
    x, y = target.box.center()
    focused = " · focused" if target.focused else ""
    commits = "" if commit_class(target) in _NOT_COMMITTING else " · commits"
    card = CARD_BOX_MARK if target.card_field else ""
    return f"[{index}] {target.kind} {_quote(target.text)} at ({x}, {y}){focused}{commits}{card}"


def _dialog_lines(targets: Sequence[PageTarget]) -> list[str]:
    consent = [t for t in targets if t.in_consent]
    dialogs = list(dict.fromkeys(t.in_dialog for t in targets if t.in_dialog and not t.in_consent))
    lines = [f"Dialog open: {_quote(title)}" for title in dialogs]
    if consent:
        lines.append("Cookie notice showing, with: " + ", ".join(_quote(t.text) for t in consent if t.text))
    return lines


def _area_lines(areas: Sequence[PageArea]) -> list[str]:
    if not areas:
        return []
    head = "Areas (read_text area=n reads all of one, also what is scrolled out of view):"
    return [head, *(f"area {i}: {a.role} {_quote(a.name)} (~{a.chars} characters)" for i, a in enumerate(areas, 1))]


GLANCE_MORE = "; look lists them all"


def summary_text(url: str, title: str, ready: str, targets: Sequence[PageTarget], facts: PageText,
                 typed: Mapping[str, bool], expect: str, notes: Sequence[str], *,
                 text_chars: int = CU_LOOK_TEXT_CHARS, areas: Sequence[PageArea] = (),
                 targets_max: int = CU_LOOK_TARGETS_MAX) -> str:
    """The facts, the controls and the page text in one escaped ``<untrusted_page>`` wrapper. Field values never
    appear: a typed field says only yes or no."""
    lines = [f"URL: {url}", f"Title: {title}", f"Page: {ready}", *_dialog_lines(targets)]
    lines += [f"Field {_quote(label)} holds what you typed: {'yes' if held else 'no'}" for label, held in typed.items()]
    lines += list(notes)
    if expect:
        lines.append(f"You expected: {expect} Check it now.")
    shown = targets[:targets_max]
    more = GLANCE_MORE if targets_max < CU_LOOK_TARGETS_MAX else ""
    lines.append(f"Controls ({len(shown)} of {len(targets)}{more}):" if len(targets) > len(shown) else "Controls:")
    lines += [_target_line(i, t) for i, t in enumerate(shown, start=1)] or ["(none in view)"]
    lines += _area_lines(areas)
    cut = " (cut short: read_text reads the rest)" if len(facts.text) > text_chars else ""
    lines += [f"Page text{cut}:", facts.text[:text_chars]]
    body = html.escape(hide_card_numbers("\n".join(lines)), quote=True)
    return f'<untrusted_page url="{html.escape(url, quote=True)}">{body}</untrusted_page>'


async def _typed(state: LookState, holds: HoldsTyped | None) -> dict[str, bool]:
    if holds is None:
        return {label: False for label in state.typed}
    return {label: await holds(label, digest) for label, digest in state.typed.items()}


async def _read(page: "PageDriver", state: LookState, holds: HoldsTyped | None, notes: Sequence[str],
                *, picture: bool, text_chars: int, targets_max: int = CU_LOOK_TARGETS_MAX) -> LookResult:
    targets = await page.targets()
    areas = await page.areas()
    image = fit_jpeg(mask_fields(await page.screenshot(), [t.box for t in targets if t.editable])) if picture else None
    facts = await page.facts()
    url = await page.url() or facts.url
    ready = _READY if ready_now(await page.lifecycle(), await page.busy_marks(), 0.0) else _CHANGING
    text = summary_text(url, facts.title, ready, targets, facts, await _typed(state, holds), state.expect, notes,
                        text_chars=text_chars, areas=areas, targets_max=targets_max)
    marks = PageMarks(url=url, controls=tuple(targets[:targets_max]), areas=areas)
    return LookResult(text=text, image=image, url=url, block=detect_block(facts), marks=marks)


async def look(page: "PageDriver", state: LookState, *, holds: HoldsTyped | None = None,
               notes: Sequence[str] = (), picture: bool = True) -> LookResult:
    """One look: bring the window up, take the masked picture (unless ``picture`` is False), read the facts and
    number the controls, run the stuck detector."""
    await page.geometry()
    return await _read(page, state, holds, notes, picture=picture, text_chars=CU_LOOK_TEXT_CHARS)


async def glance(page: "PageDriver", state: LookState, *, notes: Sequence[str] = ()) -> LookResult:
    """The text-only look an act's result ends with: the same facts and numbers, fewer controls and a shorter
    page text (every glance stays in the run's transcript)."""
    return await _read(page, state, None, notes, picture=False, text_chars=CU_GLANCE_TEXT_CHARS,
                       targets_max=CU_GLANCE_TARGETS_MAX)
