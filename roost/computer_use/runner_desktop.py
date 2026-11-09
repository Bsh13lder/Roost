"""The desktop half of the screen loop (full computer, Step 1, D1): another app than the browser is in front.

``ComputerUse`` (``roost/computer_use/runner.py``) mixes this in. A look is the whole screen with the browser's
windows black; clicks (a point only), typing, keys and scrolls go anywhere but the browser, free under every loop
rule; ``open_app`` opens a fixed app or an installed package."""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel

from roost.computer_use import desktop
from roost.computer_use import session as loop
from roost.computer_use.lines import act_line, open_line
from roost.computer_use.models import ClickIn, LookIn, OpenAppIn, ReadPdfIn, ReadTextIn, ScrollIn, TypeIn, WaitReadyIn
from roost.computer_use.outcome import CuOutcome
from roost.computer_use.scroll import scroll_pieces
from roost.computer_use.texts import NO_SCREEN_TEXT, READ_DESKTOP_TEXT
from roost.constants import CU_DESKTOP_SETTLE_S, CU_KEYS, CU_TYPE_TEXT_CONTROLS
from roost.desk import FrontWindow, InputRefusedByComputer, ScreenInput
from roost.desk.stuck import Block
from roost.llm.types import SCREENSHOT_SHOWN, ToolCallRequested
from roost.talk.verdict import GateContext


class DesktopActs:
    """Mixed into ``ComputerUse``: every attribute it reads (``_desk``, ``_gate``, ``state``…) is the runner's."""

    async def _on_desktop(self, call: ToolCallRequested, args: BaseModel | None, ctx: GateContext,
                          front: FrontWindow) -> CuOutcome:
        if isinstance(args, LookIn):
            await self._announce(act_line("look", None, {}))
            shot = await desktop.desktop_look(self._desk, front)
            self.state = loop.after_look(self.state, self._epoch())
            self._image = shot.image
            return CuOutcome(f"{shot.text}\n{SCREENSHOT_SHOWN}", looked=True)
        if isinstance(args, (ReadTextIn, ReadPdfIn)):
            return CuOutcome(READ_DESKTOP_TEXT)
        if isinstance(args, WaitReadyIn):
            await self._announce(act_line("wait_ready", None, call.arguments))
            await self._sleep(min(args.timeout_s, CU_DESKTOP_SETTLE_S))
            self.state = loop.after_wait(self.state)
            return CuOutcome(desktop.WAITED_TEXT)
        if isinstance(args, ScrollIn):
            return await self._screen_scroll(args, call)
        return await self._screen_act(call, args, ctx)

    async def _screen_scroll(self, args: ScrollIn, call: ToolCallRequested) -> CuOutcome:
        if args.area is not None:
            return CuOutcome(desktop.TARGET_TEXT)           # areas are a page's, never the desktop's
        x, y = desktop.clamp((args.at["x"], args.at["y"])) if args.at else desktop.screen_center()
        for notches in scroll_pieces(args.amount if args.direction == "down" else -args.amount):
            await self._send(ScreenInput("scroll", x, y, notches=notches, screen=True), x, y, "scroll")
        self.state = loop.after_scroll(self.state)
        await self._announce(act_line("scroll", None, call.arguments))
        return CuOutcome(desktop.SCROLLED_TEXT.format(direction=args.direction))

    async def _screen_act(self, call: ToolCallRequested, args: BaseModel, ctx: GateContext) -> CuOutcome:
        """A click, type or key press with another window in front: no page, judged free (D1) by the gate."""
        self._require_hands()
        point = None
        if getattr(args, "index", None) is not None:
            return CuOutcome(desktop.TARGET_TEXT)          # a look's numbers are page controls, never the desktop's
        if isinstance(args, TypeIn) and any(char in CU_TYPE_TEXT_CONTROLS for char in args.text):
            return CuOutcome(desktop.LINE_BREAKS_TEXT)     # only a page takes a paste; keys would press Enter
        if isinstance(args, ClickIn):
            if args.target is not None:
                return CuOutcome(desktop.TARGET_TEXT)
            point = (args.x or 0, args.y or 0)
            if not desktop.on_screen(point):
                return CuOutcome(desktop.OUTSIDE_SCREEN_TEXT)
        r = desktop.screen_resolution(call.name, point)  # type: ignore[arg-type]
        self._resolved = r
        if self._stale_click(call, r):                   # a covered dialog's closers are a page's, never the desktop's
            return CuOutcome(loop.LOOK_FIRST_TEXT)
        verdict = await self._gate.decide(self._run.user_id, self._run.bot_id, call.name, dict(call.arguments),
                                          replace(ctx, fence=self._fence), act=r)
        self._audited = True
        if verdict.decision != "do":
            return CuOutcome(verdict.text or NO_SCREEN_TEXT)
        try:
            await self._screen_input(call, point)
        except InputRefusedByComputer as exc:
            if exc.word != "in_browser":
                raise
            return await self._screen_miss(call)
        digest = loop.typed_digest(str(call.arguments.get("text", ""))) if call.name == "type" else None
        self.state = loop.after_act(self.state, r, str(call.arguments.get("expect", "")), typed_digest=digest)
        line = self.lines(call, r)
        await self._announce(line)
        return CuOutcome(desktop.SCREEN_DONE_TEXT.format(line=line))

    async def _screen_input(self, call: ToolCallRequested, point: tuple[int, int] | None) -> None:
        if point is not None:
            x, y = point
            await self._input(ScreenInput("move", x, y, screen=True))
            await self._send(ScreenInput("click", x, y, screen=True), x, y, "click")
        elif call.name == "type":
            await self._input(ScreenInput("type", text=str(call.arguments.get("text", "")), screen=True))
        else:
            await self._input(ScreenInput("key", key=CU_KEYS[str(call.arguments.get("key"))], screen=True))

    async def _screen_miss(self, call: ToolCallRequested) -> CuOutcome:
        """A point on Brave's window from the desktop is a miss; the second on the same point is Stuck."""
        self.state, last = loop.after_miss(self.state, loop.aim_key(call.name, call.arguments))
        if not last:
            return CuOutcome(desktop.IN_BROWSER_TEXT)
        block = Block(reason="asked", url="", host="", note=desktop.IN_BROWSER_NOTE)
        return CuOutcome(desktop.IN_BROWSER_TEXT, block=block)

    async def _open_app(self, args: OpenAppIn) -> CuOutcome:
        refusal = await desktop.app_refusal(self._run.config, self._run.user_id, self._run.bot_id, args.app)
        if refusal is not None:
            return CuOutcome(refusal)
        self._require_hands()
        try:
            await self._desk.open_app(args.app, held=self._held())
        except InputRefusedByComputer as exc:
            if exc.word != "no_window":
                raise
            return CuOutcome(desktop.NO_WINDOW_TEXT.format(app=args.app))
        self.state = loop.after_open(self.state)
        line = open_line(args.app)
        await self._announce(line)
        return CuOutcome(desktop.OPENED_TEXT.format(line=line))
