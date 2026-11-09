"""The Pay card, P1: a card box is a secret box the bot never types into or picks in.

``docs/plans/2026-11-05-roost-pay-card.md``. A box's card part comes from its ``autocomplete`` or its id, name,
placeholder and label (EN + ES); a passport's expiry or a passenger's name is not a card box."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.models import ApprovalState
from roost.computer_use.fence import SiteFence
from roost.computer_use.look import CARD_BOX_MARK, _target_line
from roost.computer_use.gate_rules import ACT_TEXTS, judge_act
from roost.computer_use.models import ActResolution, Box
from roost.desk.card_names import card_part
from roost.desk.page_targets import target_from_ax
from roost.talk.gate import GateContext
from roost.talk.tool_catalog import CATALOG

_FENCE = SiteFence(frozenset({"alsa.es"}))


def _box(names: str = "", autocomplete: str = "", tag: str = "input", input_type: str = "text") -> dict:
    return {"tag": tag, "input_type": input_type, "autocomplete": autocomplete, "field_names": names}


@pytest.mark.parametrize(("autocomplete", "part"), [
    ("cc-number", "number"), ("cc-exp", "exp"), ("cc-exp-month", "exp_month"), ("cc-exp-year", "exp_year"),
    ("cc-csc", "cvc"), ("cc-name", "name"), ("section-pay billing cc-number", "number"),
])
def test_autocomplete_names_the_card_part(autocomplete, part):
    assert card_part(_box(autocomplete=autocomplete)) == part


@pytest.mark.parametrize(("names", "part"), [
    ("cardNumber Card number", "number"),
    ("numero Número de tarjeta", "number"),
    ("cvc CVC", "cvc"), ("cvv2 CVV", "cvc"),
    ("Código de seguridad de la tarjeta", "cvc"),
    ("Card security code", "cvc"),
    ("expiry MM / YY", "exp"),
    ("Fecha de caducidad de la tarjeta", "exp"),
    ("Card expiry month", "exp_month"), ("Tarjeta año de caducidad", "exp_year"),
    ("Name on card", "name"), ("Titular de la tarjeta", "name"), ("cardholder", "name"),
])
def test_names_say_the_card_part_in_english_and_spanish(names, part):
    assert card_part(_box(names)) == part


@pytest.mark.parametrize("names", [
    "Fecha de caducidad del documento", "Passport expiry date", "Name", "Nombre", "Phone number",
    "Postal code", "Gift card number", "Loyalty card number", "Security code", "Promo code",
])
def test_other_boxes_are_not_card_boxes(names):
    assert card_part(_box(names)) == ""


def test_a_card_select_counts_and_a_radio_does_not():
    assert card_part(_box("Card expiry month", tag="select", input_type="")) == "exp_month"
    assert card_part(_box("Credit card number", input_type="radio")) == ""
    assert card_part(_box("Card number", tag="button", input_type="")) == ""


def _ax_box(label: str) -> dict:
    return {"role": {"value": "textbox"}, "name": {"value": label}, "backendDOMNodeId": 9, "properties": []}


def test_a_card_box_is_a_secret_box_with_its_part():
    target = target_from_ax(_ax_box("Card number"), Box(0, 0, 200, 30), _box("cardNumber Card number"))
    assert target.card_field == "number" and target.secret_field
    plain = target_from_ax(_ax_box("Email"), Box(0, 0, 200, 30), _box("email Email", input_type="email"))
    assert plain.card_field == "" and not plain.secret_field


def test_the_bot_never_types_into_a_card_box_even_in_your_own_chat():
    target = target_from_ax(_ax_box("CVC"), Box(0, 0, 80, 30), _box("cvc CVC", autocomplete="cc-csc"))
    act = ActResolution(tool="type", url="https://www.alsa.es/pay", host="www.alsa.es", target=target,
                        point=target.box.center(), covered_by="", nav_host="", commit="browsing", text_ok=True)
    ctx = GateContext(allowed=frozenset(CATALOG), tainted=True, owner_chat=True, site_fresh=False, fence=_FENCE,
                      approval=ApprovalState(mode="auto_edit", ask_topics=frozenset(), cards=True))
    verdict = judge_act("type", act, ctx, _FENCE)
    assert (verdict.decision, verdict.text) == ("never", ACT_TEXTS.card)
    assert judge_act("type", act, replace(ctx, owner_chat=False), _FENCE).decision == "never"


def test_a_look_marks_a_card_box():
    target = target_from_ax(_ax_box("Card number"), Box(0, 0, 200, 30), _box("cardNumber Card number"))
    assert _target_line(4, target).endswith(CARD_BOX_MARK)


async def test_the_pay_buttons_picture_greys_a_card_box_beside_it():
    import io

    from PIL import Image

    from roost.computer_use.resolve import _crop
    from roost.constants import CU_MASK_FILL
    from roost.desk.fake_cu import FakeComputerPage, FakeScreenState, fake_target
    card = fake_target("field", "Card number", 40, 100, width=200, tag="input", secret_field=True, card_field="number")
    pay = fake_target("button", "Pay 36 EUR", 40, 140, width=160, tag="button")
    page = FakeComputerPage({"pay": FakeScreenState(url="https://shop.test/pay", title="Pay", targets=(card, pay))})
    with Image.open(io.BytesIO(await _crop(page, pay))) as crop:
        # The crop starts 24 px above and left of Pay, so the card box sits at its top left.
        pixel = crop.convert("RGB").getpixel((40, 4))
    assert all(abs(got - want) < 12 for got, want in zip(pixel, CU_MASK_FILL))


@pytest.mark.parametrize("label", ["Continue", "Confirmar", "Submit"])
def test_a_committing_click_in_a_card_form_pays(label):
    from roost.computer_use.commit_words import commit_class
    from roost.desk.fake_cu import fake_target
    button = fake_target("button", label, 40, 300, tag="button", form_method="post", is_form_submit=True,
                         form_has_card=True)
    assert commit_class(button) == "spend"
    assert commit_class(fake_target("button", label, 40, 300, tag="button", form_method="post",
                                    is_form_submit=True)) != "spend"
    assert commit_class(fake_target("button", "Back", 40, 300, tag="button", form_has_card=True)) != "spend"
