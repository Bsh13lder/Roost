"""The Pay card end to end (owner, 2026-11-05): your own chat books up to Pay, the card asks for the card parts the
page has, your card goes into the page's boxes, and only then the same Pay button is clicked. The security code is
never stored; a saved card is sealed in Vault: cards; a bad number types nothing."""

from __future__ import annotations

import json
import logging
import sqlite3

import pytest

from roost.approvals.models import approval_card_out
from roost.crypto.encryption import decrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import get_db_path
from roost.desk.fake_shop import FAKE_SHOP
from roost.payments.cards import CardStore, NewCard
from roost.payments.checks import CardCheckError
from roost.payments.entry import PAY_AUDIT_ACTION, NotPayCard, PayEntry, PayRequest
from roost.payments.fill import PayRefused
from roost.payments.texts import HELD_TEXT
from roost.talk.gate import Gate

from team_helpers import send, wait_idle
from test_owner_chat_booking import WAIT, YOUR_MESSAGE, _booking_steps, _rig
from test_owner_chat_booking import cfg as _booking_cfg

cfg = _booking_cfg      # the same fixture: the Fake shop on a fake Linux computer

NUMBER, CVC = "4242424242424242", "737"


def _new(**over) -> PayRequest:
    fields = dict(card_id=None, number=NUMBER, exp="12/28", name="Ana Garcia", cvc=CVC, save=False)
    fields.update(over)
    return PayRequest(**fields)  # type: ignore[arg-type]


async def _parked(cfg):
    rig = await _rig(cfg, _booking_steps())
    thread = await rig.talk.create_thread(rig.user_id, rig.bot_id)
    await send(rig, rig.user_id, rig.bot_id, thread.id, YOUR_MESSAGE)
    await wait_idle(rig.runner, timeout=WAIT)
    [card] = await rig.open_cards()
    store = CardStore(cfg)
    entry = PayEntry(rig.service, rig.talk, rig.bots, rig.desks, rig.control, rig.leases, Gate(cfg), store)
    return rig, thread, card, entry, store


def _box(rig, label: str) -> str:
    return next(rig.page._boxes.get(t.node_id, "") for t in FAKE_SHOP["pay"].targets if t.text == label)


def _every_row(cfg) -> str:
    con = sqlite3.connect(get_db_path(cfg))
    try:
        tables = [n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return " ".join(" ".join(str(v) for v in row) for t in tables for row in con.execute(f"SELECT * FROM {t}"))
    finally:
        con.close()


async def test_the_pay_card_fills_your_card_then_clicks_pay(cfg, caplog):
    caplog.set_level(logging.DEBUG)
    rig, thread, card, entry, store = await _parked(cfg)
    assert approval_card_out(card).pay
    fields = await entry.fields(rig.user_id, card.id)
    assert (fields.parts, fields.refusal, fields.cards) == (("number", "exp", "name", "cvc"), "", ())

    await entry.pay(rig.user_id, card.id, _new(save=True))
    assert (_box(rig, "Card number"), _box(rig, "MM / YY"), _box(rig, "CVC")) == (NUMBER, "12/28", CVC)
    await wait_idle(rig.runner, timeout=WAIT)
    assert rig.page.state_name == "paid" and await rig.open_cards() == ()

    [saved] = await store.list(rig.user_id)
    assert (saved.brand, saved.last4) == ("visa", "4242")
    everything = _every_row(cfg)
    assert NUMBER not in everything and f" {CVC} " not in f" {everything} " and NUMBER not in caplog.text
    messages = await rig.talk.list_messages(rig.user_id, thread.id)
    assert all(NUMBER not in m.body and CVC not in m.body.split() for m in messages)
    dek = await get_user_dek(cfg, rig.user_id)
    con = sqlite3.connect(get_db_path(cfg))
    [(detail,)] = con.execute("SELECT detail FROM audit WHERE action = ?", (PAY_AUDIT_ACTION,)).fetchall()
    con.close()
    assert json.loads(decrypt(detail, dek, user_aad(rig.user_id, "audit:detail"))) == {
        "parts": ["number", "exp", "cvc", "name"], "last4": "4242"}


async def test_a_saved_card_needs_only_the_security_code(cfg):
    rig, _, card, entry, store = await _parked(cfg)
    saved = await store.save(rig.user_id, NewCard(number=NUMBER, exp="01/30", name="Ana Garcia"))
    await entry.pay(rig.user_id, card.id, PayRequest(card_id=saved.id, number="", exp="", name="", cvc=CVC,
                                                     save=False))
    assert (_box(rig, "Card number"), _box(rig, "MM / YY"), _box(rig, "CVC")) == (NUMBER, "01/30", CVC)
    await wait_idle(rig.runner, timeout=WAIT)
    assert rig.page.state_name == "paid"
    assert (await store.list(rig.user_id))[0].last_used_at


@pytest.mark.parametrize("request_", [_new(number="4242424242424241"), _new(cvc="12"), _new(exp="01/20"),
                                      _new(name="")])
async def test_a_bad_value_types_nothing_and_the_card_stays_open(cfg, request_):
    rig, _, card, entry, _ = await _parked(cfg)
    typed_before = rig.page.typed_lengths
    with pytest.raises(CardCheckError):
        await entry.pay(rig.user_id, card.id, request_)
    assert rig.page.typed_lengths == typed_before and rig.page.state_name == "pay"
    assert [c.id for c in await rig.open_cards()] == [card.id]


async def test_while_you_hold_the_computer_nothing_is_typed(cfg):
    rig, _, card, entry, _ = await _parked(cfg)
    rig.control.take(rig.bot_id)
    with pytest.raises(PayRefused) as caught:
        await entry.pay(rig.user_id, card.id, _new())
    assert caught.value.detail == HELD_TEXT and rig.page.state_name == "pay"


async def test_another_users_card_is_not_found_and_other_cards_are_not_pay_cards(cfg):
    rig, _, card, entry, _ = await _parked(cfg)
    assert await entry.pay("someone-else", card.id, _new()) is None
    await rig.service.answer(rig.user_id, card.id, "no")
    await wait_idle(rig.runner, timeout=WAIT)
    from roost.approvals.models import CardClosed
    with pytest.raises(CardClosed):
        await entry.pay(rig.user_id, card.id, _new())
    assert NotPayCard  # the routine flow keeps its hard floor: tests/test_owner_chat_booking.py


async def test_card_values_with_no_box_to_fill_are_refused_not_dropped(cfg):
    from dataclasses import replace

    from roost.desk.fake_cu import fake_target
    from roost.payments.texts import FRAMED_TEXT
    rig, _, card, entry, _ = await _parked(cfg)
    frame = fake_target("frame", "Secure payment", 40, 100, width=400, height=200, cross_origin_frame=True)
    framed = replace(FAKE_SHOP["pay"], targets=(frame, FAKE_SHOP["pay"].targets[-1]))
    rig.page._states = type(rig.page._states)({**rig.page._states, "pay": framed})
    with pytest.raises(PayRefused) as caught:
        await entry.pay(rig.user_id, card.id, _new())
    assert caught.value.detail == FRAMED_TEXT and rig.page.state_name == "pay"
    # You typed the card yourself under Take control: Pay with no values just clicks.
    await entry.pay(rig.user_id, card.id, PayRequest(card_id=None, number="", exp="", name="", cvc="", save=False))
    await wait_idle(rig.runner, timeout=WAIT)
    assert rig.page.state_name == "paid"


async def test_a_pay_click_that_does_not_happen_empties_the_card_boxes(cfg, monkeypatch):
    from dataclasses import replace

    from roost.desk.fake_cu import fake_target
    rig, _, card, entry, _ = await _parked(cfg)
    *boxes, _pay = FAKE_SHOP["pay"].targets
    dearer = replace(FAKE_SHOP["pay"], targets=(*boxes, fake_target("button", "Pay 90 EUR", 40, 320, width=160,
                                                                    tag="button")), on_click={})
    rig.page._states = type(rig.page._states)({**rig.page._states, "pay_dearer": dearer})
    original = entry._after_fill

    async def price_changes(*args):
        await original(*args)
        rig.page.state_name = "pay_dearer"          # the site changed the total while you typed

    monkeypatch.setattr(entry, "_after_fill", price_changes)
    await entry.pay(rig.user_id, card.id, _new())
    assert rig.page.state_name == "pay_dearer"
    assert (_box(rig, "Card number"), _box(rig, "MM / YY"), _box(rig, "CVC"), _box(rig, "Name on card")) == (
        "", "", "", "")


async def test_a_fill_that_stops_halfway_empties_what_it_typed(cfg):
    rig, _, card, entry, _ = await _parked(cfg)
    rig.page.lossy_typing = 0
    original = rig.page.box_text

    async def short_cvc(node_id):
        held = await original(node_id)
        return held[:-1] if held == CVC else held     # the CVC box drops a digit

    rig.page.box_text = short_cvc
    with pytest.raises(PayRefused):
        await entry.pay(rig.user_id, card.id, _new())
    rig.page.box_text = original
    assert _box(rig, "Card number") == "" and _box(rig, "MM / YY") == "" and rig.page.state_name == "pay"
