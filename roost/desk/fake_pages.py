"""``FAKE_PAGES`` -- the scripted pages every ``FakeDesk`` serves by default
(stuck flow, design R11).

``ROOST_DESK=fake`` runs (every test, the Playwright E2E) never reach a real
web page, and ``check_url`` refuses every local address, so a page that stops
the bot has to live here. The hosts are under ``.example`` (RFC 2606), which
no real site can ever use, and ``check_url`` lets them through unchanged.

- ``https://login.example/`` shows a sign-in page (``LOGIN_WALL``) first, then
  the signed-in page (``SIGNED_IN``): the bot opens it and gets stuck, you
  give it back, and its next read is clear.
- ``https://challenge.example/`` shows a "Just a moment..." check twice (the
  first open and rung 1's repeat), then the page behind it (``CLEARED``).

Each page carries what the real browser reports for an ``open_page``.
``FakeDesk.read_page`` drops the ``status``, as the real ``read_page`` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from roost.desk import PageText

LOGIN_URL = "https://login.example/"
CHALLENGE_URL = "https://challenge.example/"

LOGIN_WALL = PageText(
    url=LOGIN_URL,
    title="Sign in · Login Example",
    text="Sign in\nEmail\nPassword\nSign in\nForgot your password?",
    truncated=False,
    status=200,
    password_field=True,
)

SIGNED_IN = PageText(
    url=LOGIN_URL,
    title="Your orders",
    text="Your orders\nOrder 1042: a kettle, delivered on 12 October.\nOrder 1043: a toaster, on its way.",
    truncated=False,
    status=200,
)

CHALLENGE = PageText(
    url=CHALLENGE_URL,
    title="Just a moment...",
    text=(
        "challenge.example\nVerify you are human by completing the action below.\n"
        "challenge.example needs to review the security of your connection before proceeding."
    ),
    truncated=False,
    status=403,
    captcha_frame=True,
)

CLEARED = PageText(
    url=CHALLENGE_URL,
    title="Prices",
    text="Prices\nA kettle costs 24 euros.\nA toaster costs 31 euros.",
    truncated=False,
    status=200,
)

# The fake jar's cookies at start (A1): login.example's page sets one, as a real site does, so I'm done on its
# Sign-in card saves the login once the signed-in page is in front (and never while the wall still is).
FAKE_COOKIE_DOMAINS: tuple[str, ...] = (".login.example",)

FAKE_PAGES: Mapping[str, tuple[PageText, ...]] = MappingProxyType(
    {
        LOGIN_URL: (LOGIN_WALL, SIGNED_IN),
        CHALLENGE_URL: (CHALLENGE, CHALLENGE, CLEARED),
    }
)
