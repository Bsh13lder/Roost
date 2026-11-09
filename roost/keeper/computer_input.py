"""The keeper's computer input route: ``POST /desks/{bot_id}/computer/input`` (C3 Task 4, security review b).

One click, move, key, type or scroll on a bot's Linux computer screen. The body is a strict pydantic union
(``extra="forbid"``, strict types, integer bounds, keys from the ``CU_KEYS`` keysyms only) plus the bot's window
as the desk read it over CDP. The keeper turns it into one fixed argv, ``docker exec -i --user 10002:10002
roost-computer-<id> /usr/local/bin/roost-input <verb> <ints> --window <left> <top> <width> <height>``, run with no
shell; roost-input acts only in the one Chromium window that matches. Typing gets time for its length
(``roost/computer_use/timing.py``), and the keeper waits longer than roost-input's own deadline. Text to type goes **only on stdin**: it is never in the argv, a log line, the audit,
an error or a response. ``roost-input`` checks everything again inside the computer (Design meets code 6).

Refusals: unsigned 401, a bad id 400, a bad body 422, ``held`` 409 (the user holds Take control), not running 409
``asleep`` (never wakes the computer), more than ``CU_INPUT_MAX_PER_SECOND`` a second 429 ``too_fast``,
``roost-input``'s own ``not_chromium`` / ``outside`` 409, anything else 500 ``input failed``. The audit gets only
``computer_input``, the bot id, the verb and a result word.

Full computer, Step 1 (``docs/plans/2026-10-23-roost-full-computer.md``): the same route answers ``front``
(``{"front": "brave"|"other", "window": [l, t, w, h]|null}``) and ``browsers`` (``{"windows": [[l, t, w, h], ...]}``,
rects only), runs ``open <app>`` (audited as the verb and the app id only), and sends an act with ``"screen": true``
and no window as ``<verb> <ints> --screen``: anywhere on the screen but in Brave (roost-input's ``in_browser``,
409). A package app's ``no_window`` is 409 too.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from roost.computer_use.timing import keeper_input_timeout_s
from roost.constants import (
    COMPUTER_UID,
    CU_APP_NAME_RE,
    CU_BROWSER_WINDOWS_MAX,
    CU_INPUT_MAX_PER_SECOND,
    CU_KEYS,
    CU_OPEN_APPS,
    CU_SCROLL_NOTCHES_PER_INPUT,
    CU_TYPE_MAX_CHARS,
    CU_VIEW_MAX_H,
    CU_VIEW_MAX_W,
)
from roost.keeper.auth import require_signed_body
from roost.keeper.computers import container_name
from roost.keeper.workspaces import _RunOutcome

logger = logging.getLogger(__name__)

INPUT_BIN = "/usr/local/bin/roost-input"
KEYSYMS = frozenset(CU_KEYS.values())
_USER = f"{COMPUTER_UID}:{COMPUTER_UID}"
_X_MAX = CU_VIEW_MAX_W - 1
_Y_MAX = CU_VIEW_MAX_H - 1
_RATE_WINDOW_S = 1.0
_REFUSED_EXIT = 3
_REFUSED_WORDS = frozenset({"not_chromium", "outside", "in_browser", "no_window"})
_AUDIT_ACTION = "computer_input"
_FAILED = "input failed"
_BAD_KEY = "not an allowed key"
_BAD_TEXT = "text must not hold control characters"
_BAD_NOTCHES = "notches must not be 0"
_WINDOW_FLAG = "--window"
_SCREEN_FLAG = "--screen"
_BAD_APP = "not an app this computer can open"
_APP_NAME = re.compile(CU_APP_NAME_RE)
_QUERY_VERBS = frozenset({"front", "browsers"})
_FRONT_OTHER = "other"
_FRONT_BRAVE = "brave"


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ClickAction(_Action):
    verb: Literal["click"]
    x: int = Field(ge=0, le=_X_MAX)
    y: int = Field(ge=0, le=_Y_MAX)
    count: Literal[1, 2] = 1


class MoveAction(_Action):
    verb: Literal["move"]
    x: int = Field(ge=0, le=_X_MAX)
    y: int = Field(ge=0, le=_Y_MAX)


class KeyAction(_Action):
    verb: Literal["key"]
    key: str

    @field_validator("key")
    @classmethod
    def _listed(cls, key: str) -> str:
        if key not in KEYSYMS:
            raise ValueError(_BAD_KEY)
        return key


class TypeAction(_Action):
    verb: Literal["type"]
    text: str = Field(min_length=1, max_length=CU_TYPE_MAX_CHARS)

    @field_validator("text")
    @classmethod
    def _no_controls(cls, text: str) -> str:
        # A newline or a tab would press Enter or Tab, which are their own, separately judged keys.
        if any(unicodedata.category(char) == "Cc" for char in text):
            raise ValueError(_BAD_TEXT)
        return text


class ScrollAction(_Action):
    verb: Literal["scroll"]
    x: int = Field(ge=0, le=_X_MAX)
    y: int = Field(ge=0, le=_Y_MAX)
    notches: int = Field(ge=-CU_SCROLL_NOTCHES_PER_INPUT, le=CU_SCROLL_NOTCHES_PER_INPUT)

    @field_validator("notches")
    @classmethod
    def _not_zero(cls, notches: int) -> int:
        if notches == 0:
            raise ValueError(_BAD_NOTCHES)
        return notches


class FrontAction(_Action):
    verb: Literal["front"]


class BrowsersAction(_Action):
    verb: Literal["browsers"]


class OpenAction(_Action):
    verb: Literal["open"]
    app: str = Field(min_length=2, max_length=63)

    @field_validator("app")
    @classmethod
    def _an_app(cls, app: str) -> str:
        if app not in CU_OPEN_APPS and not _APP_NAME.fullmatch(app):
            raise ValueError(_BAD_APP)
        return app


InputAction = Annotated[
    ClickAction | MoveAction | KeyAction | TypeAction | ScrollAction | FrontAction | BrowsersAction | OpenAction,
    Field(discriminator="verb"),
]
_NO_WINDOW_ACTIONS = (FrontAction, BrowsersAction, OpenAction)


class WindowRect(_Action):
    """The bot's Chromium window on the screen (CDP's bounds); it may sit partly off the screen."""

    left: int = Field(ge=-CU_VIEW_MAX_W, le=CU_VIEW_MAX_W)
    top: int = Field(ge=-CU_VIEW_MAX_H, le=CU_VIEW_MAX_H)
    width: int = Field(ge=1, le=2 * CU_VIEW_MAX_W)
    height: int = Field(ge=1, le=2 * CU_VIEW_MAX_H)


class InputBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: InputAction
    window: WindowRect | None = None
    screen: bool = False                 # anywhere but Brave (roost-input --screen); never with a window
    held: bool = False

    @model_validator(mode="after")
    def _one_place(self) -> "InputBody":
        if isinstance(self.action, _NO_WINDOW_ACTIONS):
            if self.window is not None or self.screen:
                raise ValueError("front, browsers and open take no window and no screen flag")
        elif self.screen == (self.window is not None):
            raise ValueError("an act needs either the bot's window or the screen flag, not both")
        return self


def _argv_tail(action: InputAction) -> list[str]:
    if isinstance(action, ClickAction):
        return [str(action.x), str(action.y), str(action.count)]
    if isinstance(action, MoveAction):
        return [str(action.x), str(action.y)]
    if isinstance(action, KeyAction):
        return [action.key]
    if isinstance(action, ScrollAction):
        return [str(action.x), str(action.y), str(action.notches)]
    if isinstance(action, OpenAction):
        return [action.app]
    return []                           # type: the text goes on stdin, never here


def _place(action: InputAction, window: WindowRect | None, screen: bool) -> list[str]:
    if isinstance(action, _NO_WINDOW_ACTIONS):
        return []
    if screen:
        return [_SCREEN_FLAG]
    if window is None:
        raise ValueError("an act needs the bot's window or the screen flag")
    return [_WINDOW_FLAG, str(window.left), str(window.top), str(window.width), str(window.height)]


def build_input_argv(bot_id: str, action: InputAction, window: WindowRect | None, *,
                     screen: bool = False) -> list[str]:
    """The one argv for ``action``: in ``window``, on the screen (``screen``), or a question / ``open`` with
    neither. A bot id that is not a UUID4 raises ``ValueError``."""
    return ["docker", "exec", "-i", "--user", _USER, container_name(bot_id), INPUT_BIN, action.verb,
            *_argv_tail(action), *_place(action, window, screen)]


def _rect(words: Sequence[str]) -> list[int] | None:
    """Four integers that fit a ``WindowRect``, or None."""
    if len(words) != 4 or not all(w.lstrip("-").isdigit() and w.isascii() for w in words):
        return None
    left, top, width, height = (int(w) for w in words)
    try:
        WindowRect(left=left, top=top, width=width, height=height)
    except ValidationError:
        return None
    return [left, top, width, height]


def parse_front(stdout: bytes) -> dict[str, object] | None:
    """``other`` or ``brave L T W H``, exactly one line; anything else is None (a failure)."""
    lines = stdout.decode("utf-8", "replace").splitlines()
    if len(lines) != 1:
        return None
    words = lines[0].split(" ")
    if words == [_FRONT_OTHER]:
        return {"front": _FRONT_OTHER, "window": None}
    rect = _rect(words[1:]) if words[0] == _FRONT_BRAVE else None
    return None if rect is None else {"front": _FRONT_BRAVE, "window": rect}


def parse_browsers(stdout: bytes) -> dict[str, object] | None:
    """At most ``CU_BROWSER_WINDOWS_MAX`` lines of four integers; anything else is None (a failure)."""
    rects = [_rect(line.split(" ")) for line in stdout.decode("utf-8", "replace").splitlines()]
    if len(rects) > CU_BROWSER_WINDOWS_MAX or any(r is None for r in rects):
        return None
    return {"windows": rects}


def _answer_of(verb: str, stdout: bytes) -> dict[str, object] | None:
    if verb == "front":
        return parse_front(stdout)
    if verb == "browsers":
        return parse_browsers(stdout)
    return {"done": True}


def _app_of(action: InputAction) -> str | None:
    return action.app if isinstance(action, OpenAction) else None


def input_timeout_s(action: InputAction) -> float:
    """How long the keeper waits: longer than roost-input's own deadline, which grows with the text."""
    return keeper_input_timeout_s(len(action.text) if isinstance(action, TypeAction) else 0)


def input_stdin(action: InputAction) -> bytes | None:
    """UTF-8 text for ``type``; ``None`` (stdin closed) for every other verb."""
    return action.text.encode("utf-8") if isinstance(action, TypeAction) else None


InputRunner = Callable[[Sequence[str], bytes | None, float], Awaitable[_RunOutcome]]


async def run_input(argv: Sequence[str], stdin: bytes | None, timeout_s: float) -> _RunOutcome:
    """Run ``argv`` with no shell, ``stdin`` written to it, bounded by ``timeout_s`` (killed after)."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(stdin or b""), timeout=timeout_s)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return _RunOutcome(returncode=-1, stdout=b"", stderr=b"", timed_out=True)
    return _RunOutcome(returncode=proc.returncode or 0, stdout=stdout, stderr=stderr, timed_out=False)


class InputRateLimiter:
    """At most ``max_per_second`` inputs per bot in any sliding second. In memory, per keeper process."""

    def __init__(self, max_per_second: int = CU_INPUT_MAX_PER_SECOND,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._max = max_per_second
        self._clock = clock
        self._recent: dict[str, tuple[float, ...]] = {}

    def allow(self, bot_id: str) -> bool:
        now = self._clock()
        recent = tuple(t for t in self._recent.get(bot_id, ()) if now - t < _RATE_WINDOW_S)
        if len(recent) >= self._max:
            self._recent = {**self._recent, bot_id: recent}
            return False
        self._recent = {**self._recent, bot_id: (*recent, now)}
        return True


def _parse_body(body: bytes) -> InputBody:
    try:
        return InputBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        # include_input=False: a refused text is never echoed back.
        raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False,
                                                               include_context=False)) from exc


def _outcome_word(outcome: _RunOutcome) -> str:
    """``ok``, ``roost-input``'s own refusal word, or ``error``. Never reads anything but a fixed word."""
    if outcome.timed_out:
        return "error"
    if outcome.returncode == 0:
        return "ok"
    word = outcome.stderr.decode("utf-8", "replace").strip()
    if outcome.returncode == _REFUSED_EXIT and word in _REFUSED_WORDS:
        return word
    return "error"


def _answer(app: FastAPI, bot_id: str, parsed: InputBody, stdout: bytes) -> dict[str, object]:
    """The reply. A question's answer is checked word by word; a strange one is a failure. Questions are not
    audited when they work (they run before every look and act); every act is."""
    verb = parsed.action.verb
    found = _answer_of(verb, stdout)
    if found is None:
        logger.warning("computer input for bot %s gave a strange %s answer", bot_id, verb)
        app.state.audit.record(_AUDIT_ACTION, bot_id, "error", verb=verb)
        raise HTTPException(status_code=500, detail=_FAILED)
    if verb not in _QUERY_VERBS:
        app.state.audit.record(_AUDIT_ACTION, bot_id, "ok", verb=verb, app=_app_of(parsed.action))
    return found


def input_routes(app: FastAPI) -> APIRouter:
    router = APIRouter()
    app.state.input_runner = run_input
    app.state.input_limiter = InputRateLimiter()

    def refuse(bot_id: str, verb: str, word: str, status: int) -> HTTPException:
        app.state.audit.record(_AUDIT_ACTION, bot_id, word, verb=verb)
        return HTTPException(status_code=status, detail=word)

    async def run(bot_id: str, parsed: InputBody) -> tuple[str, bytes]:
        action = parsed.action
        try:
            outcome = await app.state.input_runner(
                build_input_argv(bot_id, action, parsed.window, screen=parsed.screen), input_stdin(action),
                input_timeout_s(action),
            )
        except OSError:
            logger.error("computer input for bot %s could not run (%s)", bot_id, action.verb)
            return "error", b""
        word = _outcome_word(outcome)
        if word == "error":
            logger.warning("computer input for bot %s failed (%s, exit %s)", bot_id, action.verb, outcome.returncode)
        return word, outcome.stdout

    @router.post("/desks/{bot_id}/computer/input")
    async def computer_input(bot_id: str, body: bytes = Depends(require_signed_body)):
        try:
            container_name(bot_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bot_id must be a UUID4") from exc
        parsed = _parse_body(body)
        verb = parsed.action.verb
        if parsed.held:
            raise refuse(bot_id, verb, "held", 409)
        if app.state.computers.state(bot_id) != "running":
            raise refuse(bot_id, verb, "asleep", 409)
        if not app.state.input_limiter.allow(bot_id):
            raise refuse(bot_id, verb, "too_fast", 429)
        app.state.computers.touch(bot_id)
        word, stdout = await run(bot_id, parsed)
        if word in _REFUSED_WORDS:
            raise refuse(bot_id, verb, word, 409)
        if word != "ok":
            app.state.audit.record(_AUDIT_ACTION, bot_id, "error", verb=verb)
            raise HTTPException(status_code=500, detail=_FAILED)
        return _answer(app, bot_id, parsed, stdout)

    return router
