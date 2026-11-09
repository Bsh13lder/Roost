"""The numbers of the newest look (fast pages, docs/plans/2026-10-26-roost-fast-pages.md, slice 2).

A look (or an act's glance) numbers the controls it shows, 1 to ``CU_LOOK_TARGETS_MAX``, and the page's readable
areas. ``PageMarks`` keeps that numbering in the runner's memory only, for the newest look: a later look replaces it.
A number is never trusted on its own: the runner reads the numbered node again on the live page and acts only when
``same_mark`` says it is still the same control (and the page is still at the same address). The gate then judges
the resolution read from the page, exactly as for an act aimed by words or a point."""

from __future__ import annotations

from dataclasses import dataclass

from roost.computer_use.models import Box, PageTarget

# What must not change between the look and the act: the node itself, and everything the gate reads of it.
_KEPT = ("node_id", "kind", "text", "tag", "input_type", "link_host", "in_dialog", "in_consent",
         "cross_origin_frame", "editable", "secret_field", "visible_text", "form_method", "is_form_submit")


@dataclass(frozen=True)
class PageArea:
    """A part of the page with its own text (a list, a grid, a dialog, a message pane), for ``read_text``."""

    node_id: int
    role: str
    name: str
    chars: int                   # how much readable text it holds (scrolled-out text included)
    box: Box | None = None       # its visible part, None when none of it shows


@dataclass(frozen=True)
class PageMarks:
    url: str
    controls: tuple[PageTarget, ...] = ()
    areas: tuple[PageArea, ...] = ()

    @classmethod
    def empty(cls) -> "PageMarks":
        return cls(url="")

    def control(self, index: int) -> PageTarget | None:
        return self.controls[index - 1] if 0 < index <= len(self.controls) else None

    def area(self, index: int) -> PageArea | None:
        return self.areas[index - 1] if 0 < index <= len(self.areas) else None


def same_mark(stored: PageTarget, live: PageTarget) -> bool:
    """The live node is still the control the look numbered (its box may have moved)."""
    return all(getattr(stored, name) == getattr(live, name) for name in _KEPT)


def page_address(url: str) -> str:
    """The address without its ``#fragment``: scrolling to a section is the same page."""
    return url.split("#", 1)[0]


def same_page(a: str, b: str) -> bool:
    return bool(a) and page_address(a) == page_address(b)
