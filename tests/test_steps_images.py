"""C3 Task 9: the step loop attaches only the newest look's screenshot, and older looks say so in words.

The stored turns are never changed; only the request the model sees is."""

from __future__ import annotations

from roost.llm.types import (
    SCREENSHOT_GONE,
    SCREENSHOT_SHOWN,
    ChatTurn,
    ImagePart,
    ModelRequest,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)
from roost.talk.steps import step_loop, with_screen


class _Recording:
    def __init__(self, steps):
        self._steps = list(steps)
        self.requests: list[ModelRequest] = []

    async def stream(self, request):
        self.requests.append(request)
        for event in self._steps.pop(0):
            yield event


class _LookRunner:
    """A runner whose ``look`` hands back a new image each time, as ``ComputerUse`` will (Task 12)."""

    block = None
    parked = None

    def __init__(self):
        self._image: bytes | None = None
        self._n = 0

    async def run(self, call):
        if call.name == "look":
            self._n += 1
            self._image = f"jpeg-{self._n}".encode()
            return f"<untrusted_page>look {self._n}</untrusted_page> {SCREENSHOT_SHOWN}"
        return "ok"

    def newest_image(self):
        return self._image


def _look(n):
    return ToolCallRequested(id=f"l{n}", name="look", arguments={})


async def _run(steps, runner):
    model = _Recording(steps)
    first = (ChatTurn("user", "check the price"),)

    async def on_delta(text):
        return None

    await step_loop(
        model=model, tool_runner=runner, max_steps=8, deadline_s=60, on_delta=on_delta,
        request_for=lambda added: ModelRequest(system="", turns=first + added, tools=(), model="m"),
    )
    return model.requests


async def test_only_the_newest_look_is_attached():
    requests = await _run([
        [_look(1), TurnDone("tool_use")],
        [_look(2), TurnDone("tool_use")],
        [TextDelta("Done."), TurnDone("end_turn")],
    ], _LookRunner())
    assert requests[0].images == ()
    # Each rides right after its own look turn, so the steps after it share the same prompt prefix (tokens,
    # owner 2026-11-07).
    assert requests[1].images == (ImagePart("image/jpeg", b"jpeg-1", after_turn=1),)
    assert requests[2].images == (ImagePart("image/jpeg", b"jpeg-2", after_turn=2),)


async def test_older_looks_render_as_not_shown():
    requests = await _run([
        [_look(1), TurnDone("tool_use")],
        [_look(2), TurnDone("tool_use")],
        [TextDelta("Done."), TurnDone("end_turn")],
    ], _LookRunner())
    looks = [turn for turn in requests[2].turns if turn.tool_name == "look"]
    assert SCREENSHOT_GONE in looks[0].text and SCREENSHOT_SHOWN not in looks[0].text
    assert SCREENSHOT_SHOWN in looks[1].text and SCREENSHOT_GONE not in looks[1].text
    assert "look 1" in looks[0].text  # the summary text stays; only the image mark changes


async def test_a_runner_without_images_leaves_requests_alone():
    class _Plain:
        block = None
        parked = None

        async def run(self, call):
            return "ok"

    requests = await _run([[TextDelta("Hi."), TurnDone("end_turn")]], _Plain())
    assert requests[0].images == ()
    assert requests[0].turns == (ChatTurn("user", "check the price"),)


def test_with_screen_never_changes_the_stored_turns():
    shown = ChatTurn("tool", f"a {SCREENSHOT_SHOWN}", tool_call_id="l1", tool_name="look")
    turns = (ChatTurn("user", "hi"), shown)
    request = ModelRequest(system="", turns=turns, tools=(), model="m")
    out = with_screen(request, None)
    assert out.images == ()
    assert SCREENSHOT_GONE in out.turns[1].text  # no image this step: even the newest look says not shown
    assert shown.text == f"a {SCREENSHOT_SHOWN}" and request.turns == turns


def test_with_screen_keeps_the_newest_look_shown_when_an_image_rides():
    old = ChatTurn("tool", f"a {SCREENSHOT_SHOWN}", tool_call_id="l1", tool_name="look")
    new = ChatTurn("tool", f"b {SCREENSHOT_SHOWN}", tool_call_id="l2", tool_name="look")
    other = ChatTurn("tool", f"c {SCREENSHOT_SHOWN}", tool_call_id="r1", tool_name="read_page")
    request = ModelRequest(system="", turns=(old, new, other), tools=(), model="m")
    out = with_screen(request, b"img")
    assert out.images == (ImagePart("image/jpeg", b"img", after_turn=1),)
    assert out.turns[0].text == f"a {SCREENSHOT_GONE}"
    assert out.turns[1].text == f"b {SCREENSHOT_SHOWN}"
    assert out.turns[2] is other  # not a look turn: untouched
