"""The Pay card, P5/P8: Roost's own code types each card part into the page's own card box, checks it went in, and
never touches a framed card box or a list it can't type into."""

from __future__ import annotations

import pytest

from roost.desk.fake_cu import FakeComputerPage, FakeScreenState, fake_target
from roost.payments.fill import CardValues, PayRefused, fill_card, needs_card
from roost.payments.texts import FRAMED_TEXT, LIST_BOX_TEXT, NOT_TYPED_TEXT

_VALUES = CardValues(number="4242424242424242", exp="12/28", name="Ana Garcia", cvc="123")


def _box(label: str, part: str, y: int, **over) -> object:
    flags = {"tag": "input", "input_type": "text", "secret_field": True, "card_field": part, **over}
    return fake_target("field", label, 40, y, width=300, **flags)


_PAY = fake_target("button", "Pay 36 EUR", 40, 400, width=160, tag="button")
_CARD = (_box("Card number", "number", 100), _box("MM / YY", "exp", 160), _box("CVC", "cvc", 220),
         _box("Name on card", "name", 280), _PAY)


class _Desk:
    def __init__(self, page: FakeComputerPage) -> None:
        self.page, self.verbs = page, []

    async def send_input(self, action) -> None:
        self.verbs.append(action.verb)
        await self.page.apply(action)


def _page(targets) -> FakeComputerPage:
    return FakeComputerPage({"pay": FakeScreenState(url="https://shop.test/pay", title="Pay", targets=targets)})


async def test_each_card_part_goes_into_its_own_box_once():
    page = _page(_CARD)
    desk = _Desk(page)
    assert await fill_card(page, desk, _VALUES, "shop.test") == ("number", "exp", "cvc", "name")
    assert page.typed_lengths == (16, 5, 3, 10)
    assert desk.verbs == ["move", "click", "type"] * 4
    held = [await page.box_text(t.node_id) for t in _CARD[:4]]
    assert held == ["4242424242424242", "12/28", "123", "Ana Garcia"]


async def test_split_expiry_boxes_take_month_and_a_four_digit_year_when_asked():
    page = _page((_box("Month", "exp_month", 100), _box("Year (YYYY)", "exp_year", 160), _PAY))
    await fill_card(page, _Desk(page), _VALUES, "shop.test")
    assert [await page.box_text(t.node_id) for t in page.state.targets[:2]] == ["12", "2028"]


async def test_a_box_that_loses_a_digit_stops_before_pay():
    page = _page(_CARD)
    page.lossy_typing = 1
    with pytest.raises(PayRefused) as caught:
        await fill_card(page, _Desk(page), _VALUES, "shop.test")
    assert caught.value.detail == NOT_TYPED_TEXT and page.typed_lengths == (16,)


async def test_a_framed_card_box_asks_you_to_take_control():
    frame = fake_target("frame", "Secure payment", 40, 100, width=400, height=200, cross_origin_frame=True)
    page = _page((frame, _PAY))
    with pytest.raises(PayRefused) as caught:
        await fill_card(page, _Desk(page), _VALUES, "shop.test")
    assert caught.value.detail == FRAMED_TEXT and page.typed_lengths == ()


async def test_a_list_for_the_expiry_asks_you_to_pick_it():
    page = _page((_box("Card number", "number", 100), _box("Month", "exp_month", 160, tag="select"), _PAY))
    with pytest.raises(PayRefused) as caught:
        await fill_card(page, _Desk(page), _VALUES, "shop.test")
    assert caught.value.detail == LIST_BOX_TEXT and page.typed_lengths == ()


async def test_no_card_boxes_types_nothing():
    page = _page((_PAY,))
    assert await fill_card(page, _Desk(page), _VALUES, "shop.test") == ()


def test_the_pay_card_shows_fields_only_for_what_the_page_asks():
    assert needs_card(_CARD) == ("number", "exp", "name", "cvc")
    assert needs_card((_box("CVC", "cvc", 100), _PAY)) == ("cvc",)
    assert needs_card((_PAY,)) == ()


def test_card_values_never_show_in_a_repr():
    assert "4242" not in repr(_VALUES) and "123" not in repr(_VALUES)
