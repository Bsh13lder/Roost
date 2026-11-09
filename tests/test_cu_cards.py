"""C3 Task 12: committing clicks park on an Ask card with the button's crop and words; Yes resolves the page again
and clicks only the same control; No clicks nothing; a new-site Yes widens this chat's fence; the run's lease and
guards are freed when it ends, also on an error."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

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
from roost.computer_use.runner import CHANGED_TEXT, CHECK_TEXT
from roost.computer_use.session import ComputerUseLease
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.desk.control import ControlLock
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import Gate
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

from cu_run_helpers import AVATAR, SHOP, YOUR_MESSAGE
from team_helpers import RecordingModel, say, wait_idle


@pytest.fixture
async def cfg(monkeypatch):
    monkeypatch.setattr("roost.desk.ready.CU_READY_STABLE_MS", 0)
    config = load_config()
    await init_db(config)
    return config


def _tool(name: str, **arguments: Any):
    return [ToolCallRequested(id=f"c-{name}", name=name, arguments=arguments), TurnDone("tool_use")]


@dataclass
class _Rig:
    runner: TurnRunner
    talk: TalkStore
    store: ApprovalStore
    service: ApprovalService
    leases: ComputerUseLease
    desks: DeskFactory
    user_id: str
    bot_id: str
    thread_id: str

    @property
    def desk(self):
        return self.desks.for_bot(self.bot_id, "linux")

    async def send(self, text: str) -> None:
        message = await self.talk.add_message(self.user_id, self.thread_id, "user", text)
        await self.runner.submit(self.user_id, WorkDraft(
            bot_id=self.bot_id, thread_id=self.thread_id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU, body=text,
            message_id=message.id))
        await wait_idle(self.runner)

    async def card(self):
        cards = await self.store.list_open(self.user_id)
        assert len(cards) == 1
        return cards[0]

    async def kinds(self, kind: str):
        return [m for m in await self.talk.list_messages(self.user_id, self.thread_id) if m.kind == kind]


async def _rig(cfg, steps, model=None) -> _Rig:
    user = await register_user(cfg, "alice", "pw-123456")
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    bot = await bots.create(user.id, BotDraft(name="Shopper", job="shops", instructions="", avatar=AVATAR))
    await bots.update(user.id, bot.id, BotPatch(computer="linux"))
    desk = desks.for_bot(bot.id, "linux")
    await desk.start_browser()
    desk.serve_screen(SHOP)
    store, sessions, leases, control = ApprovalStore(cfg), SessionOks(), ComputerUseLease(), ControlLock()
    the_model = model or RecordingModel(ScriptedTeamModel({"Shopper": steps}))
    runner = TurnRunner(cfg, bots, talk, events, desks, the_model, ActivityBoard(),
                        approvals=ApprovalWiring(store, sessions), domain=build_domain_tools(cfg, events),
                        control=control, cu_leases=leases)
    gate = Gate(cfg)
    executor = ApprovedCalls(runner.domain, gate, talk, events,
                             screen=ScreenReruns(cfg, bots, desks, gate, events, leases, control))
    service = ApprovalService(store, talk, events, runner, executor, sessions)
    thread = await talk.create_thread(user.id, bot.id)
    return _Rig(runner, talk, store, service, leases, desks, user.id, bot.id, thread.id)


_BUY = [_tool("look"), _tool("click", target={"text": "Buy now"}, expect="the order is placed"), say("Asked."),
        say("Bought it.")]


async def test_a_buy_click_parks_a_card_with_crop_and_label(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    card = await rig.card()
    step = card.steps[0]
    assert step.tool == "click" and step.floor == "commit_click" and step.tainted_basis and card.tainted
    assert base64.b64decode(step.crop or "")[:2] == b"\xff\xd8"
    rows = {row.label: row.value for row in step.rows}
    assert rows == {"Site": "shop.example", "Button text": "Buy now", "What it does": "Buys or pays for something",
                    "You expected": "the order is placed"}
    assert step.act is not None and "crop" not in step.act
    assert rig.desk.inputs == () and rig.leases.holder(rig.bot_id) is None and not rig.desk.guards_armed


async def test_yes_runs_the_click_after_a_fresh_resolve(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    await rig.service.answer(rig.user_id, (await rig.card()).id, "yes")
    await wait_idle(rig.runner)
    assert rig.desk._screen_page.state_name == "bought"
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click"]
    results = await rig.kinds("approval_result")
    assert len(results) == 1 and CHECK_TEXT in results[0].body
    assert rig.leases.holder(rig.bot_id) is None and not rig.desk.guards_armed


async def test_yes_on_a_click_aimed_by_number_clicks_that_same_control(cfg):
    """Fast pages: the card's re-run names the stored control (a new run has no look of its own)."""
    steps = [_tool("look"), _tool("click", index=3, expect="the order is placed"), say("Asked."), say("Bought it.")]
    rig = await _rig(cfg, steps)
    await rig.send(YOUR_MESSAGE)
    card = await rig.card()
    assert card.steps[0].title == "Click 'Buy now'"
    await rig.service.answer(rig.user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert rig.desk._screen_page.state_name == "bought"
    body = (await rig.kinds("approval_result"))[0].body
    assert CHECK_TEXT in body and "untrusted_page" not in body


async def test_yes_on_a_changed_page_does_not_click(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    rig.desk._screen_page.state_name = "jobs"          # the page moved on before you said yes
    await rig.service.answer(rig.user_id, (await rig.card()).id, "yes")
    await wait_idle(rig.runner)
    assert rig.desk.inputs == ()
    assert CHANGED_TEXT in (await rig.kinds("approval_result"))[0].body


async def test_no_does_not_click(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    await rig.service.answer(rig.user_id, (await rig.card()).id, "no")
    await wait_idle(rig.runner)
    assert rig.desk.inputs == () and rig.desk._screen_page.state_name == "shop"


async def test_an_off_fence_link_in_your_own_chat_goes_there_and_extends_the_fence(cfg):
    steps = [_tool("look"), _tool("click", target={"text": "Partner deals"}, expect="the deals show"),
             say("There.")]
    rig = await _rig(cfg, steps)
    await rig.send(YOUR_MESSAGE)
    assert tuple(await rig.store.list_open(rig.user_id)) == ()
    assert rig.desk.guard_fences[-1].allows("partner.example") and rig.desk.guard_fences[-1].allows("shop.example")
    assert rig.desk._screen_page.state_name == "partner"


async def test_a_contact_typing_card_yes_types_exactly_that_text(cfg):
    typed = "mail me at ana@example.com"     # an email the user never gave the bot: typing it asks
    steps = [_tool("look"), _tool("click", target={"text": "Note"}, expect="focused"),
             _tool("type", text=typed, source={"from": "message"}, expect="saved"),
             say("Asked."), say("Typed.")]
    rig = await _rig(cfg, steps)
    await rig.send("Please find wool socks and put a note")
    card = await rig.card()
    assert card.steps[0].floor == "contact"
    await rig.service.answer(rig.user_id, card.id, "yes")
    await wait_idle(rig.runner)
    assert rig.desk._screen_page.pasted_lengths == (len(typed),) and rig.desk.typed_lengths == ()


class _Boom:
    """Looks once, then fails: the run ends on an error."""

    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, request):
        self.calls += 1
        if self.calls == 1:
            for event in _tool("look"):
                yield event
            return
        raise RuntimeError("the model went away")


async def test_the_lease_and_guards_are_released_when_the_run_ends(cfg):
    rig = await _rig(cfg, [_tool("look"), say("Looked.")])
    await rig.send(YOUR_MESSAGE)
    assert rig.desk.guard_fences and not rig.desk.guards_armed
    assert rig.leases.holder(rig.bot_id) is None


async def test_the_lease_and_guards_are_released_when_the_run_fails(cfg):
    rig = await _rig(cfg, [], model=_Boom())
    await rig.send(YOUR_MESSAGE)
    assert rig.desk.guard_fences and not rig.desk.guards_armed
    assert rig.leases.holder(rig.bot_id) is None


async def test_an_act_never_runs_as_part_of_a_plan(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    card = await rig.card()
    outcome = await rig.service._executor.run(rig.user_id, card, card.steps[0], reason="plan_accepted")
    assert not outcome.ok and rig.desk.inputs == ()


async def test_yes_while_you_hold_the_computer_does_not_click(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    card = await rig.card()
    rig.runner._control.take(rig.bot_id)
    outcome = await rig.service._executor.run(rig.user_id, card, card.steps[0])
    assert not outcome.ok and "You have my computer" in outcome.text and rig.desk.inputs == ()


async def test_an_executor_without_a_screen_never_clicks(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    card = await rig.card()
    bare = ApprovedCalls(rig.runner.domain, Gate(cfg), rig.talk, EventHub(cfg))
    assert not (await bare.run(rig.user_id, card, card.steps[0])).ok and rig.desk.inputs == ()


# --- B2 (2026-10-23): why an approved click said "It didn't run" -----------------------------------------------

async def test_yes_with_another_tab_in_front_brings_the_bots_tab_up_and_clicks(cfg):
    """Root cause: the re-run waited for the page (a screenshot) before bringing the bot's tab to the front, and
    Chromium never answers a screenshot of a background tab, so the CDP call failed and the Yes "didn't run"."""
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    rig.desk._screen_page.behind = True                  # the owner's other tab is in front
    await rig.service.answer(rig.user_id, (await rig.card()).id, "yes")
    await wait_idle(rig.runner)
    assert rig.desk._screen_page.state_name == "bought"
    assert [verb for verb, _, _ in rig.desk.inputs] == ["move", "click"]


class _DeadPage:
    """Every page call fails as a hung or closed tab does."""

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            from roost.desk.cdp import CdpReplyError
            raise CdpReplyError("No target with given id found")
        return fail


async def test_a_page_error_on_yes_says_why_in_plain_words(cfg, monkeypatch):
    from roost.computer_use.runner import BROWSER_SILENT_TEXT
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    monkeypatch.setattr(rig.desk, "page", lambda: _DeadPage())
    card = await rig.service.answer(rig.user_id, (await rig.card()).id, "yes")
    await wait_idle(rig.runner)
    assert card.state.value == "failed" and rig.desk.inputs == ()
    assert BROWSER_SILENT_TEXT in (await rig.kinds("approval_result"))[0].body


async def test_a_failed_yes_posts_the_reason_under_the_card(cfg):
    rig = await _rig(cfg, _BUY)
    await rig.send(YOUR_MESSAGE)
    rig.desk._screen_page.state_name = "jobs"
    await rig.service.answer(rig.user_id, (await rig.card()).id, "yes")
    await wait_idle(rig.runner)
    notices = [m.body for m in await rig.kinds("notice")]
    assert notices == [f"It didn't run: {CHANGED_TEXT}"]
