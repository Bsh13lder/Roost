"""Tests for ``roost.desk.signing`` — HMAC request signing shared by the
gateway's keeper client and the keeper's own request-auth dependency.

The round-trip/tamper/replay/staleness test is given verbatim by the Task 5
brief (contract.md ``signed_headers``/``verify`` signatures); the rest cover
``NonceCache`` eviction and header-shape edge cases the brief's single test
doesn't reach.
"""

from __future__ import annotations

import time

from roost.desk.signing import NonceCache, sign, signed_headers, verify


def test_sign_verify_roundtrip_and_tamper():
    h = signed_headers("s3cret", "POST", "/desks/x/browser/start", b"{}")
    seen = NonceCache()
    assert verify("s3cret", "POST", "/desks/x/browser/start", b"{}", h, now=int(h["X-Roost-Ts"]), seen=seen)
    assert not verify("s3cret", "POST", "/desks/x/browser/start", b"{}", h, now=int(h["X-Roost-Ts"]), seen=seen)  # replay
    h2 = signed_headers("s3cret", "POST", "/p", b"{}")
    assert not verify("s3cret", "POST", "/p", b'{"a":1}', h2, now=int(h2["X-Roost-Ts"]), seen=NonceCache())  # body changed
    h3 = signed_headers("s3cret", "GET", "/p", b"")
    assert not verify("s3cret", "GET", "/p", b"", h3, now=int(h3["X-Roost-Ts"]) + 31, seen=NonceCache())     # stale


def test_signed_headers_has_exactly_the_three_header_names():
    h = signed_headers("s3cret", "GET", "/p", b"")
    assert set(h) == {"X-Roost-Ts", "X-Roost-Nonce", "X-Roost-Sig"}


def test_verify_rejects_wrong_secret():
    h = signed_headers("s3cret", "GET", "/p", b"")
    assert not verify("different-secret", "GET", "/p", b"", h, now=int(h["X-Roost-Ts"]), seen=NonceCache())


def test_verify_rejects_wrong_method_or_path():
    h = signed_headers("s3cret", "POST", "/a", b"{}")
    now = int(h["X-Roost-Ts"])
    assert not verify("s3cret", "GET", "/a", b"{}", h, now=now, seen=NonceCache())
    assert not verify("s3cret", "POST", "/b", b"{}", h, now=now, seen=NonceCache())


def test_verify_rejects_missing_headers():
    assert not verify("s3cret", "GET", "/p", b"", {}, now=int(time.time()), seen=NonceCache())


def test_verify_accepts_within_30s_clock_skew_both_directions():
    h = signed_headers("s3cret", "GET", "/p", b"")
    ts = int(h["X-Roost-Ts"])
    assert verify("s3cret", "GET", "/p", b"", h, now=ts - 30, seen=NonceCache())
    assert verify("s3cret", "GET", "/p", b"", h, now=ts + 30, seen=NonceCache())


def test_sign_is_deterministic_for_same_inputs():
    sig1 = sign("s3cret", "GET", "/p", b"", 1000, "abc")
    sig2 = sign("s3cret", "GET", "/p", b"", 1000, "abc")
    assert sig1 == sig2


def test_nonce_cache_evicts_after_ttl():
    cache = NonceCache()
    cache.remember("n1", now=0)
    assert cache.seen_recently("n1", now=0)
    assert cache.seen_recently("n1", now=119)
    assert not cache.seen_recently("n1", now=121)
