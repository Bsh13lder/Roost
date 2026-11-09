"""URL policy for a bot's own browser tab — ``check_url`` is the one gate
every navigation goes through before ``DeskBrowserPage.open_page``
(``roost/desk/browser.py``) ever sends ``Page.navigate``.

This is a *pre-DNS*, string-level check: scheme, literal host and port
only, never a network call. Two refusals below look like they overlap
with the egress proxy's job (``roost/keeper/proxy.py``), but they are a
different control point for a different threat:

- A **literal** IP address (``http://192.168.1.1``) or a reserved local
  name (``localhost``, ``printer.local``, ``x.internal``) is refused
  here, with no DNS lookup needed — the same defense-in-depth split the
  keeper's own ``BraveLauncher`` docstring describes (``roost/keeper/
  browsers.py``): this is the first of two independent layers.
- A **public hostname that happens to resolve to a private address**
  (DNS rebinding) can only be caught by actually resolving it at
  connect time — that is the egress proxy's job (Task 7), which re-
  resolves and re-checks on every connection, never trusting a cached
  answer. ``check_url`` cannot and does not attempt that here.

Sensitive ports (every port a Roost or LazyClaw process binds, plus the
Brave/CDP and Ollama ports Roost never wants a bot reaching) are blocked
on *any* host, literal or named, mirroring the proxy's own
``_SENSITIVE_PORTS`` rule — both read from the one shared
``roost.constants.SENSITIVE_PORTS`` set.

A URL carrying userinfo (``https://user:pass@host``) is refused outright,
regardless of the host that follows: credentials embedded in a URL are a
classic phishing/credential-smuggling vector (the eye is drawn to the
trusted-looking ``host`` that follows ``user:pass@``, not to the actual
authority before it), and a bot's browser has no legitimate reason to
ever supply one.

Fix round 1, findings 1 & 3: a hostile page can steer a bot to a host
*string* that looks like an ordinary public hostname but that Chromium
itself canonicalizes into a home-network address before ever asking DNS
— ``192.168.1`` (WHATWG's short IPv4 form, -> ``192.168.0.1``),
``3232235777`` (decimal IPv4, -> ``192.168.1.1``), ``0x7f.1``/``127.1``
(-> ``127.0.0.1``), ``0`` (-> ``0.0.0.0``), fullwidth-digit hosts
(NFKC-folds to ASCII digits), ``localhost.``/``printer.local.`` (a
trailing dot Chromium strips) and ``foo.localhost`` (Chromium resolves
every ``*.localhost`` name to loopback itself, never asking DNS). A
string-level check that judges the *literal* host but then hands the
*same literal string* to ``Page.navigate`` checks one thing and
navigates to another. So ``check_url`` canonicalizes the host the same
way Chromium's own URL parser does — NFKC-normalize, IDNA-encode, parse
WHATWG-style IPv4 forms — judges *that* form, and returns the rebuilt,
canonical URL for the caller to actually navigate to, never the raw
input.
"""

from __future__ import annotations

import ipaddress
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from roost.constants import SENSITIVE_PORTS

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_ALLOWED_SCHEMES = frozenset({"http", "https"})

_DEFAULT_SCHEME_PORTS = {"http": 80, "https": 443}

# Single-label TLDs reserved by convention for local-network device
# discovery (mDNS's ".local"), private/internal naming (".internal"), or
# that Chromium itself resolves straight to loopback without ever asking
# DNS (any ``*.localhost`` name, per the WHATWG/Chromium host-parsing
# spec) — never a legitimate public destination, so refused by name
# alone, no network lookup needed.
_LOCAL_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_LOCAL_HOSTNAMES = frozenset({"localhost"})

# RFC 6598 "shared address space" (CGNAT). Python's ``ipaddress`` module
# does not count this as ``is_private`` — same gap ``roost/keeper/
# proxy.py`` works around, for the same reason.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# WHATWG IPv4-number forms: "0x"/"0X"-prefixed -> hex, a lone leading
# "0" -> octal, anything else -> decimal. Mirrors the parser every
# Chromium-based browser actually runs before a navigation, which is
# exactly why a *string-level* host check must mirror it too (see the
# module docstring).
_HEX_PREFIX = ("0x", "0X")
_DECIMAL_DIGITS = "0123456789"
_OCTAL_DIGITS = "01234567"
_HEX_DIGITS = "0123456789abcdefABCDEF"


class UrlBlocked(ValueError):
    """Raised by ``check_url`` when a URL fails the bot-browser policy."""


def _ip_is_blocked(ip: IPAddress) -> bool:
    """True if ``ip`` (already parsed) is loopback, private, link-local,
    CGNAT, multicast, unspecified or reserved — the address itself must
    never host a sensitive-port navigation, so ``check_url`` never needs
    to resolve a literal IP to know whether it's blocked."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # An IPv4-mapped IPv6 literal (::ffff:a.b.c.d) must be judged by
        # the IPv4 address it wraps, not waved through because the outer
        # address "looks" like a routable IPv6 one.
        ip = ip.ipv4_mapped

    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return True
    return bool(
        ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved or ip.is_private
    )


def _is_local_hostname(hostname: str) -> bool:
    return hostname in _LOCAL_HOSTNAMES or hostname.endswith(_LOCAL_HOST_SUFFIXES)


def to_ascii_host(hostname: str) -> str:
    """NFKC-normalize (folds fullwidth/compatibility digits like
    ``１`` to ASCII ``1``, the same mapping Chromium's URL host
    parser applies before punycode) then IDNA-encode ``hostname``.
    Raises ``UrlBlocked`` if it can't be encoded (an invalid label, a
    label that's too long, ...) or if anything non-ASCII survives --
    this is a defensive bot browser, not a general-purpose URL parser,
    so anything that doesn't resolve to a clean ASCII host is refused
    rather than guessed at.

    Shared with ``roost.talk.links`` (Fix round 1, S1 Task 4): the Links
    tab needs this same IDNA form so a homograph host (Cyrillic ``а`` in
    ``аpple.com``) is shown as its punycode, never as a label that reads
    identically to a trusted domain.
    """
    normalized = unicodedata.normalize("NFKC", hostname)
    try:
        ascii_host = normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlBlocked(f"host {hostname!r} is not a valid hostname") from exc
    if not ascii_host.isascii():
        raise UrlBlocked(f"host {hostname!r} is not a valid hostname")
    return ascii_host


def _parse_ipv4_number(part: str) -> int | None:
    """One WHATWG IPv4-number part: decimal, or ``0x``/``0X``-prefixed
    hex, or a leading-zero octal part. Returns ``None`` if ``part`` isn't
    a number in any of those forms at all (an ordinary hostname label),
    never for a number that's merely out of range -- range is the
    caller's job, so a too-big number still signals "this was an IPv4
    attempt" rather than silently falling back to "it's just a domain"."""
    if part == "":
        return None

    radix, digits, body = 10, _DECIMAL_DIGITS, part
    if body.startswith(_HEX_PREFIX):
        radix, digits, body = 16, _HEX_DIGITS, body[2:]
    elif len(body) >= 2 and body[0] == "0":
        radix, digits, body = 8, _OCTAL_DIGITS, body[1:]

    if body == "":
        return 0
    if any(ch not in digits for ch in body):
        return None
    return int(body, radix)


def _ends_in_a_number(hostname: str) -> bool:
    """True if ``hostname``'s last dot-separated label is itself a
    number (decimal, hex or octal) -- the WHATWG signal that the *whole*
    host must be parsed as an IPv4 literal (and refused outright if it
    doesn't parse as one), not treated as an ordinary domain name."""
    last = hostname.rsplit(".", 1)[-1]
    if last == "":
        return False
    return last.isdigit() or _parse_ipv4_number(last) is not None


def _parse_ipv4(hostname: str) -> ipaddress.IPv4Address:
    """Parse ``hostname`` as a WHATWG-style IPv4 literal: 1-4 dot-
    separated decimal/octal/hex parts, with the last part absorbing
    whatever bits the earlier parts don't cover (``127.1`` is
    ``127.0.0.1``, ``3232235777`` is ``192.168.1.1``) -- the exact
    canonicalization every Chromium-based browser applies before
    navigating. Only called once ``_ends_in_a_number`` has already
    decided ``hostname`` is an IPv4 *attempt*, so any failure here means
    a malformed literal (e.g. a part over 255, or too many parts) --
    raises ``UrlBlocked`` rather than falling back to treating it as an
    ordinary hostname, since a browser would refuse to navigate at all.
    """
    parts = hostname.split(".")
    if len(parts) > 4:
        raise UrlBlocked(f"host {hostname!r} is not a valid IPv4 literal")

    numbers: list[int] = []
    for part in parts:
        value = _parse_ipv4_number(part)
        if value is None:
            raise UrlBlocked(f"host {hostname!r} is not a valid IPv4 literal")
        numbers.append(value)

    if any(n > 255 for n in numbers[:-1]):
        raise UrlBlocked(f"host {hostname!r} is not a valid IPv4 literal")
    if numbers[-1] >= 256 ** (5 - len(numbers)):
        raise UrlBlocked(f"host {hostname!r} is not a valid IPv4 literal")

    value = numbers[-1]
    for index, number in enumerate(numbers[:-1]):
        value += number << (8 * (3 - index))
    return ipaddress.IPv4Address(value)


def _canonicalize_host(raw_hostname: str) -> tuple[str, bool]:
    """Return ``(host, is_ipv6)`` for the canonical form ``raw_hostname``
    resolves to -- the exact string a browser would actually navigate
    to -- or raise ``UrlBlocked``. ``raw_hostname`` is already lowercased
    and bracket-stripped by ``urlsplit``."""
    if ":" in raw_hostname:
        # A bracketed IPv6 literal (``urlsplit.hostname`` already
        # stripped the brackets) -- never NFKC/IDNA-normalized, since
        # colons and hex digits aren't domain characters at all.
        try:
            ip6 = ipaddress.IPv6Address(raw_hostname)
        except ValueError as exc:
            raise UrlBlocked(f"host {raw_hostname!r} is not a valid IPv6 literal") from exc
        if _ip_is_blocked(ip6):
            raise UrlBlocked(f"host {raw_hostname!r} is a private, loopback or reserved address")
        return str(ip6), True

    # A single trailing dot denotes the DNS root and is never significant
    # to the policy below -- Chromium strips it before resolving, so
    # ``localhost.``/``printer.local.`` must be judged exactly like
    # ``localhost``/``printer.local``, not waved through as some other
    # hostname because of one extra character.
    stripped = raw_hostname.rstrip(".")
    if not stripped:
        raise UrlBlocked(f"host {raw_hostname!r} has no host")

    ascii_host = to_ascii_host(stripped)

    if _is_local_hostname(ascii_host):
        raise UrlBlocked(f"host {ascii_host!r} is a reserved local-network name")

    if _ends_in_a_number(ascii_host):
        ip4 = _parse_ipv4(ascii_host)
        if _ip_is_blocked(ip4):
            raise UrlBlocked(f"host {raw_hostname!r} is a private, loopback or reserved address")
        return str(ip4), False

    return ascii_host, False


def _rebuild_netloc(host: str, port: int | None, is_ipv6: bool) -> str:
    host_part = f"[{host}]" if is_ipv6 else host
    return host_part if port is None else f"{host_part}:{port}"


def check_url(url: str) -> str:
    """Return the *normalized* URL if the bot's browser may navigate to
    it, else raise ``UrlBlocked`` with a human-readable reason.

    The returned URL is the canonical form Chromium's own URL parser
    would resolve ``url`` to — same scheme, path, query and fragment,
    but with the host rebuilt from whatever canonicalization applied
    (NFKC folding, IDNA encoding, WHATWG IPv4-literal parsing) — because
    that canonical form, not the raw input, is what ``Page.navigate``
    actually sends the browser to (see the module docstring, Fix round 1
    findings 1 & 3).
    """
    try:
        # Newer Pythons (the bracketed-host hardening landed in 3.13)
        # already reject a malformed bracketed IPv6 literal (``[::zzzz]``)
        # inside urlsplit itself, raising a plain ValueError rather than
        # ever handing back a parsed result -- this is still a URL this
        # bot's browser must never navigate to, so it's UrlBlocked like
        # every other refusal here, not an uncaught exception.
        parsed = urlsplit(url)
    except ValueError as exc:
        raise UrlBlocked(f"url {url!r} could not be parsed: {exc}") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlBlocked(f"scheme {parsed.scheme!r} is not allowed")

    if parsed.username is not None or parsed.password is not None:
        raise UrlBlocked("urls carrying credentials (userinfo) are not allowed")

    raw_hostname = parsed.hostname
    if not raw_hostname:
        raise UrlBlocked("url has no host")

    port = parsed.port or _DEFAULT_SCHEME_PORTS[parsed.scheme]
    if port in SENSITIVE_PORTS:
        raise UrlBlocked(f"port {port} is not allowed")

    host, is_ipv6 = _canonicalize_host(raw_hostname)

    netloc = _rebuild_netloc(host, parsed.port, is_ipv6)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
