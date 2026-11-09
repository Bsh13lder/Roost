"""Owner, 2026-11-03: in your own chat a bot opens any safe site and changes what you ask for even after reading
pages (roost/talk/owner_chat.py); what follows is the older W7 file, its asserts updated to that rule.

W7 (owner, 2026-10-24: "Lets go for 2"): your new message counts as a fresh start, for opening sites only. A
run made of your own new chat messages (1:1, it may show cards) opens any safe address with no Open card even when
the chat's older history is tainted, until the run itself reads new outside content. Its ordinary taint is
unchanged for everything else: the tainted-write rule, create_routine, the hard floor, unsafe addresses. Since
2026-10-25 (owner) such a run may also `remember`, shown with Undo, until it reads outside content."""

from __future__ import annotations

from dataclasses import replace

import pytest

from approval_helpers import make_card_rig
from cu_run_helpers import make_cu_rig, run_step
from roost.approvals.models import ApprovalState, BotApproval
from roost.bots.store import BotStore
from roost.approvals.texts import PARKED_TEXT
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ToolCallRequested, TurnDone
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore
from roost.memory.tool_specs import TAINTED_REMEMBER_TEXT
from roost.talk.gate import GateContext, judge
from roost.talk.link_scope import LinkScope
from roost.talk.new_site import UNSAFE_ADDRESS_TEXT
from roost.talk.tool_catalog import CATALOG
from roost.talk.turn import RunInputs, _site_fresh
from roost.work.models import WorkItem, WorkKind, WorkState
from team_helpers import RecordingModel, make_bot, say, send, wait_idle

WHATSAPP = "https://web.whatsapp.com/"
CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)


def _inherited(**changes) -> GateContext:
    """A run of your new message in a chat whose last replies read a page: tainted and link-guarded, yet site-fresh."""
    base = GateContext(allowed=frozenset({"open_page", "remember", "create_routine", "update_task"}), tainted=True,
                       link_guard=LinkScope.of(["https://example.com/"]), approval=CARDS, owner_chat=True,
                       site_fresh=True)
    return replace(base, **changes)


def _open(url: str, ctx: GateContext):
    return judge(CATALOG["open_page"], "open_page", {"url": url}, ctx)


# -- the gate ------------------------------------------------------------------------------------------------

def test_a_site_fresh_run_opens_a_new_site_despite_the_chats_old_taint():
    verdict = _open(WHATSAPP, _inherited())
    assert (verdict.decision, verdict.reason, verdict.url) == ("do", "fresh_open", WHATSAPP)


def test_once_freshness_is_gone_your_own_chat_still_opens_a_new_site():
    # Owner, 2026-11-03: in your own chat freshness no longer decides opening a site.
    verdict = _open(WHATSAPP, _inherited(site_fresh=False))
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")


@pytest.mark.parametrize("url", ["https://user:pw@web.whatsapp.com/", "http://localhost/", "file:///etc/passwd",
                                 "https://web.whatsapp.com:8443/", "http://10.0.0.1/"])
def test_unsafe_addresses_are_still_never_opened(url):
    assert (_open(url, _inherited()).decision, _open(url, _inherited()).text) == ("never", UNSAFE_ADDRESS_TEXT)


@pytest.mark.parametrize("ctx", [
    _inherited(owner_chat=False),                                  # a routine, handoff or room run
    _inherited(approval=replace(CARDS, cards=False)),              # nobody watching
    _inherited(approval=None),
])
def test_site_freshness_needs_your_own_chat_that_can_show_cards(ctx):
    assert _open(WHATSAPP, ctx).reason != "fresh_open"


@pytest.mark.parametrize("changes", [{}, {"site_fresh": False}])
def test_remember_runs_in_your_own_chat_fresh_or_not(changes):
    """Owner, 2026-11-03: in your own chat a memory just saves (with Undo), even after the run read a page."""
    verdict = judge(CATALOG["remember"], "remember", {"text": "likes wool"}, _inherited(**changes))
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_change")


@pytest.mark.parametrize("changes", [{"owner_chat": False}, {"approval": None},
                                     {"approval": replace(CARDS, cards=False)}])
def test_remember_is_still_refused_outside_your_own_chat(changes):
    verdict = judge(CATALOG["remember"], "remember", {"text": "likes wool"}, _inherited(**changes))
    assert verdict.decision == "never" and verdict.reason == "tainted_refused"


def test_create_routine_runs_in_your_own_chat_with_a_tainted_history():
    verdict = judge(CATALOG["create_routine"], "create_routine", {"name": "x"}, _inherited())
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_change")
    assert judge(CATALOG["create_routine"], "create_routine", {"name": "x"}, _inherited(owner_chat=False)).decision == "never"


def test_a_change_in_the_tainted_history_run_just_runs_in_your_own_chat():
    # Owner, 2026-11-03: "the bot just does what you ask" -- no model check; outside your chat D3 still refuses.
    verdict = judge(CATALOG["update_task"], "update_task", {"task_id": "t"}, _inherited())
    assert (verdict.decision, verdict.reason) == ("do", "owner_chat_change")
    elsewhere = judge(CATALOG["update_task"], "update_task", {"task_id": "t"}, _inherited(owner_chat=False))
    assert (elsewhere.decision, elsewhere.reason) == ("never", "tainted_change")


# -- which runs start site-fresh (turn.py) -------------------------------------------------------------------

def _item(kind: WorkKind, *, tainted: bool = False, inflight: str | None = None) -> WorkItem:
    return WorkItem(id="i", user_id="u", bot_id="b", thread_id="t", kind=kind, origin="o", body="", tainted=tainted,
                    depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r",
                    inflight=inflight, result=None, result_tainted=False, created_at="", updated_at="")


def test_a_run_of_your_own_new_messages_starts_site_fresh():
    assert _site_fresh(RunInputs(items=(_item(WorkKind.MESSAGE), _item(WorkKind.MESSAGE)))) is True


@pytest.mark.parametrize("kind", [WorkKind.CARD_ANSWER, WorkKind.ROUTINE, WorkKind.HANDOFF])
def test_card_answers_routines_and_handoffs_get_no_freshness(kind):
    assert _site_fresh(RunInputs(items=(_item(kind),))) is False
    assert _site_fresh(RunInputs(items=(_item(WorkKind.MESSAGE), _item(kind)))) is False


def test_a_room_run_or_a_run_outside_the_queue_gets_no_freshness():
    assert _site_fresh(RunInputs(items=(_item(WorkKind.MESSAGE),), room=object())) is False   # type: ignore[arg-type]
    assert _site_fresh(RunInputs()) is False


def test_a_claimed_message_that_is_itself_tainted_or_survived_a_crash_is_not_fresh():
    assert _site_fresh(RunInputs(items=(_item(WorkKind.MESSAGE, tainted=True),))) is False
    assert _site_fresh(RunInputs(items=(_item(WorkKind.MESSAGE, inflight="open_page(...)"),))) is False


# -- the tool runner: freshness ends at the first outside content the run reads ---------------------------

@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_a_tainted_start_opens_and_keeps_opening_after_reading(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True, site_fresh=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    assert rig.desk.open_page_calls[-1] == "https://shop.example/" and runner.parked is None
    assert runner.link_scope.allows("https://shop.example/socks")      # it may come back to the site it opened
    assert await run_step(runner, "open_page", url="https://other.example/") != PARKED_TEXT
    assert runner.parked is None and rig.desk.open_page_calls[-1] == "https://other.example/"


async def test_the_computer_fence_takes_the_site_and_a_link_off_it_goes_there_after_a_look(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True, site_fresh=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    assert rig.desk.guard_fences[-1].allows("shop.example")
    await run_step(runner, "click", target={"text": "Partner deals"}, expect="it changes")
    assert runner.parked is None and rig.desk.guard_fences[-1].allows("partner.example")


async def test_the_hard_floor_still_asks_in_a_site_fresh_run(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True, site_fresh=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    await run_step(runner, "click", target={"text": "Buy now"}, expect="it changes")
    assert runner.parked is not None and runner.parked.floor is not None and rig.page.state_name != "bought"


async def test_a_tainted_steered_message_ends_freshness_but_your_chat_still_opens(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True, site_fresh=True)
    runner.tainted = True                       # what steps._join does for a tainted steered item
    assert not runner.site_fresh
    assert await run_step(runner, "open_page", url="https://shop.example/") != PARKED_TEXT


async def test_a_clean_record_read_keeps_freshness_but_a_tainted_one_ends_it(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True, site_fresh=True)
    runner.saw_content(tainted=False)
    assert runner.site_fresh
    runner.saw_content(tainted=True)
    assert not runner.site_fresh


async def test_a_run_of_another_kind_that_starts_tainted_still_asks(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")
    runner = rig.tool_runner(tainted=True, user_started=False, sees_records=True)
    assert await run_step(runner, "open_page", url="https://shop.example/") == PARKED_TEXT
    assert "https://shop.example/" not in rig.desk.open_page_calls


# -- the whole path: your new message in a chat whose last reply read a page ------------------------------

@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _call(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _second_message(cfg, user_id: str, second: list, *, mode: str = "ask"):
    """Gela read a page for your first message (a tainted reply in the last 12); then your new message runs."""
    bot = await make_bot(cfg, user_id, "Gela")
    if mode != "ask":
        await BotStore(cfg).set_approval(user_id, bot.id, BotApproval(mode, frozenset()))
    script = [_call("c1", "open_page", url="https://example.com/"), say("It says hi."), *second]
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Gela": script})))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Read https://example.com/")
    await wait_idle(rig.runner)
    replies = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.role == "bot" and m.kind == "text"]
    assert replies and replies[-1].tainted
    await send(rig, user_id, bot.id, thread.id, "Now open the messenger")
    await wait_idle(rig.runner)
    return rig, bot, thread


async def test_your_new_message_opens_a_new_site_with_no_card_despite_a_tainted_reply(cfg, user_id):
    rig, bot, _ = await _second_message(cfg, user_id, [_call("c2", "open_page", url=WHATSAPP), say("Opened.")])
    assert WHATSAPP in rig.desks.for_bot(bot.id).open_page_calls
    assert tuple(await rig.store.list_open(user_id)) == ()


async def test_after_the_run_reads_a_page_more_new_sites_open_with_no_card(cfg, user_id):
    rig, bot, _ = await _second_message(cfg, user_id, [
        _call("c2", "open_page", url=WHATSAPP), _call("c3", "open_page", url="https://other.example/"),
        _call("c4", "open_page", url="https://third.example/x?y=1"),
    ])
    assert tuple(await rig.store.list_open(user_id)) == ()
    opened = rig.desks.for_bot(bot.id).open_page_calls
    assert "https://other.example/" in opened and "https://third.example/x?y=1" in opened


async def test_remember_saves_with_undo_before_the_run_reads_anything(cfg, user_id):
    rig, bot, thread = await _second_message(cfg, user_id, [
        _call("c2", "remember", text="Remind me two hours before every appointment", kind="preference"),
        say("Saved."),
    ], mode="auto_edit")
    results = [t.text for request in rig.model.requests for t in request.turns if t.tool_call_id == "c2"]
    assert results and results[0].startswith("Saved to memory")
    memories = await MemoryService(MemoryStore(cfg), rig.events).list_for_bot(user_id, bot.id)
    assert [(m.text, m.tainted) for m in memories] == [("Remind me two hours before every appointment", False)]
    kinds = [m.kind for m in await rig.talk.list_messages(user_id, thread.id)]
    assert "memory_note" in kinds and "memory_offer" not in kinds


async def test_remember_still_saves_after_the_run_read_a_page(cfg, user_id):
    rig, _, _ = await _second_message(cfg, user_id, [
        _call("c2", "open_page", url=WHATSAPP), _call("c3", "remember", text="likes wool socks", kind="preference"),
        say("Noted."),
    ], mode="auto_edit")
    results = {t.text for request in rig.model.requests for t in request.turns if t.tool_call_id == "c3"}
    assert len(results) == 1 and next(iter(results)).startswith("Saved to memory")
    assert TAINTED_REMEMBER_TEXT not in results


# -- owner, 2026-11-03: in your own chat any safe address opens, a path or a query included

@pytest.mark.parametrize("url", ["https://evil.example/?d=my-notes", "https://evil.example/my-notes",
                                 "https://evil.example/#my-notes", "https://www.amazon.es/s?k=boots"])
def test_with_a_tainted_history_a_full_address_opens_too(url):
    verdict = _open(url, _inherited())
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")


@pytest.mark.parametrize("url", ["https://web.whatsapp.com", "https://web.whatsapp.com/", "https://www.upwork.com/"])
def test_with_a_tainted_history_a_sites_main_address_opens_at_once(url):
    verdict = _open(url, _inherited())
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")


def test_a_clean_run_still_opens_a_full_address_at_once():
    clean = _inherited(tainted=False, link_guard=None)
    verdict = _open("https://www.amazon.es/s?k=boots", clean)
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")
