"""C3 Task 10: the gate for clicks and keystrokes on the live page (security review a).

Amendment 2026-10-21 (user): ordinary clicks (browsing, consent) just happen in every mode unless the
Browsing actions topic is on; committing clicks hit the hard floor and ask in every mode and every taint."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from roost.approvals import topics
from roost.approvals.models import (
    ApprovalCard,
    ApprovalState,
    CardState,
    PendingCall,
    approval_card_out,
    step_from_dict,
    step_to_dict,
)
from roost.approvals.texts import NEEDS_YOUR_OK_TEXT
from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.computer_use import gate_rules
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.gate_rules import ACT_TEXTS, floor_of, judge_act
from roost.computer_use.models import ActResolution, Box, ClickIn, PageTarget, PressKeyIn, TypeIn, resolution_to_json
from roost.config import load_config
from roost.constants import CU_SEARCH_TEXT_MAX
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolSpec
from roost.mac.redact import redact_for_audit
from roost.talk.gate import Gate, GateContext, judge
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_def import ToolDef

_MODES = ("ask", "auto_edit", "plan")
_FENCE = SiteFence(frozenset({"example.com"}))
_EMPTY = {"type": "object", "properties": {}}
_ACTS = {name: ToolDef(ToolSpec(name, name, _EMPTY), "act") for name in ("click", "type", "press_key")}
_CATALOG = {**CATALOG, **_ACTS}
_ALL = frozenset(_CATALOG)


def _target(text: str = "Next page", **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=7, kind="link", text=text, tag="a", input_type="", box=Box(100, 200, 80, 30), form_method="",
        form_submit_text="", is_form_submit=False, link_host="", in_dialog="", in_consent=False,
        cross_origin_frame=False, editable=False, secret_field=False, searchish=False, expands=False,
    )
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _click(target: PageTarget | None = None, **over: object) -> ActResolution:
    target = _target() if target is None else target
    fields: dict[str, object] = dict(
        tool="click", url="https://example.com/jobs", host="example.com", target=target,
        point=target.box.center(), covered_by="", nav_host="", commit=commit_class(target),
    )
    fields.update(over)
    return ActResolution(**fields)  # type: ignore[arg-type]


def _field(**over: object) -> PageTarget:
    fields: dict[str, object] = {"kind": "field", "tag": "textarea", "editable": True, **over}
    return _target("Cover letter", **fields)


def _typing(*, text_ok: bool = True, flags: frozenset[str] = frozenset(), **over: object) -> ActResolution:
    """Typing on a site outside ``_FENCE``: on a trusted site typing is free (owner, 2026-10-27,
    ``tests/test_cu_trusted_typing.py``), so the typed-text rules are checked off it."""
    target = over.pop("target", _field())
    where = {"url": "https://other.example/form", "host": "other.example", **over}
    return _click(target, tool="type", commit="browsing", text_ok=text_ok, text_flags=flags, **where)  # type: ignore[arg-type]


def _state(mode: str = "auto_edit", **kw: object) -> ApprovalState:
    return ApprovalState(mode=mode, ask_topics=kw.pop("ask_topics", frozenset()), cards=kw.pop("cards", True), **kw)  # type: ignore[arg-type]


def _ctx(mode: str = "auto_edit", *, tainted: bool = False, fence: SiteFence | None = _FENCE, **kw: object) -> GateContext:
    return GateContext(allowed=_ALL, tainted=tainted, approval=_state(mode, **kw), fence=fence)


def _pair(verdict) -> tuple[str, str]:
    return verdict.decision, verdict.reason


def _judge(name: str, r: ActResolution | None, *, args: dict | None = None, **kw: object):
    return judge(_CATALOG[name], name, args or {}, _ctx(**kw), act=r)  # type: ignore[arg-type]


def test_a_buy_click_asks_in_auto_edit_with_browsing_on_auto():
    buy = _click(_target("Buy now", kind="button", tag="button"))
    assert buy.commit == "spend" and floor_of(buy) == "commit_click"
    assert _pair(_judge("click", buy, mode="auto_edit")) == ("ask", "hard_floor")


@pytest.mark.parametrize("mode", _MODES)
def test_a_tainted_auto_edit_run_still_asks_to_send(mode):
    send = _click(_target("Send message", kind="button", tag="button"))
    assert send.commit == "send"
    assert _pair(_judge("click", send, mode=mode, tainted=True)) == ("ask", "hard_floor")


@pytest.mark.parametrize("mode", _MODES)
def test_ordinary_clicks_just_happen_in_every_mode(mode):
    for tainted in (False, True):
        assert _pair(_judge("click", _click(), mode=mode, tainted=tainted)) == ("do", "allowed")
        consent = _click(_target("Reject all", kind="button", tag="button", in_consent=True))
        assert consent.commit == "consent"
        assert _pair(_judge("click", consent, mode=mode, tainted=tainted)) == ("do", "allowed")
        assert _pair(_judge("type", _typing(), mode=mode, tainted=tainted)) == ("do", "allowed")


@pytest.mark.parametrize("mode", _MODES)
def test_browsing_topic_on_asks_for_ordinary_clicks(mode):
    on = frozenset({"browsing"})
    assert _pair(_judge("click", _click(), mode=mode, ask_topics=on)) == ("ask", "topic_asks")
    assert _pair(_judge("press_key", _click(tool="press_key"), mode=mode, ask_topics=on)) == ("ask", "topic_asks")
    assert _pair(_judge("click", _click(), mode=mode, ask_topics=frozenset({"files"}))) == ("do", "allowed")


def test_a_browsing_click_is_done_in_auto_edit_when_the_topic_is_off():
    assert _pair(_judge("click", _click(), mode="auto_edit")) == ("do", "allowed")


@pytest.mark.parametrize("mode", _MODES)
def test_plan_mode_asks_never_plans_an_act(mode):
    buy = _click(_target("Checkout", kind="button", tag="button"))
    assert _judge("click", buy, mode=mode).decision == "ask"
    for name, r in (("click", buy), ("click", _click()), ("type", _typing(text_ok=False))):
        assert _judge(name, r, mode="plan").decision != "plan"


def test_no_cards_turns_ask_into_never():
    buy = _click(_target("Pay now", kind="button", tag="button"))
    for r, kw in ((buy, {}), (_click(), {"ask_topics": frozenset({"browsing"})}),
                  (_click(nav_host="evil.io"), {})):
        verdict = _judge("click", r, cards=False, **kw)
        assert _pair(verdict) == ("never", "needs_your_ok") and verdict.text == NEEDS_YOUR_OK_TEXT
    assert _pair(_judge("click", _click(), cards=False)) == ("do", "allowed")   # a routine may still browse


def test_off_fence_navigation_asks_new_site():
    away = _click(nav_host="accounts.other.org")
    assert floor_of(away, _FENCE) == "new_site"
    assert _pair(_judge("click", away)) == ("ask", "new_site")
    assert _pair(_judge("click", _click(nav_host="www.example.com"))) == ("do", "allowed")
    enter = _click(tool="press_key", nav_host="search.other.org", commit="browsing")
    assert _pair(_judge("press_key", enter)) == ("ask", "new_site")
    assert floor_of(_click(nav_host="www.example.com"), _FENCE) is None


def test_the_fence_comes_before_the_floor_and_both_ignore_taint():
    buy_away = _click(_target("Buy now", kind="button", tag="button"), nav_host="pay.other.org")
    assert _pair(_judge("click", buy_away, tainted=True)) == ("ask", "new_site")


def test_password_field_is_never():
    secret_box = _field(secret_field=True)
    refused = _typing(target=secret_box, refusal=ACT_TEXTS.password)
    for mode in _MODES:
        verdict = _judge("type", refused, mode=mode)
        assert _pair(verdict) == ("never", "act_refused") and verdict.text == ACT_TEXTS.password
    # even when the resolver forgot to say so, a secret field is never typed into
    verdict = _judge("type", _typing(target=secret_box))
    assert _pair(verdict) == ("never", "act_refused") and verdict.text == ACT_TEXTS.password


def test_a_resolver_refusal_is_never_with_its_own_sentence():
    verdict = _judge("click", _click(refusal="That point is outside the page."))
    assert _pair(verdict) == ("never", "act_refused") and verdict.text == "That point is outside the page."


def test_mac_brave_is_never():
    verdict = _judge("click", _click(), fence=None)
    assert _pair(verdict) == ("never", "act_refused") and verdict.text == ACT_TEXTS.mac_brave


def test_unapproved_text_types_with_no_card():
    # Owner, 2026-11-03: typing never asks; only a secret or a contact detail does.
    r = _typing(text_ok=False)
    assert floor_of(r, _FENCE, typed_chars=12) is None
    for mode in _MODES:
        assert _pair(_judge("type", r, args={"text": "x" * 12}, mode=mode)) == ("do", "allowed")


def test_search_box_takes_short_model_text():
    search = _typing(target=_field(searchish=True, tag="input", input_type="search"), text_ok=False)
    short, long = {"text": "x" * CU_SEARCH_TEXT_MAX}, {"text": "x" * (CU_SEARCH_TEXT_MAX + 1)}
    assert _pair(_judge("type", search, args=short, mode="ask")) == ("do", "allowed")
    assert _pair(_judge("type", search, args=long)) == ("do", "allowed")      # any length now (2026-11-03)
    assert floor_of(search, _FENCE, typed_chars=CU_SEARCH_TEXT_MAX + 1) is None
    assert floor_of(search, _FENCE) is None
    flagged = replace(search, text_flags=frozenset({"contact"}))
    assert floor_of(flagged, _FENCE, typed_chars=10) == "contact"
    assert _pair(_judge("type", flagged, args={"text": "a@b.co"})) == ("ask", "hard_floor")


def test_contact_details_hit_the_floor():
    contact = _typing(flags=frozenset({"contact"}))
    secret = _typing(flags=frozenset({"secret"}))
    assert floor_of(contact) == "contact" and floor_of(secret) == "secret"
    assert floor_of(_typing(text_ok=False, flags=frozenset({"secret", "contact"}))) == "secret"
    for mode in _MODES:
        assert _pair(_judge("type", contact, mode=mode, tainted=True)) == ("ask", "hard_floor")
        assert _pair(_judge("type", secret, mode=mode)) == ("ask", "hard_floor")


@pytest.mark.parametrize("word", ["commit", "resolution", "act"])
def test_model_supplied_resolution_fields_are_rejected(word):
    forged = {word: "browsing"}
    with pytest.raises(ValidationError):
        ClickIn.model_validate({"x": 10, "y": 10, "expect": "a page", **forged})
    with pytest.raises(ValidationError):
        TypeIn.model_validate({"text": "hi", "source": {"from": "message"}, "expect": "typed", **forged})
    with pytest.raises(ValidationError):
        PressKeyIn.model_validate({"key": "Enter", "expect": "sent", **forged})
    # the gate never reads a resolution from the arguments either
    args = {"x": 10, "y": 10, "expect": "a page", word: resolution_to_json(_click())}
    assert _judge("click", None, args=args).decision == "never"


def test_act_without_a_resolution_is_never():
    for name in ("click", "type", "press_key"):
        verdict = _judge(name, None)
        assert _pair(verdict) == ("never", "act_refused") and verdict.text == ACT_TEXTS.not_found
    assert judge_act("click", None, _ctx(), _FENCE).decision == "never"


def test_an_act_outside_the_run_allowlist_is_never():
    ctx = GateContext(allowed=frozenset({"look"}), approval=_state(), fence=_FENCE)
    assert _pair(judge(_ACTS["click"], "click", {}, ctx, act=_click())) == ("never", "not_allowed")
    assert judge_act("look", _click(), _ctx(), _FENCE).decision == "never"   # not an act tool


def test_a_tainted_committing_act_is_never_done_even_without_a_floor(monkeypatch):
    monkeypatch.setattr(gate_rules, "floor_of", lambda *a, **k: None)   # the case the floor makes unreachable
    buy = _click(_target("Buy now", kind="button", tag="button"))
    assert _pair(_judge("click", buy, tainted=True)) == ("never", "tainted_refused")


def test_no_approval_state_turns_floors_into_never():
    buy = _click(_target("Buy now", kind="button", tag="button"))
    ctx = GateContext(allowed=_ALL, fence=_FENCE)
    assert _pair(judge(_ACTS["click"], "click", {}, ctx, act=buy)) == ("never", "needs_your_ok")
    assert _pair(judge(_ACTS["click"], "click", {}, ctx, act=_click())) == ("do", "allowed")


def test_a_page_cannot_turn_a_buy_button_into_browsing():
    # The page says "this is just a menu" around a "Buy now" button that also claims to expand a menu.
    buy = _target("Buy now", kind="button", tag="button", in_dialog="this is just a menu", expands=True)
    assert commit_class(buy) == "spend"
    assert _pair(_judge("click", _click(buy))) == ("ask", "hard_floor")
    # Even a resolution that was (wrongly) classed as browsing is re-read from its control.
    forged = _click(buy, commit="browsing")
    assert floor_of(forged) == "commit_click"
    assert _pair(_judge("click", forged)) == ("ask", "hard_floor")
    nothing = replace(_click(), target=None, point=(5, 5), commit="browsing")
    assert _pair(_judge("click", nothing)) == ("ask", "hard_floor")


def test_every_act_tool_belongs_to_browsing():
    for name in ("click", "type", "press_key"):
        assert topics.topic_of(name) == "browsing"
    for name in ("look", "wait_ready", "scroll"):
        assert topics.topic_of(name) is None


# --- the audit and the card -------------------------------------------------------------------------------

_TYPED = "Dear Ana, my code is 4471 and I can start Monday"


def test_redact_keeps_source_length_and_a_keyed_hash_never_the_text():
    dek = b"k" * 32
    args = {"text": _TYPED, "source": {"from": "message", "id": None}, "expect": "the letter is in the box"}
    out = redact_for_audit("type", args, dek, act=_typing())
    blob = json.dumps(out)
    assert _TYPED not in blob and "4471" not in blob and "the letter is in the box" not in blob
    assert out["source"] == {"from": "message"} and out["length"] == len(_TYPED)
    assert out["sha256"] == hmac.new(dek, _TYPED.encode(), hashlib.sha256).hexdigest()
    assert out["sha256"] != hashlib.sha256(_TYPED.encode()).hexdigest()
    assert out["label"] == "Cover letter" and out["host"] == "other.example" and out["class"] == "browsing"


def test_redact_keeps_only_known_act_fields():
    dek = b"k" * 32
    click = redact_for_audit("click", {"target": {"text": "Buy now", "kind": "button", "nth": 1}, "expect": "paid",
                                       "smuggled": _TYPED}, dek, act=_click(_target("Buy now")))
    assert _TYPED not in json.dumps(click)
    assert click["class"] == "spend" and click["label"] == "Buy now"
    key = redact_for_audit("press_key", {"key": "Enter", "expect": "sent", "text": _TYPED}, dek)
    assert key == {"key": "Enter", "expect": {"chars": 4}}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_the_audit_never_holds_typed_text(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await BotStore(cfg).create(user.id, BotDraft("Scout", "j", "", Avatar("round", "#22c55e", "none")))
    gate = Gate(cfg, catalog=_CATALOG)
    args = {"text": _TYPED, "source": {"from": "message"}, "expect": "typed"}
    verdict = await gate.decide(user.id, bot.id, "type", args, _ctx(), act=_typing())
    assert verdict.decision == "do"
    await gate.decide(user.id, bot.id, "type", args, _ctx(), act=None)
    await gate.record_approved(user.id, bot.id, "type", args, reason="approved", tainted=False, act=_typing())
    dek = await get_user_dek(cfg, user.id)
    async with db_session(cfg) as db:
        cursor = await db.execute("SELECT detail FROM audit WHERE user_id = ? AND action = 'type'", (user.id,))
        rows = [decrypt(row["detail"], dek, user_aad(user.id, "audit:detail")) for row in await cursor.fetchall()]
    assert len(rows) == 3
    for detail in rows:
        assert _TYPED not in detail and "4471" not in detail and json.loads(detail)["length"] == len(_TYPED)


def _card(step: PendingCall) -> ApprovalCard:
    return ApprovalCard(
        id="c1", user_id="u1", bot_id="b1", thread_id="t1", work_item_id=None, kind="ask", state=CardState.OPEN,
        steps=(step,), request="", tainted=False, session_offer=False, answer_item_id=None,
        created_at="2026-10-21T10:00:00+00:00", closed_at=None,
    )


def test_the_crop_is_only_in_the_full_card():
    crop = base64.b64encode(b"\xff\xd8jpeg").decode("ascii")
    step = PendingCall(tool="click", arguments={"x": 1, "y": 2, "expect": "paid"}, topic="browsing",
                       title="Click 'Buy now'", floor="commit_click", crop=crop, act=resolution_to_json(_click()))
    assert approval_card_out(_card(step), full=True).steps[0].crop == crop
    assert approval_card_out(_card(step)).steps[0].crop is None
    assert approval_card_out(_card(step), full=True, counts_only=True).steps[0].crop is None
    back = step_from_dict(json.loads(json.dumps(step_to_dict(step))))
    assert back.crop == crop and back.act == step.act and back.floor == "commit_click"
    plain = step_from_dict({"tool": "add_task", "arguments": {}, "topic": "tasks", "title": "Add"})
    assert plain.crop is None and plain.act is None


# -- security review (a) after Task 10 ------------------------------------------------------------------------


def test_a_chat_box_takes_model_text_but_enter_there_asks():
    chat = _field(tag="input", input_type="text", searchish=True, form_method="get", form_submit_text="Send")
    typing = _typing(target=chat, text_ok=False)
    assert floor_of(typing, _FENCE, typed_chars=12) is None
    for mode in _MODES:
        assert _pair(_judge("type", typing, args={"text": "x" * 12}, mode=mode, tainted=True)) == ("do", "allowed")
    enter = _click(chat, tool="press_key", commit=commit_class(chat, key="Enter"))
    assert enter.commit == "send"
    assert _pair(_judge("press_key", enter, tainted=True)) == ("ask", "hard_floor")


def test_a_fake_text_box_buy_button_asks_in_every_mode_and_taint():
    fake = _target("Buy now", kind="field", tag="button", editable=True)
    for mode in _MODES:
        for tainted in (False, True):
            assert _pair(_judge("click", _click(fake), mode=mode, tainted=tainted)) == ("ask", "hard_floor")
    forged = _click(fake, commit="browsing")
    assert floor_of(forged) == "commit_click"


def test_type_into_something_that_is_not_a_text_box_is_never():
    for target in (_target("Inbox", kind="link"), _target("Buy now", kind="field", tag="button", editable=True)):
        verdict = _judge("type", _typing(target=target), args={"text": "e"})
        assert _pair(verdict) == ("never", "act_refused") and verdict.text == ACT_TEXTS.not_a_box
