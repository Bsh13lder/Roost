"""W6 (owner, 2026-10-24: "Yes do that"): in a fresh run of your own chat, a bot opens any web address and browses
that site with no Open card. A fresh run is one of your own messages (1:1, no room) that has read no outside
content yet. Owner, 2026-11-03: in your own chat that holds after the run read pages too. Everything else stays: a
routine, a handoff or a room; the unsafe addresses; the hard floor."""

from __future__ import annotations

from dataclasses import replace

import pytest

from cu_run_helpers import make_cu_rig, run_step
from roost.approvals.models import ApprovalState
from roost.approvals.texts import PARKED_TEXT
from roost.config import load_config
from roost.constants import FRESH_RUN_OPENS_ANY_SITE
from roost.db.connection import init_db
from roost.talk.gate import GateContext, judge
from roost.talk.link_scope import LinkScope
from roost.talk.new_site import UNSAFE_ADDRESS_TEXT
from roost.talk.tool_catalog import CATALOG

WHATSAPP = "https://web.whatsapp.com/"
CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)
UNSAFE = [
    "https://user:pw@web.whatsapp.com/", "https://web.whatsapp.com:8443/", "ftp://web.whatsapp.com/",
    "file:///etc/passwd", "javascript:alert(1)", "https://web.whatsapp.com\\@evil.io/", "http://localhost/",
    "http://192.168.1.1/", "", "web.whatsapp.com",
]


def _fresh(**changes) -> GateContext:
    base = GateContext(allowed=frozenset({"open_page"}), approval=CARDS, owner_chat=True, site_fresh=True)
    return replace(base, **changes)


def _judge(url: str, ctx: GateContext):
    return judge(CATALOG["open_page"], "open_page", {"url": url}, ctx)


def test_the_rule_has_one_name():
    assert FRESH_RUN_OPENS_ANY_SITE is True


def test_a_fresh_run_of_your_chat_opens_any_address_with_no_card():
    verdict = _judge(WHATSAPP, _fresh())
    assert (verdict.decision, verdict.reason, verdict.url) == ("do", "fresh_open", WHATSAPP)


def test_the_fresh_open_goes_to_the_canonical_address():
    verdict = _judge("https://WEB.WhatsApp.com/", _fresh())
    assert verdict.decision == "do" and verdict.url == askable(WHATSAPP)


def askable(url: str) -> str:
    from roost.talk.new_site import askable_url
    return askable_url(url) or ""


@pytest.mark.parametrize("url", UNSAFE)
def test_an_unsafe_address_is_still_never_opened_in_a_fresh_run(url):
    verdict = _judge(url, _fresh())
    assert (verdict.decision, verdict.text) == ("never", UNSAFE_ADDRESS_TEXT)


def test_a_tainted_run_of_your_chat_opens_with_no_card_too():
    ctx = _fresh(tainted=True, link_guard=LinkScope.of(["https://example.com/"]), site_fresh=False)
    verdict = _judge(WHATSAPP, ctx)
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")


def test_a_run_carrying_outside_content_opens_with_no_card_too():
    verdict = _judge(WHATSAPP, _fresh(link_guard=LinkScope(), site_fresh=False))
    assert (verdict.decision, verdict.reason) == ("do", "fresh_open")


@pytest.mark.parametrize("ctx", [
    _fresh(owner_chat=False),                                    # a routine, a handoff or a room: as before
    _fresh(approval=None),                                       # an old rig with no approval state
    _fresh(approval=replace(CARDS, cards=False)),
])
def test_other_clean_runs_keep_todays_verdict(ctx):
    verdict = _judge(WHATSAPP, ctx)
    assert (verdict.decision, verdict.reason) == ("do", "allowed")


def test_nobody_watching_a_tainted_run_is_still_refused():
    ctx = _fresh(owner_chat=False, tainted=True, link_guard=LinkScope(), approval=replace(CARDS, cards=False),
                 site_fresh=False)
    assert _judge(WHATSAPP, ctx).decision == "never"


# -- the whole path on a Linux computer --------------------------------------------------------------------

@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _rig(cfg):
    rig = await make_cu_rig(cfg, "Find me some wool socks please")   # names no site
    return rig


async def test_a_fresh_run_opens_the_site_and_browses_it_with_no_card(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    assert rig.desk.open_page_calls[-1] == "https://shop.example/" and runner.parked is None
    assert runner.tainted                                           # it read the page
    await run_step(runner, "look")
    assert rig.desk.guard_fences[-1].allows("shop.example")        # the site it opened itself
    assert not rig.desk.guard_fences[-1].allows("partner.example")
    await run_step(runner, "click", target={"text": "Jobs"}, expect="it changes")
    assert runner.parked is None and rig.page.state_name == "jobs"
    assert runner.link_scope.allows("https://shop.example/socks")   # open_page may go back to that site


async def test_after_reading_a_page_a_new_site_opens_too(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    assert await run_step(runner, "open_page", url="https://other.example/") != PARKED_TEXT
    assert runner.parked is None and "https://other.example/" in rig.desk.open_page_calls


async def test_after_reading_a_page_a_link_to_another_site_goes_there(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    await run_step(runner, "click", target={"text": "Partner deals"}, expect="it changes")
    assert runner.parked is None and rig.desk.guard_fences[-1].allows("partner.example")


async def test_the_hard_floor_still_asks_in_a_fresh_run(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    await run_step(runner, "click", target={"text": "Buy now"}, expect="it changes")
    assert runner.parked is not None and runner.parked.floor is not None and rig.page.state_name != "bought"


async def test_a_run_of_your_chat_that_starts_tainted_opens_too(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=True, user_started=True, sees_records=True)
    assert await run_step(runner, "open_page", url="https://shop.example/") != PARKED_TEXT
    assert rig.desk.open_page_calls == ["https://shop.example/"]


async def test_a_clean_routine_run_does_not_widen_the_fence(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=False, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    assert not rig.desk.guard_fences[-1].allows("shop.example")
    assert not runner.link_scope.allows("https://shop.example/socks")


async def test_guards_armed_before_the_open_are_widened_so_the_page_can_load(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "wait_ready")                            # arms the guards on a blank tab, reads nothing
    armed = len(rig.desk.guard_fences)
    assert armed >= 1 and not rig.desk.guard_fences[-1].allows("shop.example")
    await run_step(runner, "open_page", url="https://shop.example/")
    assert len(rig.desk.guard_fences) > armed and rig.desk.guard_fences[-1].allows("shop.example")


@pytest.mark.parametrize(("url", "site"), [
    ("https://www.shop.example/a", "shop.example"), ("https://shop.example/", "shop.example"),
    ("https://www.com/", "www.com"), ("https://user:pw@shop.example/", ""), ("http://localhost/", ""),
])
def test_the_site_a_fresh_open_keeps(url, site):
    from roost.talk.new_site import fresh_site
    assert fresh_site(url) == site


async def test_a_www_address_lets_the_run_come_back_to_the_bare_site(cfg):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://www.shop.example/")
    assert runner.link_scope.allows("https://shop.example/socks")
    assert runner.link_scope.allows("https://www.shop.example/socks")


async def test_guards_that_cannot_widen_leave_the_open_to_the_browser(cfg, monkeypatch, caplog):
    rig = await _rig(cfg)
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "wait_ready")

    async def broken(fence):
        raise RuntimeError("cdp gone")

    monkeypatch.setattr(rig.desk, "arm_guards", broken)
    await run_step(runner, "open_page", url="https://shop.example/")
    assert "Could not widen the browser guards" in caplog.text
