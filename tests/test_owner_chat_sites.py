"""Owner, 2026-11-03: in your own chat a bot opens any safe site with no Open card, even after the run read pages,
and a link it clicks to another site just goes there; either way the run's fence widens to that site. Unsafe
addresses are never opened, a committing click still asks, and outside your own chat nothing changed."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import judge_act
from roost.computer_use.models import ActResolution, Box
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.page_targets import target_from_ax
from roost.talk.gate import GateContext, judge
from roost.talk.link_scope import LinkScope
from roost.talk.new_site import UNSAFE_ADDRESS_TEXT
from roost.talk.tool_catalog import CATALOG
from cu_run_helpers import make_cu_rig, run_step

CARDS = ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True)
_FENCE = SiteFence(frozenset({"shop.example"}))


def _ctx(**changes) -> GateContext:
    """Your own chat after it read a page: tainted, link-guarded, no longer site-fresh."""
    base = GateContext(allowed=frozenset(CATALOG), tainted=True, link_guard=LinkScope.of(["https://example.com/"]),
                       approval=CARDS, owner_chat=True, site_fresh=False, fence=_FENCE)
    return replace(base, **changes)


def _open(url: str, ctx: GateContext):
    return judge(CATALOG["open_page"], "open_page", {"url": url}, ctx)


@pytest.mark.parametrize("url", ["https://web.whatsapp.com/", "https://www.amazon.es/s?k=boots",
                                 "https://evil.example/?d=notes"])
def test_your_own_chat_opens_any_safe_address_with_no_card(url):
    verdict = _open(url, _ctx())
    assert (verdict.decision, verdict.reason, verdict.url) == ("do", "fresh_open", url)


@pytest.mark.parametrize("url", ["https://user:pw@web.whatsapp.com/", "http://localhost/", "http://10.0.0.1/"])
def test_unsafe_addresses_are_never_opened(url):
    verdict = _open(url, _ctx())
    assert (verdict.decision, verdict.text) == ("never", UNSAFE_ADDRESS_TEXT)


@pytest.mark.parametrize("changes", [{"owner_chat": False}, {"approval": replace(CARDS, cards=False)}])
def test_outside_your_own_chat_a_new_site_is_unchanged(changes):
    assert _open("https://web.whatsapp.com/", _ctx(**changes)).reason in ("new_site", "link_not_trusted")


def _link(text: str, host: str, *, method: str = "") -> ActResolution:
    ax = {"role": {"value": "link" if not method else "button"}, "name": {"value": text}, "backendDOMNodeId": 3}
    target = target_from_ax(ax, Box(10, 10, 100, 20), {"tag": "a" if not method else "button"})
    return ActResolution("click", "https://shop.example/", "shop.example", target, (60, 20), "", host,
                         "browsing" if not method else "submit")


def test_a_link_to_another_site_just_goes_there_in_your_own_chat():
    verdict = judge_act("click", _link("Partner deals", "partner.example"), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("do", "owner_site")


def test_a_committing_click_to_another_site_still_asks():
    verdict = judge_act("click", _link("Pay now", "pay.example", method="post"), _ctx(), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "hard_floor")


def test_outside_your_own_chat_a_link_off_the_fence_is_unchanged():
    verdict = judge_act("click", _link("Partner deals", "partner.example"), _ctx(owner_chat=False), _FENCE)
    assert (verdict.decision, verdict.reason) == ("ask", "new_site")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_after_reading_a_page_a_link_to_another_site_runs_and_widens_the_fence(cfg):
    rig = await make_cu_rig(cfg, "Find me wool socks on https://shop.example/")
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "look")
    await run_step(runner, "click", target={"text": "Partner deals"}, expect="it changes")
    assert runner.parked is None and rig.page.state_name == "partner"
    assert rig.desk.guard_fences[-1].allows("partner.example")


async def test_after_reading_a_page_a_second_site_opens_with_no_card(cfg):
    rig = await make_cu_rig(cfg, "Find me wool socks")
    runner = rig.tool_runner(tainted=False, user_started=True, sees_records=True)
    await run_step(runner, "open_page", url="https://shop.example/")
    await run_step(runner, "open_page", url="https://other.example/page?x=1")
    assert runner.parked is None and rig.desk.open_page_calls[-1] == "https://other.example/page?x=1"
