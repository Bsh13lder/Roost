"""Vault: passwords, the fill (docs/plans/2026-11-08-roost-vault-passwords.md V6): Roost's own code types the user
name and the password into the page's own boxes, only on the login's own site, never into a box inside another
site's frame, and presses nothing."""

from __future__ import annotations

import pytest

from roost.desk.fake_cu import FakeComputerPage, FakeScreenState, fake_target
from roost.vault.password_fill import (
    MANY_BOXES_TEXT, NO_BOX_TEXT, NOT_TYPED_TEXT, WRONG_SITE_TEXT, FillRefused, fill_login,
)
from roost.vault.passwords import LoginSecret

_LOGIN = LoginSecret(id="L1", host="upwork.com", username="ana@example.com", password="s3cret-Pass!")
_EMAIL = fake_target("field", "Email", 40, 100, width=300, tag="input", input_type="email", sign_in_box=True)
_PASSWORD = fake_target("field", "Password", 40, 160, width=300, tag="input", input_type="password",
                        secret_field=True)
_SIGN_IN = fake_target("button", "Log in", 40, 220, width=120, tag="button")


class _Desk:
    def __init__(self, page: FakeComputerPage) -> None:
        self.page, self.verbs = page, []

    async def send_input(self, action) -> None:
        self.verbs.append(action.verb)
        await self.page.apply(action)


def _page(targets, url="https://www.upwork.com/ab/account-security/login") -> FakeComputerPage:
    return FakeComputerPage({"login": FakeScreenState(url=url, title="Log in", targets=targets)})


async def test_the_user_name_and_password_go_into_their_own_boxes_and_nothing_is_pressed():
    page = _page((_EMAIL, _PASSWORD, _SIGN_IN))
    desk = _Desk(page)
    await fill_login(page, desk, _EMAIL, _LOGIN)
    assert await page.box_text(_EMAIL.node_id) == "ana@example.com"
    assert page.typed_lengths == (len("ana@example.com"), len("s3cret-Pass!"))
    assert desk.verbs == ["move", "click", "type", "move", "click", "type"]


async def test_a_page_that_asks_for_the_password_alone_types_only_the_password():
    page = _page((_PASSWORD, _SIGN_IN))
    desk = _Desk(page)
    await fill_login(page, desk, None, _LOGIN)
    assert page.typed_lengths == (len("s3cret-Pass!"),)


async def test_a_user_name_already_in_its_box_is_not_typed_again():
    page = _page((_EMAIL, _PASSWORD, _SIGN_IN))
    page.fill_box("ana@example.com", _EMAIL.node_id)
    await fill_login(page, _Desk(page), _EMAIL, _LOGIN)
    assert page.typed_lengths == (len("s3cret-Pass!"),)


@pytest.mark.parametrize("url", ["https://notupwork.com/login", "https://upwork.com.evil.io/login",
                                 "https://evil.io/?next=upwork.com"])
async def test_another_site_gets_nothing(url):
    page = _page((_EMAIL, _PASSWORD), url=url)
    with pytest.raises(FillRefused) as caught:
        await fill_login(page, _Desk(page), _EMAIL, _LOGIN)
    assert caught.value.detail == WRONG_SITE_TEXT and page.typed_lengths == ()


async def test_a_password_box_inside_another_sites_frame_is_never_used():
    framed = fake_target("field", "Password", 40, 160, width=300, tag="input", input_type="password",
                         secret_field=True, cross_origin_frame=True)
    page = _page((_EMAIL, framed))
    with pytest.raises(FillRefused) as caught:
        await fill_login(page, _Desk(page), _EMAIL, _LOGIN)
    assert caught.value.detail == NO_BOX_TEXT and page.typed_lengths == ()


async def test_two_password_boxes_type_nothing():
    second = fake_target("field", "Repeat password", 40, 200, width=300, tag="input", input_type="password",
                         secret_field=True)
    page = _page((_EMAIL, _PASSWORD, second))
    with pytest.raises(FillRefused) as caught:
        await fill_login(page, _Desk(page), _EMAIL, _LOGIN)
    assert caught.value.detail == MANY_BOXES_TEXT and page.typed_lengths == ()


async def test_a_user_name_that_does_not_go_in_stops_before_the_password():
    page = _page((_EMAIL, _PASSWORD))
    page.lossy_typing = 1
    with pytest.raises(FillRefused) as caught:
        await fill_login(page, _Desk(page), _EMAIL, _LOGIN)
    assert caught.value.detail == NOT_TYPED_TEXT and page.typed_lengths == (len("ana@example.com"),)


def test_refusal_texts_never_hold_a_value():
    for text in (WRONG_SITE_TEXT, NO_BOX_TEXT, MANY_BOXES_TEXT, NOT_TYPED_TEXT):
        assert "s3cret" not in text and "ana@" not in text
