"""The control socket's teach observer: one per control socket, shown every input message it forwards.

It keeps the input state (``read_input``) always, and reads the page only while the bot is being taught. A
capture is awaited before the message is forwarded, at most ``TEACH_CAPTURE_TIMEOUT_S``, so a press is read before
it changes the page. Any failure records nothing and is logged by bot id and exception type name alone: it never
stops the socket and never names what was on the screen."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from roost.constants import TEACH_CAPTURE_TIMEOUT_S
from roost.desk.page_geometry import WindowGeometry
from roost.desk.rfb import RfbMessage
from roost.teach.capture import capture
from roost.teach.input import InputState, Intent, NamedKey, Press, read_input
from roost.teach.models import TeachStep

logger = logging.getLogger(__name__)


class TeachRecorder(Protocol):
    def recording(self, bot_id: str) -> bool: ...
    async def record(self, bot_id: str, step: TeachStep) -> bool: ...


class TeachObserver:
    def __init__(self, recorder: TeachRecorder, bot_id: str, page: Any) -> None:
        self._recorder = recorder
        self._bot_id = bot_id
        self._page = page
        self._state = InputState()
        self._geometry: WindowGeometry | None = None
        self._address_bar = False

    async def __call__(self, message: RfbMessage) -> None:
        self._state, intent = read_input(message, self._state)
        if intent is None or self._page is None or not self._recorder.recording(self._bot_id):
            return
        try:
            async with asyncio.timeout(TEACH_CAPTURE_TIMEOUT_S):
                step = await self._capture(intent)
            await self._recorder.record(self._bot_id, step)
        except Exception as exc:     # never the message: a page's words stay out of the log
            logger.info("teach capture skipped for bot %s: %s", self._bot_id, type(exc).__name__)

    async def _capture(self, intent: Intent) -> TeachStep:
        if self._geometry is None:
            self._geometry = await self._page.geometry()
        step = await capture(self._page, intent, self._geometry, address_bar=self._address_bar)
        if isinstance(intent, Press):
            self._address_bar = step.kind == "browser"
        elif isinstance(intent, NamedKey) and intent.name == "Enter":
            self._address_bar = False
        return step
