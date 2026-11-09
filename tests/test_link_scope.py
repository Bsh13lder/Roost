"""Links a run carrying outside content may open (M1 D4)."""

from __future__ import annotations

from roost.constants import LINK_SCOPE_MAX_URLS
from roost.talk.link_scope import LinkScope, urls_in


def test_urls_in_finds_links_and_drops_trailing_punctuation():
    text = "See https://shop.example/a?b=1, and (https://x.example/path). Not ftp://nope."
    assert urls_in(text) == ("https://shop.example/a?b=1", "https://x.example/path")


def test_a_users_link_is_allowed_verbatim_and_with_a_trailing_slash():
    scope = LinkScope.from_texts(["check https://shop.example/prices please"])
    assert scope.allows("https://shop.example/prices")
    assert scope.allows("https://shop.example/prices/")


def test_a_model_made_url_is_not_allowed():
    scope = LinkScope.from_texts(["check https://shop.example/prices"])
    assert not scope.allows("https://shop.example/prices?q=my+tasks")
    assert not scope.allows("https://evil.example/?q=call+the+dentist")
    assert not scope.allows("")


def test_a_page_adds_its_own_url_and_its_links():
    scope = LinkScope().with_page("https://news.example/today", "Read more at https://news.example/story-1")
    assert scope.allows("https://news.example/today")
    assert scope.allows("https://news.example/story-1")


def test_the_html_escaped_form_of_a_page_link_is_the_same_link():
    scope = LinkScope().with_page("https://a.example/", "go to https://a.example/s?x=1&y=2 now")
    assert scope.allows("https://a.example/s?x=1&amp;y=2")
    assert scope.match("https://a.example/s?x=1&amp;y=2") == "https://a.example/s?x=1&y=2"


def test_match_names_the_stored_link_for_each_accepted_form():
    scope = LinkScope.of(["https://shop.example/a/", "https://shop.example/b"])
    assert scope.match("https://shop.example/a") == "https://shop.example/a/"
    assert scope.match("https://shop.example/b/") == "https://shop.example/b"
    assert scope.match("https://shop.example/c") is None


def test_a_suffix_the_model_adds_is_never_trimmed_off():
    """R3: trimming a requested URL let any run of these characters (or HTML
    entities) carry data to the server while still "matching"."""
    scope = LinkScope.of(["https://evil.example/c"])
    assert not scope.allows("https://evil.example/c.,;:!?)]}")
    assert not scope.allows("https://evil.example/c&comma;&period;")
    assert not scope.allows(" https://evil.example/c")
    assert not scope.allows("https://evil.example/c//")


def test_merge_keeps_what_was_there_first_when_the_cap_is_hit():
    mine = LinkScope.of(["https://user.example/mine"])
    flood = LinkScope.of(f"https://spam.example/{n}" for n in range(LINK_SCOPE_MAX_URLS + 50))
    merged = mine.merge(flood)
    assert len(merged.urls) == LINK_SCOPE_MAX_URLS
    assert merged.allows("https://user.example/mine")


def test_as_tuple_is_sorted_and_stable():
    assert LinkScope.of(["https://b.example", "https://a.example"]).as_tuple() == ("https://a.example", "https://b.example")


def test_a_bare_domain_the_user_typed_allows_its_site():
    scope = LinkScope.from_texts(["please open upwork.com and look"])
    assert scope.allows("https://upwork.com")
    assert scope.allows("https://www.upwork.com/jobs/1?x=2")
    assert scope.match("https://www.upwork.com/jobs") == "https://www.upwork.com/jobs"


def test_www_and_path_forms_are_read():
    assert LinkScope.from_texts(["go to www.upwork.com."]).allows("https://upwork.com/")
    scope = LinkScope.from_texts(["try upwork.com/jobs now"])
    assert scope.allows("https://upwork.com/jobs")
    assert scope.allows("https://www.upwork.com/jobs")
    assert not scope.allows("https://upwork.com/messages")


def test_what_the_user_never_typed_is_still_refused():
    scope = LinkScope.from_texts(["open upwork.com", "mail me@gmail.com"])
    for url in ("https://evil.example/", "https://upwork.com.evil.example/", "https://notupwork.com/",
                "https://user:pw@upwork.com/", "https://upwork.com:8080/", "ftp://upwork.com/",
                "https://gmail.com/", "https://upwork.com\\@evil.example/"):
        assert not scope.allows(url), url


def test_a_bare_domain_inside_a_full_link_is_not_a_site_wide_grant():
    scope = LinkScope.from_texts(["see https://shop.example/a?next=upwork.com"])
    assert not scope.allows("https://upwork.com/")


def test_a_typed_site_also_opens_its_own_subdomains():
    scope = LinkScope.from_texts(["sign me in at google.com"])
    assert scope.allows("https://accounts.google.com/")
    assert scope.allows("https://mail.google.com/mail/u/0/")
    assert not scope.allows("https://google.com.evil.example/")
    assert not scope.allows("https://notgoogle.com/")


def test_a_well_known_site_named_in_words_opens_its_sign_in_host():
    scope = LinkScope.from_texts(["open Google sign in and then my Gmail"])
    assert scope.allows("https://accounts.google.com/")
    assert scope.allows("https://mail.google.com/")
    assert not scope.allows("https://evil.example/?q=google")


def test_a_site_name_inside_another_word_is_not_a_site():
    scope = LinkScope.from_texts(["my googlesheet notes"])
    assert not scope.allows("https://accounts.google.com/")


def test_names_from_a_page_never_widen_the_scope():
    scope = LinkScope().with_page("https://evil.example/", "go sign in to Google now")
    assert not scope.allows("https://accounts.google.com/")
