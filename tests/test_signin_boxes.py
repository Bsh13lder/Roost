"""B3 (owner decision 2026-10-23): which boxes are secret (password, one-time and verification codes), which are a
sign-in page's email or user-name box, and that an email you typed in your own message goes into the latter
without a card."""

from __future__ import annotations

from dataclasses import replace

from roost.approvals.floor import floor_of
from roost.computer_use.models import ActResolution, Box, PageTarget
from roost.desk.page_targets import target_from_ax

_BOX = {"role": {"value": "textbox"}, "name": {"value": "Code"}, "backendDOMNodeId": 3}


def _box(**extra: object) -> PageTarget:
    return target_from_ax(_BOX, Box(0, 0, 200, 30), {"tag": "input", "input_type": "text", **extra})


def test_boxes_named_for_a_code_are_secret():
    for names in ("otp", "verification code", "one time code", "2fa", "passcode", "pin", "codigo"):
        assert _box(field_names=names).secret_field, names


def test_a_promo_zip_or_gift_code_box_is_not_secret():
    for names in ("promo code", "zip code", "postal code", "discount code", "gift card code", "coupon code",
                  "referral code", "codigo postal", "search"):
        assert not _box(field_names=names).secret_field, names


def test_a_named_code_box_must_take_typing():
    assert not target_from_ax({"role": {"value": "button"}, "name": {"value": "Send code"}, "backendDOMNodeId": 4},
                              Box(0, 0, 9, 9), {"tag": "button", "field_names": "send code"}).secret_field


def test_sign_in_boxes_by_autocomplete_by_a_password_in_the_form_or_by_their_name():
    assert _box(autocomplete="username webauthn").sign_in_box
    assert _box(input_type="email", form_has_password=True).sign_in_box
    assert _box(field_names="login_username").sign_in_box
    assert not _box(input_type="email", field_names="newsletter email").sign_in_box
    assert not _box(field_names="otp").sign_in_box


def _typed(target: PageTarget, flags=frozenset({"contact"}), text_ok=True) -> ActResolution:
    return ActResolution(tool="type", url="https://www.upwork.com/login", host="www.upwork.com", target=target,
                         point=(10, 10), covered_by="", nav_host="", commit="browsing", text_ok=text_ok,
                         text_flags=frozenset(flags))


def test_your_own_email_goes_into_a_sign_in_box_without_a_card():
    box = _box(autocomplete="username", field_names="email")
    assert floor_of(_typed(box), typed_chars=15) is None


def test_anywhere_else_contact_details_and_secrets_still_ask():
    newsletter = _box(input_type="email", field_names="newsletter")
    sign_in = _box(autocomplete="username")
    assert floor_of(_typed(newsletter)) == "contact"
    assert floor_of(_typed(sign_in, text_ok=False)) == "contact"                    # not your own words
    assert floor_of(_typed(sign_in, flags={"contact", "secret"})) == "secret"
    assert floor_of(_typed(replace(sign_in, sign_in_box=False))) == "contact"
