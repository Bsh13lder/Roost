"""The stuck detector (stuck flow Piece A, design R2/R3): which pages are a wall and which are content.

Every fixture page in ``tests/fixtures/pages/`` holds exactly ``PageText``'s fields. A page whose text is
at most ``STUCK_THIN_PAGE_CHARS`` long is thin (a wall); words and boxes that block a thin page are only
an article or a site header on a long one."""

from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from roost.constants import (
    MAIN_BROWSER_OPEN_ARGV,
    STUCK_CHALLENGE_TEXT_MARKERS,
    STUCK_CHALLENGE_TITLE_MARKERS,
    STUCK_CHALLENGE_URL_MARKERS,
    STUCK_CODE_MARKERS,
    STUCK_LOGIN_MARKERS,
    STUCK_THIN_PAGE_CHARS,
)
from roost.desk import PageText
from roost.desk.stuck import Block, detect_block, host_of_url, is_thin

PAGES = Path(__file__).parent / "fixtures" / "pages"

THIN_PAGES = ("normal", "challenge_title", "challenge_thin_text", "challenge_cf_url", "captcha_thin",
              "login_wall", "code_2fa", "refused_403", "refused_429")
LONG_PAGES = ("login_by_title", "article_mentions_verify", "shop_with_header_login")
EXPECTED_REASONS = {
    "challenge_title": "challenge",
    "challenge_thin_text": "challenge",
    "challenge_cf_url": "challenge",
    "captcha_thin": "challenge",
    "login_wall": "login",
    "login_by_title": "login",
    "code_2fa": "code",
    "refused_403": "refused",
    "refused_429": "refused",
    "article_mentions_verify": None,
    "shop_with_header_login": None,
    "normal": None,
}
# Plain content, well past the thin limit, with no marker of any kind in it.
_LONG_TEXT = "Plain news of the day. " * 100


def load_page(name: str) -> PageText:
    """``tests/fixtures/pages/<name>.json`` as a ``PageText``."""
    return PageText(**json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8")))


def _reason_of(page: PageText) -> str | None:
    block = detect_block(page)
    return None if block is None else block.reason


def test_a_page_text_built_the_old_way_has_no_signals():
    page = PageText(url="https://example.com/", title="Example Domain", text="Hello", truncated=False)
    assert (page.status, page.password_field, page.captcha_frame) == (None, False, False)
    assert PageText("https://example.com/", "Example Domain", "Hello", False) == page


def test_every_fixture_page_has_exactly_the_page_text_fields():
    names = sorted(path.stem for path in PAGES.glob("*.json"))
    assert names == sorted((*THIN_PAGES, *LONG_PAGES)) == sorted(EXPECTED_REASONS)
    field_names = {field.name for field in fields(PageText)}
    for name in names:
        assert set(json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8"))) == field_names, name


@pytest.mark.parametrize("name", THIN_PAGES)
def test_the_thin_fixture_pages_are_thin(name):
    assert is_thin(load_page(name))


@pytest.mark.parametrize("name", LONG_PAGES)
def test_the_long_fixture_pages_are_long(name):
    assert not is_thin(load_page(name))


@pytest.mark.parametrize(("name", "reason"), EXPECTED_REASONS.items())
def test_each_fixture_page_gets_its_reason(name, reason):
    assert _reason_of(load_page(name)) == reason


def test_a_block_carries_the_page_address_and_its_host():
    block = detect_block(load_page("login_wall"))
    assert block == Block(reason="login", url="https://accounts.example/v3/password", host="accounts.example")
    assert (block.note, block.suggest_main_browser) == ("", False)


def test_a_long_page_with_a_password_box_is_not_a_login_wall():
    shop = load_page("shop_with_header_login")
    assert shop.password_field and not is_thin(shop) and "sign in" in shop.text.casefold()
    assert detect_block(shop) is None


def test_a_long_article_that_mentions_verify_you_are_human_is_not_a_challenge():
    article = load_page("article_mentions_verify")
    assert "verify you are human" in article.text.casefold() and not is_thin(article)
    assert detect_block(article) is None


def test_a_challenge_title_or_address_counts_on_a_page_of_any_length():
    titled = replace(load_page("challenge_title"), text=_LONG_TEXT)
    addressed = replace(load_page("challenge_cf_url"), text=_LONG_TEXT)
    assert not is_thin(titled) and not is_thin(addressed)
    assert _reason_of(titled) == _reason_of(addressed) == "challenge"


@pytest.mark.parametrize("title", [
    "Just a moment...", "  just a MOMENT...  ", "Attention Required! | Cloudflare", "Verify you are human",
    "Checking your browser - example.com",
])
def test_a_challenge_title_marker_at_the_start_of_the_title_counts_on_a_page_of_any_length(title):
    long_page = replace(load_page("normal"), title=title, text=_LONG_TEXT)
    assert not is_thin(long_page)
    assert _reason_of(long_page) == "challenge"


@pytest.mark.parametrize("title", [
    "Just a moment of calm | Garden Journal", "Checking your browser before accessing example.com",
    "A page where attention required is in the middle", "Why we ask you to verify you are human",
    "Notes on checking your browser history", "Just a momentary pause",
])
def test_a_challenge_title_marker_that_is_not_the_start_of_the_title_is_not_a_challenge_on_a_long_page(title):
    long_page = replace(load_page("normal"), title=title, text=_LONG_TEXT)
    assert not is_thin(long_page)
    assert detect_block(long_page) is None


@pytest.mark.parametrize("title", ["Just a moment of calm | Garden Journal", "Checking your browser before accessing x"])
def test_a_title_that_starts_with_a_marker_and_runs_on_in_words_still_counts_on_a_thin_page(title):
    thin_page = replace(load_page("normal"), title=title)
    assert is_thin(thin_page)
    assert _reason_of(thin_page) == "challenge"


def test_a_challenge_marker_in_the_middle_of_a_title_never_counts_even_on_a_thin_page():
    assert detect_block(replace(load_page("normal"), title="Notes on checking your browser history")) is None


def test_challenge_words_or_a_captcha_frame_count_only_on_a_thin_page():
    words = load_page("challenge_thin_text")
    frame = load_page("captcha_thin")
    assert detect_block(replace(words, text=f"{words.text}\n{_LONG_TEXT}")) is None
    assert detect_block(replace(frame, text=f"{frame.text}\n{_LONG_TEXT}")) is None


def test_markers_match_in_any_letter_case():
    normal = load_page("normal")
    assert _reason_of(replace(normal, title="JUST A MOMENT...")) == "challenge"
    assert _reason_of(replace(normal, url="https://example.com/?__CF_CHL_TK=abc")) == "challenge"
    assert _reason_of(replace(normal, text="Please VERIFY YOU ARE HUMAN")) == "challenge"
    assert _reason_of(replace(normal, text="ENTER THE CODE we sent you")) == "code"
    assert _reason_of(replace(load_page("shop_with_header_login"), title="LOG IN | Shop Example")) == "login"


def test_a_login_marker_in_the_title_or_the_address_path_makes_a_password_page_a_login_wall():
    shop = load_page("shop_with_header_login")
    assert _reason_of(replace(shop, url="https://shop.example/account/sign-in?next=/cart")) == "login"
    assert _reason_of(replace(shop, url="https://shop.example/Account/Login")) == "login"
    assert _reason_of(replace(shop, title="Sign in | Shop Example")) == "login"


def test_a_login_marker_only_in_the_host_or_the_query_does_not_count():
    shop = load_page("shop_with_header_login")
    assert detect_block(replace(shop, url="https://login.example/garden/tools")) is None
    assert detect_block(replace(shop, url="https://shop.example/garden/tools?came_from=login")) is None


@pytest.mark.parametrize(("title", "path"), [
    ("Blog index | Shop Example", "/garden/tools"),                    # b-"log in"-dex
    ("Our catalog in pictures | Shop Example", "/garden/tools"),       # cata-"log in"
    ("Garden tools | Shop Example", "/blog/designing-a-rain-garden"),  # de-"signin"-g
    ("Garden tools | Shop Example", "/catalog-index"),                 # cata-"log-in"-dex
])
def test_a_login_marker_inside_a_longer_word_does_not_count(title, path):
    """Markers match whole words: a long page with only a header sign-in box stays content."""
    shop = load_page("shop_with_header_login")
    assert detect_block(replace(shop, title=title, url=f"https://shop.example{path}")) is None


@pytest.mark.parametrize("path", [
    "/users/sign_in",        # Devise
    "/users/log_in",         # Phoenix
    "/users/signin",
    "/user-login/",
    "/login.php",
    "/Account/Log.In",
])
def test_a_login_marker_between_separators_in_the_address_path_counts(path):
    shop = load_page("shop_with_header_login")
    assert _reason_of(replace(shop, url=f"https://shop.example{path}")) == "login"


@pytest.mark.parametrize("title", ["Log in", "Sign_in | Shop Example", "Shop Example - Sign-In", "LOGIN"])
def test_a_login_marker_between_separators_in_the_title_counts(title):
    assert _reason_of(replace(load_page("shop_with_header_login"), title=title)) == "login"


def test_a_login_page_without_a_password_box_is_not_a_login_wall():
    assert detect_block(replace(load_page("login_by_title"), password_field=False)) is None
    assert detect_block(replace(load_page("login_wall"), password_field=False)) is None


def test_code_words_count_only_on_a_thin_page():
    code = load_page("code_2fa")
    assert detect_block(replace(code, text=f"{code.text}\n{_LONG_TEXT}")) is None


def test_a_challenge_outranks_a_login_a_login_outranks_a_code_and_any_block_outranks_a_refusal():
    login = load_page("login_wall")
    code = load_page("code_2fa")
    assert _reason_of(replace(login, title="Just a moment...")) == "challenge"
    assert _reason_of(replace(code, password_field=True)) == "login"
    assert _reason_of(replace(code, status=429)) == "code"
    assert _reason_of(replace(login, status=403)) == "login"
    assert load_page("challenge_title").status == 403
    assert _reason_of(load_page("challenge_title")) == "challenge"


@pytest.mark.parametrize(("status", "reason"), [
    (403, "refused"), (429, "refused"), (200, None), (404, None), (500, None), (None, None),
])
def test_only_403_and_429_are_a_refusal(status, reason):
    assert _reason_of(replace(load_page("normal"), status=status)) == reason


def test_the_detector_never_says_asked():
    reasons = {_reason_of(load_page(name)) for name in EXPECTED_REASONS}
    assert "asked" not in reasons and reasons == {"challenge", "login", "code", "refused", None}


def test_a_page_is_thin_up_to_the_limit_and_long_past_it():
    normal = load_page("normal")
    assert is_thin(replace(normal, text="x" * STUCK_THIN_PAGE_CHARS))
    assert not is_thin(replace(normal, text="x" * (STUCK_THIN_PAGE_CHARS + 1)))


@pytest.mark.parametrize(("url", "host"), [
    ("https://Shop.Example:8443/cart?x=1", "shop.example"),
    ("about:blank", "about:blank"),
    ("", ""),
    ("http://[::1", "http://[::1"),
])
def test_host_of_url_is_the_lowercased_host_or_the_address_itself(url, host):
    assert host_of_url(url) == host


def test_an_address_that_cannot_be_parsed_does_not_crash_the_detector():
    broken = "http://[::1/login"
    assert detect_block(replace(load_page("shop_with_header_login"), url=broken)) is None
    assert detect_block(replace(load_page("refused_403"), url=broken)) == Block(
        reason="refused", url=broken, host=broken)


def test_every_marker_is_already_casefolded():
    markers = (*STUCK_CHALLENGE_TITLE_MARKERS, *STUCK_CHALLENGE_TEXT_MARKERS, *STUCK_CHALLENGE_URL_MARKERS,
               *STUCK_LOGIN_MARKERS, *STUCK_CODE_MARKERS)
    assert markers and all(marker == marker.casefold() for marker in markers)


def test_the_main_brave_command_names_open_by_its_absolute_path():
    """A changed PATH can never swap in another ``open`` (design §3, Task 6)."""
    assert MAIN_BROWSER_OPEN_ARGV == ("/usr/bin/open", "-a", "Brave Browser")
