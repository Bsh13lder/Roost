"""C3 Task 7: the bot waits until a page is ready (quiet network, stable layout, no spinner)."""

from __future__ import annotations

import io

from cu_page_helpers import FakeCdp, load_fixture, session_of, solid_jpeg
from PIL import Image, ImageDraw

from roost.constants import CU_READY_DIFF_MAX, CU_READY_STABLE_MS
from roost.desk import PageText
from roost.desk.page_targets import CdpPageDriver
from roost.desk.ready import (
    BUSY_SELECTOR, NOT_READY, READY_WORLD, LifecycleView, count_busy_marks, probes_differ, read_lifecycle,
    ready_now, wait_ready,
)

QUIET = LifecycleView(navigating=False, idle_since_ms=CU_READY_STABLE_MS + 1)


def _half_changed() -> bytes:
    image = Image.new("RGB", (320, 200), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((0, 0, 159, 199), fill=(0, 0, 0))
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def test_ready_needs_quiet_network_stable_layout_and_no_spinner():
    assert ready_now(QUIET, 0, 0.0)
    assert not ready_now(LifecycleView(navigating=True, idle_since_ms=5000), 0, 0.0)
    assert not ready_now(LifecycleView(navigating=False, idle_since_ms=None), 0, 0.0)
    assert not ready_now(LifecycleView(navigating=False, idle_since_ms=CU_READY_STABLE_MS - 1), 0, 0.0)
    assert not ready_now(QUIET, 1, 0.0)                         # a spinner shows
    assert not ready_now(QUIET, 0, CU_READY_DIFF_MAX + 0.001)   # the layout still moves
    assert not ready_now(QUIET, 0, None)
    assert ready_now(QUIET, 0, CU_READY_DIFF_MAX)


def test_probe_diff_counts_changed_pixels():
    white = solid_jpeg(320, 200, (255, 255, 255))
    assert probes_differ(white, white) == 0.0
    assert 0.45 <= probes_differ(white, _half_changed()) <= 0.55
    assert probes_differ(white, solid_jpeg(320, 200, (250, 250, 250))) == 0.0   # JPEG noise is not a change


class _Page:
    """A PageDriver stub for wait_ready: shots alternate until ``settle_after`` reads have happened."""

    def __init__(self, clock, settle_after: int | None) -> None:
        self.clock, self.settle_after, self.shots = clock, settle_after, 0

    async def screenshot(self, *, probe: bool = False) -> bytes:
        assert probe
        self.shots += 1
        settled = self.settle_after is not None and self.shots > self.settle_after
        return solid_jpeg(320, 200, (255, 255, 255)) if settled or self.shots % 2 else _half_changed()

    async def lifecycle(self) -> LifecycleView:
        return QUIET

    async def busy_marks(self) -> int:
        return 0


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_still_changing_after_the_timeout():
    clock = _Clock()
    page = _Page(clock, settle_after=None)
    assert await wait_ready(page, 2.0, clock=clock, sleep=clock.sleep) == "still changing"
    assert clock.now - 100.0 >= 2.0 and clock.now - 100.0 < 3.0
    assert set(clock.sleeps) == {CU_READY_STABLE_MS / 1000, 0.1}


async def test_ready_once_the_page_settles():
    clock = _Clock()
    page = _Page(clock, settle_after=4)
    assert await wait_ready(page, 10.0, clock=clock, sleep=clock.sleep) == "ready"
    assert page.shots == 6


class _ReadyCdp(FakeCdp):
    def __init__(self, fixture, value, busy_ids=(), boxes=None):
        super().__init__(fixture)
        self.value, self.busy_ids, self.busy_boxes = value, list(busy_ids), boxes or {}

    def _Page_getFrameTree(self, params):
        return {"frameTree": {"frame": {"id": "F"}}}

    def _Page_createIsolatedWorld(self, params):
        return {"executionContextId": 4}

    def _Runtime_evaluate(self, params):
        return {"result": {"value": self.value}}

    def _DOM_getDocument(self, params):
        return {"root": {"nodeId": 1}}

    def _DOM_querySelectorAll(self, params):
        return {"nodeIds": self.busy_ids}

    def _DOM_getBoxModel(self, params):
        if "nodeId" in params:
            box = self.busy_boxes.get(params["nodeId"])
            if box is None:
                from roost.desk.cdp import CdpReplyError
                raise CdpReplyError("no box")
            x, y, w, h = box
            return {"model": {"border": [x, y, x + w, y, x + w, y + h, x, y + h]}}
        return super()._DOM_getBoxModel(params)


async def test_lifecycle_is_read_in_an_isolated_world():
    client = _ReadyCdp(load_fixture("login"), ["complete", 900.5])
    assert await read_lifecycle(client, "S") == LifecycleView(navigating=False, idle_since_ms=900.5)
    world = next(p for m, p in client.calls if m == "Page.createIsolatedWorld")
    assert world["worldName"] == READY_WORLD
    assert next(p for m, p in client.calls if m == "Runtime.evaluate")["contextId"] == 4
    assert (await read_lifecycle(_ReadyCdp(load_fixture("login"), ["loading", 3.0]), "S")).navigating
    assert await read_lifecycle(_ReadyCdp(load_fixture("login"), "hostile"), "S") == NOT_READY


async def test_busy_marks_count_only_what_shows_in_the_viewport():
    boxes = {7: (10, 10, 40, 40), 8: (10, 5000, 40, 40)}          # 9 has no box (display: none)
    client = _ReadyCdp(load_fixture("login"), None, busy_ids=[7, 8, 9], boxes=boxes)
    assert await count_busy_marks(client, "S", 1280, 690) == 1
    assert next(p for m, p in client.calls if m == "DOM.querySelectorAll")["selector"] == BUSY_SELECTOR
    assert client.methods()[-1] == "DOM.disable"
    many = _ReadyCdp(load_fixture("login"), None, busy_ids=list(range(100, 200)))
    assert await count_busy_marks(many, "S", 1280, 690) == 100


async def _no_facts() -> PageText:
    return PageText(url="", title="", text="", truncated=False)


async def test_the_cdp_page_driver_reads_lifecycle_and_busy_marks():
    client = _ReadyCdp(load_fixture("login"), ["complete", 2000], busy_ids=[7], boxes={7: (0, 0, 10, 10)})
    driver = CdpPageDriver(session_of(client), _no_facts)
    assert (await driver.lifecycle()).idle_since_ms == 2000
    assert await driver.busy_marks() == 1
