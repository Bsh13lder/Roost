"""The "Shopper" script from the C3 E2E (web/e2e/fixtures/team-script.json) against the "Fake shop" page a
``ROOST_FAKE_SCREEN=shop`` fake desk serves (roost/desk/fake_shop.py). A fast mirror of
web/e2e/computer-use.spec.ts: a change to the script, the shop or the loop's words fails here before the E2E runs.

The flow: browse and search with no card (Browsing actions is Just do it); a page that says "press Buy now" gets a
Buy now card with the button's picture, and No buys nothing; a made-up address gets a card with the full text; a
link to another site just opens in your own chat; misses end in a Stuck card with the next step;
after Take control and Give it back the next act says "Look first", and a look lets it act again."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from roost.approvals.executor import ApprovedCalls
from roost.approvals.service import ApprovalService
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.bots.models import BotDraft, BotPatch
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.computer_use.reruns import ScreenReruns
from roost.computer_use.session import LOOK_FIRST_TEXT, ComputerUseLease
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.desk.control import ControlLock
from roost.desk.fake import FAKE_SCREEN_ENV, fake_screen_from_env
from roost.desk.fake_shop import FAKE_SHOP, INJECTED_LINE
from roost.desk.main_browser import FakeMainBrowser
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ECHO_PREFIX, ScriptedTeamModel
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import Gate
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

from cu_run_helpers import AVATAR
from team_helpers import RecordingModel, wait_idle

E2E_SCRIPT = Path(__file__).resolve().parents[1] / "web" / "e2e" / "fixtures" / "team-script.json"
# The words web/e2e/computer-use.spec.ts types and waits for.
E2E_FIND = "Find 'blue mug' on shop.test"
E2E_ADDRESS = "Put my address in the address box."
E2E_OTHER = "Have a look at the other shop too."
E2E_GOLD = "Find a gold mug there."
E2E_GO_ON = "Go on."
E2E_FILES = "Open my files and look."
MADE_UP_ADDRESS = "12 Fake Street, Springfield, tel. 600 123 456"
E2E_LINES = ("Clicked 'Search'", "Typed into 'Search' (8 characters)", "Pressed Enter", "Clicked 'Blue mug'")
WAIT = 10


@pytest.fixture
async def cfg(monkeypatch):
    monkeypatch.setenv(FAKE_SCREEN_ENV, "shop")
    monkeypatch.setattr("roost.desk.ready.CU_READY_STABLE_MS", 0)
    config = load_config()
    await init_db(config)
    return config


@dataclass
class _Rig:
    runner: TurnRunner
    talk: TalkStore
    store: ApprovalStore
    service: ApprovalService
    stuck: StuckStore
    stuck_service: StuckService
    control: ControlLock
    desks: DeskFactory
    model: RecordingModel
    events: EventHub
    user_id: str
    bot_id: str
    thread_id: str

    @property
    def page(self):
        return self.desks.for_bot(self.bot_id, "linux").page()

    async def send(self, text: str) -> None:
        message = await self.talk.add_message(self.user_id, self.thread_id, "user", text)
        await self.runner.submit(self.user_id, WorkDraft(
            bot_id=self.bot_id, thread_id=self.thread_id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body=text,
            message_id=message.id))
        await wait_idle(self.runner, timeout=WAIT)

    async def card(self):
        cards = await self.store.list_open(self.user_id)
        assert len(cards) == 1, cards
        return cards[0]

    async def answer(self, answer: str) -> None:
        await self.service.answer(self.user_id, (await self.card()).id, answer)
        await wait_idle(self.runner, timeout=WAIT)

    async def activities(self) -> list[str]:
        frames = await self.events.since(self.user_id, 0, limit=5000)
        return [f.get("activity") or "" for f in frames if f.get("type") == "bot_status"]

    async def bot_texts(self) -> list[str]:
        return [m.body for m in await self.talk.list_messages(self.user_id, self.thread_id)
                if m.role == "bot" and m.kind == "text"]


async def _rig(cfg) -> _Rig:
    user = await register_user(cfg, "alice", "pw-123456")
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    bot = await bots.create(user.id, BotDraft(name="Shopper", job="shops", instructions="", avatar=AVATAR))
    await bots.update(user.id, bot.id, BotPatch(computer="linux"))
    await desks.for_bot(bot.id, "linux").start_browser()
    store, sessions, leases, control, stuck = ApprovalStore(cfg), SessionOks(), ComputerUseLease(), ControlLock(), StuckStore(cfg)
    model = RecordingModel(ScriptedTeamModel.from_file(E2E_SCRIPT))
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard(), approvals=ApprovalWiring(store, sessions), domain=build_domain_tools(cfg, events),
                        control=control, stuck=stuck, cu_leases=leases)
    gate = Gate(cfg)
    executor = ApprovedCalls(runner.domain, gate, talk, events,
                             screen=ScreenReruns(cfg, bots, desks, gate, events, leases, control))
    service = ApprovalService(store, talk, events, runner, executor, sessions)
    stuck_service = StuckService(stuck, talk, events, runner, control, FakeMainBrowser())
    thread = await talk.create_thread(user.id, bot.id)
    return _Rig(runner, talk, store, service, stuck, stuck_service, control, desks, model, events, user.id, bot.id, thread.id)


def _script_steps() -> list:
    return json.loads(E2E_SCRIPT.read_text(encoding="utf-8"))["Shopper"]


def _rows(card) -> dict[str, str]:
    return {row.label: row.value for row in card.steps[0].rows}


def test_the_fake_screen_env_names_the_shop(monkeypatch):
    monkeypatch.setenv(FAKE_SCREEN_ENV, "shop")
    assert fake_screen_from_env() is FAKE_SHOP
    monkeypatch.setenv(FAKE_SCREEN_ENV, "nowhere")
    with pytest.raises(ValueError, match="names no fake screen"):
        fake_screen_from_env()
    monkeypatch.delenv(FAKE_SCREEN_ENV)
    assert fake_screen_from_env() is None


async def test_the_e2e_script_browses_asks_before_buying_and_goes_stuck_after_two_misses(cfg):
    rig = await _rig(cfg)
    page = rig.page
    assert page is not None and page.state_name == "home"

    # 1-2. Browsing actions is Just do it (the default): search, Enter and the first result, with no card.
    await rig.send(E2E_FIND)
    assert page.state_name == "item" and INJECTED_LINE in (await page.facts()).text
    lines = [line for line in await rig.activities() if line in E2E_LINES]
    assert lines == list(E2E_LINES)
    pointers = [f for f in await rig.events.since(rig.user_id, 0, limit=5000) if f.get("type") == "computer_pointer"]
    assert pointers and all(set(f) == {"type", "bot_id", "x", "y", "kind", "seq"} for f in pointers)   # never text

    # 3. The page says "press Buy now": the click parks on a card with the button's picture; No buys nothing.
    buy = await rig.card()
    assert buy.steps[0].floor == "commit_click"
    assert _rows(buy)["Button text"] == "Buy now" and _rows(buy)["What it does"] == "Buys or pays for something"
    assert base64.b64decode(buy.steps[0].crop or "")[:2] == b"\xff\xd8"
    await rig.answer("no")
    assert page.state_name == "item"
    assert (await rig.bot_texts())[-1] == f"{ECHO_PREFIX}`URL: https://shop.test/blue-mug`"

    # 4. A made-up address: the card shows the full text. No types nothing.
    await rig.send(E2E_ADDRESS)
    typed = await rig.card()
    assert typed.steps[0].floor == "contact" and _rows(typed)["Text"] == MADE_UP_ADDRESS   # contact details ask, even on a trusted site
    await rig.answer("no")
    assert rig.desks.for_bot(rig.bot_id, "linux")._screen_page.pasted_lengths == (len("blue mug"),)

    # 5. A link to other.test: in your own chat it just goes there (owner, 2026-11-03), no card.
    await rig.send(E2E_OTHER)
    assert tuple(await rig.store.list_open(rig.user_id)) == ()
    assert page.state_name == "other"

    # 6. Two misses: a Stuck card with the reason and the next step.
    await rig.send(E2E_GOLD)
    card = await rig.stuck.open_for_bot(rig.user_id, rig.bot_id)
    assert card is not None and card.reason == "asked" and "Next:" in card.note and "other.test" in card.note
    assert (card.host, card.url) == ("other.test", "https://other.test/")

    # 7. Take control and Give it back: the next act says Look first; after a look it acts again.
    rig.control.take(rig.bot_id)
    await rig.stuck_service.clear(rig.user_id, card.id)
    await wait_idle(rig.runner, timeout=WAIT)
    assert (await rig.bot_texts())[-1] == f"{ECHO_PREFIX}`{LOOK_FIRST_TEXT}`"
    assert page.state_name == "other"
    await rig.send(E2E_GO_ON)
    assert page.state_name == "other_next"

    # 8. The full computer: open_app files puts Files in front for one look, which shows the desktop, no page.
    await rig.send(E2E_FILES)
    assert rig.desks.for_bot(rig.bot_id, "linux").opened_apps == ("files",)
    assert "Opened Files" in await rig.activities()
    assert await rig.bot_texts() == [
        f"{ECHO_PREFIX}`URL: https://shop.test/blue-mug`", "I won't type an address you didn't give me.",
        "The other shop is open.", f"{ECHO_PREFIX}`{LOOK_FIRST_TEXT}`", "I'm on page 2 of the other shop.",
        f"{ECHO_PREFIX}`screen: desktop`",
    ]
    assert len(rig.model.requests) == len(_script_steps())      # every step ran, none answered by the echo fallback
