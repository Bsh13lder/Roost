"""C3 Task 2: computer use stays on the sites you named."""

from __future__ import annotations

from roost.computer_use.fence import SiteFence, fence_from


def test_fence_takes_hosts_from_your_messages_including_bare_domains() -> None:
    fence = fence_from(["find jobs on upwork.com please", "and check https://www.linkedin.com/jobs/view/1"], ())
    assert fence.hosts == frozenset({"upwork.com", "linkedin.com"})
    assert fence.allows("upwork.com")
    assert fence.allows("www.linkedin.com")


def test_fence_allows_subdomains_not_lookalikes() -> None:
    fence = fence_from(["go to upwork.com"], ())
    assert fence.allows("www.upwork.com")
    assert fence.allows("WWW.Upwork.com.")
    assert not fence.allows("upwork.com.evil.io")
    assert not fence.allows("notupwork.com")
    assert not fence.allows("")
    assert not fence.allows("bad host")


def test_fence_ignores_links_from_pages() -> None:
    fence = fence_from(["search wikipedia.org for owls"], ())
    page_text = "Visit https://evil.io/owls for more owls"
    assert not fence.allows("evil.io")
    assert fence_from(["search wikipedia.org for owls"], ()) == fence
    assert "evil.io" not in fence.hosts and page_text


def test_approved_hosts_and_with_host_widen_it() -> None:
    fence = fence_from(["open example.com"], ["accounts.example.org"])
    assert fence.allows("accounts.example.org")
    assert not fence.allows("example.org")
    wider = fence.with_host("Login.Example.net")
    assert wider.allows("login.example.net")
    assert not fence.allows("login.example.net")
    assert wider.with_host("not a host") == wider


def test_fence_normalises_idna() -> None:
    fence = fence_from(["mira https://münchen.de/stadt"], ())
    assert fence.hosts == frozenset({"xn--mnchen-3ya.de"})
    assert fence.allows("münchen.de")
    assert fence.allows("www.xn--mnchen-3ya.de")


def test_an_empty_fence_allows_nothing() -> None:
    assert not SiteFence(frozenset()).allows("example.com")
    assert fence_from(["no links here"], ()).hosts == frozenset()
