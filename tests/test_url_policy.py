"""Tests for ``roost.desk.url_policy.check_url`` — the bot browser's
pre-navigation policy (Task 9 brief). DNS-level blocking (a public name
that *resolves* to a private address) is the egress proxy's job (Task 7,
``tests/test_proxy_policy.py``); this module only judges a URL by its
scheme, literal host and port — no network access, ever.
"""

from __future__ import annotations

import pytest

from roost.desk.url_policy import UrlBlocked, check_url

_ALLOWED_URLS = [
    "https://elpais.com/",
    "http://example.com/a?b=1",
]

_BLOCKED_URLS = [
    "file:///etc/passwd",
    "chrome://settings",
    "brave://settings",
    "javascript:alert(1)",
    "data:text/html,x",
    "http://localhost:18789",
    "http://127.0.0.1",
    "http://[::1]/",
    "http://192.168.1.1",
    "http://10.1.2.3",
    "http://printer.local",
    "http://x.internal",
    "http://100.64.0.1",  # RFC 6598 CGNAT shared address space
    "http://example.com:9222",
    "https://u:p@example.com",
    # Fix round 1, finding 3: host forms Chromium itself canonicalizes
    # before navigating -- check_url must judge the *canonical* form,
    # not the literal string, or every one of these sails straight past
    # the string-level check and reaches a home-network address anyway.
    "http://192.168.1",  # WHATWG short IPv4 -> 192.168.0.1 (private)
    "http://3232235777/",  # WHATWG decimal IPv4 -> 192.168.1.1 (private)
    "http://0x7f.1:8080/",  # WHATWG hex+short IPv4 -> 127.0.0.1 (loopback)
    "http://127.1:8080/",  # WHATWG short IPv4 -> 127.0.0.1 (loopback)
    "http://0/",  # WHATWG short IPv4 -> 0.0.0.0 (unspecified)
    "http://１９２.１６８.1.1/",  # fullwidth digits -> 192.168.1.1 (NFKC)
    "http://localhost./",  # trailing dot -> localhost
    "http://foo.localhost/",  # Chromium resolves *.localhost to loopback
    "http://printer.local./",  # trailing dot -> printer.local
    "http://0177.1/",  # WHATWG octal IPv4 (0177 octal = 127) -> 127.0.0.1
    # Malformed IPv4/IPv6-literal *attempts* -- a browser refuses to
    # navigate to these at all (never falls back to treating them as an
    # ordinary hostname), so check_url must refuse them too.
    "http://1.2.3.4.5/",  # more than 4 parts
    "http://abc.1/",  # ends in a number, but an earlier part isn't one
    "http://1.99999999999/",  # last part doesn't fit the remaining bits
    "http://999.1.1.1/",  # a non-last part over 255
    "http://0x.1/",  # bare "0x" hex prefix with nothing after it (= 0)
    "http://[::zzzz]/",  # not a parseable IPv6 literal
    "http://.../path",  # every label empty once the trailing dot is stripped
]


@pytest.mark.parametrize("url", _ALLOWED_URLS)
def test_allowed_url_round_trips_through_normalization(url: str) -> None:
    # Both of these happen to already be in canonical form (plain ASCII
    # host, no explicit default port), so normalization is a no-op here
    # -- see test_normalizes_a_noncanonical_ipv4_literal_to_canonical_form
    # below for a case where the returned value actually differs from
    # the input (Fix round 1, finding 1: check_url must return the
    # *normalized* URL, not the raw input unchanged).
    assert check_url(url) == url


def test_allowed_public_ipv6_literal_is_normalized_and_returned() -> None:
    # A public IPv6 literal (Google's public resolver) must be allowed
    # through, not just every blocked form -- covers check_url's IPv6
    # "allowed" path, the mirror image of
    # test_ipv4_mapped_ipv6_literal_wrapping_a_private_address_is_blocked.
    assert check_url("http://[2001:4860:4860::8888]/") == "http://[2001:4860:4860::8888]/"


def test_normalizes_a_noncanonical_ipv4_literal_to_canonical_form() -> None:
    # 134744072 is the WHATWG short/decimal form of 8.8.8.8 (public, so
    # not blocked) -- the contract requires check_url to return the
    # normalized URL Chromium will actually navigate to, not the literal
    # input string.
    assert check_url("http://134744072/") == "http://8.8.8.8/"


@pytest.mark.parametrize("url", _BLOCKED_URLS)
def test_blocked_url_raises(url: str) -> None:
    with pytest.raises(UrlBlocked):
        check_url(url)


def test_url_blocked_is_a_value_error_subclass() -> None:
    assert issubclass(UrlBlocked, ValueError)


def test_blocked_url_message_names_the_url_or_reason() -> None:
    with pytest.raises(UrlBlocked) as exc_info:
        check_url("http://127.0.0.1")
    assert str(exc_info.value)  # non-empty, human-readable


def test_missing_host_is_blocked() -> None:
    with pytest.raises(UrlBlocked):
        check_url("http:///path")


def test_https_default_port_443_is_not_treated_as_sensitive() -> None:
    assert check_url("https://example.com/") == "https://example.com/"


def test_explicit_allowed_port_is_not_blocked() -> None:
    assert check_url("http://example.com:8080/") == "http://example.com:8080/"


def test_hostname_matching_is_case_insensitive_for_local_suffixes() -> None:
    with pytest.raises(UrlBlocked):
        check_url("http://PRINTER.LOCAL")


def test_ipv4_mapped_ipv6_literal_wrapping_a_private_address_is_blocked() -> None:
    with pytest.raises(UrlBlocked):
        check_url("http://[::ffff:192.168.1.1]/")


def test_host_label_that_cannot_be_idna_encoded_is_blocked() -> None:
    # An empty label (two dots back to back) isn't a valid hostname --
    # Python's own "idna" codec raises UnicodeError encoding it, which
    # check_url must turn into UrlBlocked, not an uncaught exception.
    with pytest.raises(UrlBlocked):
        check_url("http://a..b/")


def test_host_label_over_63_characters_cannot_be_idna_encoded_and_is_blocked() -> None:
    with pytest.raises(UrlBlocked):
        check_url(f"http://{'x' * 64}.com/")
