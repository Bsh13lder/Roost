"""Connectors: the address rules (host lock, SSRF literals and names) and the path rules (design §2)."""

from __future__ import annotations

import pytest

from roost.connectors.address import (
    AddressRefused, address_ok, build_url, check_base_url, check_prefix, is_public_ip,
)


@pytest.mark.parametrize("url", [
    "https://api.example.com",
    "https://api.example.com/",
    "https://api.example.com/v1",
    "https://API.Example.com:443/v1/",
    "https://8.8.8.8/x",
])
def test_good_bases(url):
    base = check_base_url(url)
    assert base.host == base.host.lower() and base.url.startswith("https://")
    assert not base.url.endswith("/")


@pytest.mark.parametrize("url", [
    "http://api.example.com",                  # https only
    "ftp://api.example.com",
    "https://user:pw@api.example.com",          # credentials
    "https://user@api.example.com",
    "https://api.example.com:8443",             # port tricks
    "https://api.example.com:80",
    "https://api.example.com/v1?key=1",          # no query
    "https://api.example.com/v1#frag",
    "https://localhost",
    "https://localhost/v1",
    "https://foo.localhost",
    "https://printer.local",
    "https://db.internal",
    "https://router.home.arpa",
    "https://127.0.0.1",
    "https://127.1.2.3",
    "https://10.0.0.1",
    "https://172.16.0.5",
    "https://192.168.1.1",
    "https://169.254.169.254",
    "https://100.64.0.1",
    "https://0.0.0.0",
    "https://[::1]",
    "https://[fe80::1]",
    "https://[fd00::1]",
    "https://[::ffff:127.0.0.1]",
    "https://2130706433",                        # decimal 127.0.0.1
    "https://0x7f000001",
    "https://017700000001",
    "https://intranet",                          # no dot
    "https://a.b.123",                           # numeric top label
    "https://",
    "not a url",
    "https://exa mple.com",
    "https://example.com\\@evil.com",
])
def test_bad_bases(url):
    with pytest.raises(AddressRefused):
        check_base_url(url)


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True), ("1.1.1.1", True), ("2606:4700::1111", True),
    ("127.0.0.1", False), ("10.1.2.3", False), ("172.31.255.255", False), ("192.168.0.1", False),
    ("169.254.1.1", False), ("100.64.0.1", False), ("0.0.0.0", False), ("224.0.0.1", False),
    ("::1", False), ("fe80::1", False), ("fc00::1", False), ("::ffff:10.0.0.1", False), ("::", False),
    ("not-an-ip", False),
])
def test_is_public_ip(ip, public):
    assert is_public_ip(ip) is public


def test_address_ok_needs_every_address_public():
    assert address_ok(["8.8.8.8", "1.1.1.1"])
    assert not address_ok(["8.8.8.8", "10.0.0.1"])
    assert not address_ok([])


def test_build_url_stays_under_base_and_prefixes():
    base = check_base_url("https://api.example.com/v1")
    assert build_url(base, "/sites", ()) == "https://api.example.com/v1/sites"
    assert build_url(base, "/sites/a%20b", ("/sites",)) == "https://api.example.com/v1/sites/a%20b"
    assert build_url(base, "/sites", ("/sites/",)) == "https://api.example.com/v1/sites"
    with pytest.raises(AddressRefused):
        build_url(base, "/sitesmaps", ("/sites",))   # a prefix matches itself or itself + "/…"
    with pytest.raises(AddressRefused):
        build_url(base, "/other", ("/sites",))


@pytest.mark.parametrize("path", [
    "sites",                       # must start with /
    "//evil.com/x",
    "https://evil.com/x",
    "/x://y",
    "/a\\b",
    "/a?b=1",
    "/a#b",
    "/../admin",
    "/a/../../b",
    "/a/./b",
    "/%2e%2e/admin",
    "/%2E%2e/admin",
    "/a/%2e/b",
    "/a\nb",
    "/a\tb",
    "",
])
def test_bad_paths(path):
    base = check_base_url("https://api.example.com/v1")
    with pytest.raises(AddressRefused):
        build_url(base, path, ())


@pytest.mark.parametrize("prefix,ok", [
    ("/sites", True), ("/sites/", True), ("/", True), ("sites", False), ("/a/../b", False), ("/a?x", False),
    ("//x", False), ("", False),
])
def test_check_prefix(prefix, ok):
    if ok:
        assert check_prefix(prefix).startswith("/")
    else:
        with pytest.raises(AddressRefused):
            check_prefix(prefix)
