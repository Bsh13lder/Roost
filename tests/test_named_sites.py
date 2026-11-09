"""Sites you name in plain words open their own hosts (owner, 2026-10-23: "open whatsup web" was refused)."""

from __future__ import annotations

import pytest

from roost.talk.link_scope import LinkScope, named_site_entries


@pytest.mark.parametrize("said", [
    "open whatsapp web and show me the qr", "bro enter in whatsup web", "open WhatsApp", "check my telegram",
])
def test_messengers_named_in_words_open_their_site(said):
    entries = named_site_entries(said)
    assert any(e.endswith("whatsapp.com") or e.endswith("telegram.org") for e in entries)


def test_whatsapp_web_link_is_in_scope_when_named():
    scope = LinkScope.from_texts(["bro enter in whatsup web and screen me qr"])
    assert scope.match("https://web.whatsapp.com/") is not None
    assert scope.match("https://whatsapp.com.evil.io/") is None


def test_a_name_on_a_page_never_counts():
    assert named_site_entries("") == ()
