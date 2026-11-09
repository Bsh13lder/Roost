from roost.talk.links import collect_links, links_in
from roost.talk.store import Message


def _m(mid: str, body: str, at: str) -> Message:
    return Message(id=mid, user_id="u", thread_id="t", role="bot", body=body, tainted=False, seq=1, created_at=at)


def test_links_in_finds_http_links_and_drops_trailing_punctuation():
    text = "see https://example.com/a, then (https://news.ycombinator.com/item?id=1). javascript:alert(1) ftp://x.y"
    assert links_in(text) == ("https://example.com/a", "https://news.ycombinator.com/item?id=1")


def test_collect_links_keeps_each_urls_newest_sighting_newest_first():
    newest_first = (
        _m("m3", "again https://example.com/a", "2026-10-14T10:00:00+00:00"),
        _m("m2", "https://elpais.com/x", "2026-10-13T10:00:00+00:00"),
        _m("m1", "first https://example.com/a", "2026-10-12T10:00:00+00:00"),
    )
    links = collect_links(newest_first, limit=10)
    assert [(l.url, l.host, l.message_id) for l in links] == [
        ("https://example.com/a", "example.com", "m3"), ("https://elpais.com/x", "elpais.com", "m2")]
    assert len(collect_links(newest_first, limit=1)) == 1


# Fix round 1: a browser reads a backslash in an http(s) URL as a forward
# slash, so "https://evil.example\@bank.com/login" actually navigates to
# evil.example -- but Python's urlsplit (what _host used) reports the host
# as "bank.com", the opposite of S1.9's "showing the real domain".
def test_links_in_drops_a_backslash_disguised_url():
    text = "see https://evil.example\\@bank.com/login"
    assert links_in(text) == ()


# Fix round 1: credentials in a URL (userinfo) are a classic trick for
# making an untrusted host look trusted; url_policy refuses them outright
# and the Links tab must too, rather than report a technically-correct but
# misleading host.
def test_links_in_drops_a_url_carrying_userinfo():
    text = "see https://user:pass@example.com/path"
    assert links_in(text) == ()


# Fix round 1: a Cyrillic "а" (U+0430) makes "аpple.com" look identical to
# "apple.com" -- the host must come back in its IDNA/ASCII (punycode) form
# so the two are visibly different, not as the deceptive Unicode label.
def test_collect_links_reports_a_homograph_host_as_punycode():
    message = _m("m1", "https://аpple.com/x", "2026-10-14T10:00:00+00:00")
    links = collect_links((message,), limit=10)
    assert [l.host for l in links] == ["xn--pple-43d.com"]
