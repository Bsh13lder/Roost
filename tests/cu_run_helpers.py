"""Helpers for the C3 runner tests (not a test module): a Linux bot with a scripted shop page, a ``ComputerUse``
over it, and a ``ToolRunner`` that hands it the screen tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from roost.approvals.models import ApprovalState
from roost.bots.models import Avatar, Bot, BotDraft, BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.computer_use.runner import ComputerUse, CuRun, ScreenKit
from roost.computer_use.session import ComputerUseLease
from roost.desk.control import ControlLock
from roost.desk.fake import FakeDesk
from roost.desk.fake_cu import FakeComputerPage, FakeScreenState, fake_target, script
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.talk.gate import Gate, GateContext
from roost.talk.store import TalkStore
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner

AVATAR = Avatar("round", "#22c55e", "none")
YOUR_MESSAGE = "On shop.example please find wool socks and put a note: blue wool socks size 42"

_CONTROLS = (
    fake_target("field", "Note", 100, 100, width=300, tag="input", input_type="text"),
    fake_target("link", "Jobs", 450, 100, tag="a", link_host="shop.example"),
    fake_target("button", "Buy now", 450, 200, tag="button"),
    fake_target("link", "Partner deals", 450, 300, width=160, tag="a", link_host="partner.example"),
    fake_target("field", "Password", 100, 400, width=300, tag="input", input_type="password", secret_field=True),
)
SHOP = script([
    ("shop", FakeScreenState(url="https://shop.example/", title="Shop", targets=_CONTROLS, text="Socks for sale",
                             on_click={"Jobs": "jobs", "Buy now": "bought", "Partner deals": "partner"},
                             on_type="noted", on_key={"Enter": "jobs"})),
    ("noted", FakeScreenState(url="https://shop.example/", title="Shop", targets=_CONTROLS, text="Note saved",
                              on_click={"Jobs": "jobs", "Buy now": "bought"})),
    ("jobs", FakeScreenState(url="https://shop.example/jobs", title="Jobs", text="No jobs today")),
    ("bought", FakeScreenState(url="https://shop.example/thanks", title="Thanks", text="Order 1234 placed")),
    ("partner", FakeScreenState(url="https://partner.example/", title="Partner", text="Deals")),
])


class Frames:
    """An events stand-in that keeps every published frame."""

    def __init__(self) -> None:
        self.frames: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, event: dict[str, Any]) -> int:
        self.frames.append((user_id, dict(event)))
        return len(self.frames)

    def pointers(self) -> list[dict[str, Any]]:
        return [frame for _, frame in self.frames if frame.get("type") == "computer_pointer"]


async def no_sleep(_: float) -> None:
    return None


@dataclass
class CuRig:
    cfg: Any
    user_id: str
    bot: Bot
    thread_id: str
    desk: FakeDesk
    page: FakeComputerPage
    gate: Gate
    events: Frames
    leases: ComputerUseLease
    control: ControlLock
    lines: list[str] = field(default_factory=list)

    async def announce(self, line: str) -> None:
        self.lines.append(line)

    def computer(self, run_id: str = "run-1") -> ComputerUse:
        return ComputerUse(CuRun(self.cfg, self.user_id, self.bot.id, self.thread_id, run_id), desk=self.desk,
                           gate=self.gate, events=self.events, leases=self.leases, control=self.control,
                           announce=self.announce, sleep=no_sleep)

    def tool_runner(self, *, cards: bool = True, mode: str = "ask", tainted: bool = True,
                    approval: bool = True, run_id: str = "run-1", user_started: bool = False,
                    sees_records: bool = False, site_fresh: bool = False,
                    own_sites: frozenset[str] = frozenset()) -> ToolRunner:
        state = ApprovalState(mode, frozenset(), cards) if approval else None   # type: ignore[arg-type]
        return ToolRunner(
            user_id=self.user_id, bot_id=self.bot.id, desk=self.desk, gate=self.gate, activity=ActivityBoard(),
            events=EventHub(self.cfg), allowed=frozenset(CATALOG), tainted=tainted, control=self.control,
            cards=cards, thread_id=self.thread_id, approval=state, run_id=run_id,
            screen=ScreenKit(self.cfg, self.leases, sleep=no_sleep), user_started=user_started,
            sees_records=sees_records, site_fresh=site_fresh, own_sites=own_sites,
        )


def ctx(*, mode: str = "ask", cards: bool = True, tainted: bool = True) -> GateContext:
    return GateContext(allowed=frozenset(CATALOG), tainted=tainted,
                       approval=ApprovalState(mode, frozenset(), cards))  # type: ignore[arg-type]


def call(name: str, **arguments: Any) -> ToolCallRequested:
    return ToolCallRequested(id=f"c-{name}", name=name, arguments=arguments)


async def step(cu: ComputerUse, name: str, context: GateContext | None = None, **arguments: Any):
    cu.new_step()
    return await cu.handle(call(name, **arguments), context or ctx())


async def run_step(runner: ToolRunner, name: str, **arguments: Any) -> str:
    runner.begin_step()
    return await runner.run(call(name, **arguments))


async def make_cu_rig(cfg, message: str = YOUR_MESSAGE, *, username: str = "alice", screen=None) -> CuRig:
    user = await register_user(cfg, username, "pw-123456")
    bots = BotStore(cfg)
    bot = await bots.create(user.id, BotDraft(name="Shopper", job="shops", instructions="", avatar=AVATAR))
    bot = await bots.update(user.id, bot.id, BotPatch(computer="linux")) or bot
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user.id, bot.id)
    await talk.add_message(user.id, thread.id, "user", message)
    desk = FakeDesk(bot.id, computer="linux")
    await desk.start_browser()
    page = desk.serve_screen(screen or SHOP)
    return CuRig(cfg, user.id, bot, thread.id, desk, page, Gate(cfg), Frames(), ComputerUseLease(), ControlLock(wait_seconds=0.05))
