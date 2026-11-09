"""``FakeComputerPage``: a scripted page on a fake Linux computer, for the C3 tests and the E2E (Task 8).

A script is a set of named states. Each has an address, a title, its controls (``PageTarget``), its page text, an
optional open dialog, and where a click, typing or a key leads: ``on_click`` maps a control's text to the next state,
``on_type`` names the state after typing into a field, ``on_key`` maps a key ("Enter") to the next state. The first
state is the start. Fast pages: ``areas`` are readable parts with their own text (``fake_area``), ``link_urls`` maps a
link's text to its full address, and ``files`` maps an address (a ``blob:`` one too) to the bytes the browser would fetch or read there.

Its screenshots are real JPEGs drawn with Pillow (each control a labelled rectangle), so the mask and the E2E see
real pixels. ``FakeDesk(..., computer="linux").serve_screen(script)`` makes it the desk's ``page()``, and the desk's
``send_input`` drives it. Typed text is kept only as a real page keeps it: in its text box, in memory, so ``box_text``
can read it back (owner, 2026-10-27); ``lossy_typing`` makes that many typings lose their last letter. ``paste_text``
is ``type``'s paste (owner, 2026-11-01): ``pasted_lengths`` counts each one, ``paste_works = False`` refuses them.
"""

from __future__ import annotations

import io
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from PIL import Image, ImageDraw

from roost.computer_use.marks import PageArea
from roost.computer_use.models import Box, PageTarget
from roost.constants import CU_JPEG_QUALITY, CU_KEYS
from roost.desk import PageText, ScreenInput
from roost.desk.box_text import NO_PASTE, ONE_LINE, PASTED, has_line_breaks
from roost.desk.cdp import CdpReplyError
from roost.desk.page_fetch import FetchFailed, FileTooBig
from roost.desk.page_geometry import WindowGeometry, viewport_to_screen
from roost.desk.page_targets import same_label, shrink_to_probe, visible_part
from roost.desk.ready import LifecycleView

FAKE_VIEW_W, FAKE_VIEW_H = 1280, 690                  # Xvnc 1280x800 less the browser's toolbar
FAKE_GEOMETRY = WindowGeometry(left=0, top=0, outer_w=1280, outer_h=800, inner_w=FAKE_VIEW_W, inner_h=FAKE_VIEW_H)
_VIEWPORT = Box(x=0, y=0, width=FAKE_VIEW_W, height=FAKE_VIEW_H)
_QUIET = LifecycleView(navigating=False, idle_since_ms=10_000.0)
_PAGE_BG, _BOX_BG, _INK, _DIALOG_BG = (250, 250, 250), (210, 225, 245), (20, 20, 20), (255, 240, 200)
_KEY_OF_KEYSYM = MappingProxyType({keysym: name for name, keysym in CU_KEYS.items()})
_ONE_LINE_TAG = "input"


def fake_target(kind: str, text: str, x: float, y: float, width: float = 140, height: float = 36,
                **flags: object) -> PageTarget:
    """A control for a script; ``flags`` set any other ``PageTarget`` field (``editable``, ``in_dialog``…)."""
    base = PageTarget(node_id=zlib.crc32(f"{kind}|{text}|{x}|{y}".encode()) % 1_000_000 + 1, kind=kind, text=text, tag="",
                      input_type="", box=Box(x, y, width, height), form_method="", form_submit_text="",
                      is_form_submit=False, link_host="", in_dialog="", in_consent=False, cross_origin_frame=False,
                      editable=kind == "field", secret_field=False, searchish=False, expands=False)
    return replace(base, **flags)  # type: ignore[arg-type]


@dataclass(frozen=True)
class FakeArea:
    area: PageArea
    text: str


def fake_area(role: str, name: str, text: str, x: float, y: float, width: float, height: float) -> FakeArea:
    """A readable area for a script: its text may be far longer than its box shows (scrolled out of view)."""
    node_id = zlib.crc32(f"area|{role}|{name}".encode()) % 1_000_000 + 1_000_000
    return FakeArea(PageArea(node_id=node_id, role=role, name=name, chars=len(text), box=Box(x, y, width, height)),
                    text)


@dataclass(frozen=True)
class FakeScreenState:
    url: str
    title: str
    targets: tuple[PageTarget, ...] = ()
    text: str = ""
    dialog: str = ""                                   # the open dialog's title; it covers controls not in it
    on_click: Mapping[str, str] = field(default_factory=dict)
    on_type: str = ""
    on_key: Mapping[str, str] = field(default_factory=dict)
    password_field: bool = False
    areas: tuple[FakeArea, ...] = ()
    link_urls: Mapping[str, str] = field(default_factory=dict)
    files: Mapping[str, bytes] = field(default_factory=dict)


class FakeComputerPage:
    """A ``PageDriver`` over a script. ``apply`` takes the desk's screen inputs (screen pixels)."""

    def __init__(self, states: Mapping[str, FakeScreenState], *, minimized: bool = False) -> None:
        if not states:
            raise ValueError("a screen script needs at least one state")
        self._states = MappingProxyType(dict(states))
        for name, state in self._states.items():
            for nxt in (*state.on_click.values(), *state.on_key.values(), *([state.on_type] if state.on_type else [])):
                if nxt not in self._states:
                    raise ValueError(f"state {name!r} leads to an unknown state {nxt!r}")
        self.state_name = next(iter(self._states))
        self.minimized = minimized
        # Another tab is in front of this one: Chromium never answers a screenshot of a background tab (the real
        # CDP call times out), so a screenshot raises until ``geometry`` brings this tab to the front.
        self.behind = False
        self.geometry_calls = 0
        self.typed_lengths: tuple[int, ...] = ()
        self.fetched: tuple[str, ...] = ()
        self.blobs_read: tuple[str, ...] = ()
        self._focused: PageTarget | None = None
        self._boxes: Mapping[int, str] = MappingProxyType({})   # what each text box holds
        self._selected: int | None = None                        # the box whose text is all selected
        self.lossy_typing = 0
        self.paste_works = True                                  # False: every paste is no paste (another frame)
        self.pasted_lengths: tuple[int, ...] = ()
        # use_saved_login: the password the browser has saved for this page (None: none), whether its list is open
        # after ArrowDown in a text box, and whether Enter filled it. The password itself never leaves the fake.
        self.saved_password: str | None = None
        self._saved_list_open = False
        self.saved_login_filled = False

    @property
    def state(self) -> FakeScreenState:
        return self._states[self.state_name]

    def _go(self, name: str) -> None:
        if name and name != self.state_name:
            self.state_name = name
            self._focused = None

    def _has_focus(self, target: PageTarget) -> bool:
        return self._focused is not None and self._focused.node_id == target.node_id

    async def targets(self) -> tuple[PageTarget, ...]:
        shown = ((t, visible_part(t.box, _VIEWPORT)) for t in self.state.targets)
        return tuple(replace(t, box=box, focused=self._has_focus(t)) for t, box in shown if box is not None)

    async def target_for(self, node_id: int) -> PageTarget | None:
        return next((t for t in await self.targets() if t.node_id == node_id), None)

    async def areas(self) -> tuple[PageArea, ...]:
        shown = ((a.area, visible_part(a.area.box, _VIEWPORT) if a.area.box else None) for a in self.state.areas)
        return tuple(replace(area, box=box) for area, box in shown)

    async def area_text(self, node_id: int | None) -> str | None:
        if node_id is None:
            return "\n".join([self.state.text, *(a.text for a in self.state.areas)])
        return next((a.text for a in self.state.areas if a.area.node_id == node_id), None)

    async def link_url(self, node_id: int) -> str:
        target = await self.target_for(node_id)
        return self.state.link_urls.get(target.text, "") if target is not None else ""

    async def fetch(self, url: str, max_bytes: int) -> bytes:
        """What the bot's browser would fetch at ``url`` (``FileTooBig`` past ``max_bytes``)."""
        self.fetched = (*self.fetched, url)
        return self._file(url, max_bytes)

    async def read_blob(self, url: str, max_bytes: int) -> bytes:
        """What the page would read from its ``blob:`` file at ``url`` (``FileTooBig`` past ``max_bytes``)."""
        self.blobs_read = (*self.blobs_read, url)
        return self._file(url, max_bytes)

    def _file(self, url: str, max_bytes: int) -> bytes:
        data = self.state.files.get(url)
        if data is None:
            raise FetchFailed(f"no file at {url}")
        if len(data) > max_bytes:
            raise FileTooBig(url)
        return data

    async def find(self, text: str, kind: str, nth: int) -> PageTarget | None:
        matches = [t for t in await self.targets() if same_label(t.text, text) and kind in ("any", t.kind)]
        return matches[nth - 1] if 0 < nth <= len(matches) else None

    async def node_at(self, x: int, y: int) -> PageTarget | None:
        hits = [t for t in await self.targets() if _inside(t.box, x, y)]
        on_top = [t for t in hits if t.in_dialog == self.state.dialog] if self.state.dialog else hits
        return on_top[-1] if on_top else None

    async def focused(self) -> PageTarget | None:
        return replace(self._focused, focused=True) if self._focused is not None else None

    async def covering(self, target: PageTarget) -> str:
        if self.state.dialog and target.in_dialog != self.state.dialog:
            return self.state.dialog
        return ""

    async def screenshot(self, *, probe: bool = False) -> bytes:
        if self.behind:
            raise CdpReplyError("Page.captureScreenshot timed out: the tab is not in front")
        jpeg = self.draw()
        return shrink_to_probe(jpeg) if probe else jpeg

    async def geometry(self) -> WindowGeometry:
        self.geometry_calls += 1
        self.minimized = False                          # brought up and restored, like the real window
        self.behind = False                             # Page.bringToFront
        return FAKE_GEOMETRY

    async def url(self) -> str:
        return self.state.url

    async def title(self) -> str:
        return self.state.title

    async def facts(self) -> PageText:
        state = self.state
        return PageText(url=state.url, title=state.title, text=state.text, truncated=False,
                        password_field=state.password_field)

    async def lifecycle(self) -> LifecycleView:
        return _QUIET

    async def busy_marks(self) -> int:
        return 0

    async def box_text(self, node_id: int) -> str | None:
        target = await self.target_for(node_id)
        return self._boxes.get(node_id, "") if target is not None and target.editable else None

    async def select_box(self, node_id: int) -> bool:
        if await self.box_text(node_id) is None:
            return False
        self._selected = node_id
        return True

    async def paste_text(self, node_id: int, text: str) -> str:
        """The whole text into the focused box at once, as ``Input.insertText`` would: a one-line box (tag "input")
        refuses line breaks; a box that isn't the focused one, or ``paste_works`` off, is no paste."""
        target = await self.target_for(node_id)
        if not self.paste_works or target is None or not target.editable or not self._has_focus(target):
            return NO_PASTE
        if target.tag == _ONE_LINE_TAG and has_line_breaks(text):
            return ONE_LINE
        self.pasted_lengths = (*self.pasted_lengths, len(text))
        self._type(text)
        return PASTED

    def fill_box(self, text: str, node_id: int | None = None) -> None:
        """A test's draft already in a box (the focused one when no id is given)."""
        key = node_id if node_id is not None else (self._focused.node_id if self._focused is not None else 0)
        self._boxes = MappingProxyType({**self._boxes, key: text})

    def _type(self, text: str) -> None:
        if self._focused is None or not self._focused.editable:
            return
        key = self._focused.node_id
        if self.lossy_typing > 0 and text:
            self.lossy_typing, text = self.lossy_typing - 1, text[:-1]
        held = "" if self._selected == key else self._boxes.get(key, "")
        self._boxes, self._selected = MappingProxyType({**self._boxes, key: held + text}), None
        self._go(self.state.on_type)

    def draw(self) -> bytes:
        image = Image.new("RGB", (FAKE_VIEW_W, FAKE_VIEW_H), _PAGE_BG)
        pen = ImageDraw.Draw(image)
        pen.text((16, 8), self.state.title, fill=_INK)
        for target in self.state.targets:
            box = target.box
            fill = _DIALOG_BG if target.in_dialog else _BOX_BG
            pen.rectangle((box.x, box.y, box.x + box.width, box.y + box.height), fill=fill, outline=_INK)
            pen.text((box.x + 6, box.y + 6), target.text, fill=_INK)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=CU_JPEG_QUALITY)
        return out.getvalue()

    # -- input from the desk (screen pixels) ------------------------------------------------------------

    async def apply(self, action: ScreenInput) -> None:
        if action.verb == "click":
            await self._click(_to_viewport(action.x, action.y))
        elif action.verb == "type":
            self.typed_lengths = (*self.typed_lengths, len(action.text))
            self._type(action.text)
        elif action.verb == "key":
            if self._saved_login_key(action.key) or self._backspace(action.key):
                return
            self._go(self.state.on_key.get(_KEY_OF_KEYSYM.get(action.key, action.key), ""))

    def _backspace(self, keysym: str) -> bool:
        """BackSpace in a focused box: empties it when all its text is selected, else drops the last letter."""
        if keysym != "BackSpace" or self._focused is None or not self._focused.editable:
            return False
        key = self._focused.node_id
        held = "" if self._selected == key else self._boxes.get(key, "")[:-1]
        self._boxes, self._selected = MappingProxyType({**self._boxes, key: held}), None
        return True

    def _saved_login_key(self, keysym: str) -> bool:
        """The browser's saved-login list: ArrowDown in a text box opens it when a password is saved, Enter then
        fills it. True when the list took the key."""
        if keysym == "Down" and self.saved_password and self._focused is not None and self._focused.editable \
                and not self._focused.secret_field:
            self._saved_list_open = True
            return True
        if keysym == "Return" and self._saved_list_open:
            self._saved_list_open, self.saved_login_filled = False, True
            return True
        self._saved_list_open = False
        return False

    async def password_filled(self) -> bool:
        return self.saved_login_filled

    async def _click(self, point: tuple[int, int] | None) -> None:
        target = await self.node_at(*point) if point else None
        if target is None:
            return
        self._focused, self._selected = target, None
        self._go(self.state.on_click.get(target.text, ""))


def _inside(box: Box, x: int, y: int) -> bool:
    return box.x <= x <= box.x + box.width and box.y <= y <= box.y + box.height


def _to_viewport(x: int, y: int) -> tuple[int, int] | None:
    vx, vy = x - FAKE_GEOMETRY.left - FAKE_GEOMETRY.border, y - FAKE_GEOMETRY.page_top
    return (vx, vy) if 0 <= vx < FAKE_VIEW_W and 0 <= vy < FAKE_VIEW_H else None


def screen_point(x: int, y: int) -> tuple[int, int]:
    """Where viewport ``(x, y)`` is on the fake computer's screen."""
    return viewport_to_screen((x, y), FAKE_GEOMETRY)


def script(states: Sequence[tuple[str, FakeScreenState]]) -> Mapping[str, FakeScreenState]:
    """An ordered script; the first state is the start."""
    return MappingProxyType(dict(states))
