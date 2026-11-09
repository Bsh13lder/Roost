"""Is the bot stuck on this page? (stuck flow Piece A, design R2/R3).

``detect_block`` is a pure function of one ``PageText``: no I/O, no clock, no clicks. It never
solves anything and never changes the browser. It never returns reason ``"asked"``: only the bot's
own ``ask_for_help`` call raises that one.

A page whose text is at most ``STUCK_THIN_PAGE_CHARS`` long is *thin*: a wall, not content. Words
like "verify you are human", a captcha frame or a password box block a thin page, but on a long
page they are an article or a site header. When several rules match, the first wins:
challenge > login > code > refused. A challenge title marker counts only at the start of the title.
Every marker (``roost/constants.py``) is matched against casefolded text. Login markers match whole
words only (see ``_has_word_marker``), so "catalog in" or "/blog/designing-a-rain-garden" is not a
sign-in page.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from roost.constants import (
    STUCK_CHALLENGE_TEXT_MARKERS,
    STUCK_CHALLENGE_TITLE_MARKERS,
    STUCK_CHALLENGE_URL_MARKERS,
    STUCK_CODE_MARKERS,
    STUCK_LOGIN_MARKERS,
    STUCK_REFUSED_STATUSES,
    STUCK_THIN_PAGE_CHARS,
)
from roost.desk import PageText

BlockReason = Literal["challenge", "login", "code", "refused", "asked"]

# Runs of anything that is not a letter or digit; "_" is a separator too, so "/users/sign_in" (Devise)
# and "/users/log_in" (Phoenix) read as the words "sign in" and "log in".
_WORD_SEPARATORS = re.compile(r"[\W_]+")


@dataclass(frozen=True)
class Block:
    """Why the bot can't go on, and where. ``note`` is the bot's own words (``ask_for_help``'s
    reason) and ``suggest_main_browser`` its own suggestion; the detector leaves both empty."""

    reason: BlockReason
    url: str
    host: str
    note: str = ""
    suggest_main_browser: bool = False
    sign_in: bool = False       # the bot asked you to sign in (request_sign_in, or ask_for_help naming a sign-in)
    field: str = ""             # B3: "password" or "code" when the bot asked for a secret field (ask_secret_field)


def host_of_url(url: str) -> str:
    """The URL's host name, lowercased. A URL with no host (``about:blank``) or one that can't be
    parsed is its own host, and ``""`` stays ``""``."""
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


def names_sign_in(text: str) -> bool:
    """The bot's own words ask for a sign-in ("please log in to …"): a login marker as whole words."""
    return _has_word_marker(text, STUCK_LOGIN_MARKERS)


def is_thin(page: PageText) -> bool:
    return len(page.text) <= STUCK_THIN_PAGE_CHARS


def detect_block(page: PageText) -> Block | None:
    """The block this page puts in the bot's way, or ``None`` when it is ordinary content."""
    reason = _reason(page)
    if reason is None:
        return None
    return Block(reason=reason, url=page.url, host=host_of_url(page.url))


def _reason(page: PageText) -> BlockReason | None:
    thin = is_thin(page)
    if _is_challenge(page, thin):
        return "challenge"
    if _is_login(page, thin):
        return "login"
    if _is_code(page, thin):
        return "code"
    if page.status in STUCK_REFUSED_STATUSES:
        return "refused"
    return None


def _is_challenge(page: PageText, thin: bool) -> bool:
    """A challenge title or a ``__cf_chl`` address counts at any length; challenge words and a
    visible captcha frame count only on a thin page."""
    if _is_challenge_title(page.title, thin) or _has_marker(page.url, STUCK_CHALLENGE_URL_MARKERS):
        return True
    return thin and (page.captcha_frame or _has_marker(page.text, STUCK_CHALLENGE_TEXT_MARKERS))


def _is_challenge_title(title: str, thin: bool) -> bool:
    """A marker counts only at the *start* of the trimmed, casefolded title, which is how Cloudflare's
    titles read ("Just a moment...", "Attention Required! | Cloudflare"). When the title then runs on
    in words ("Just a moment of calm"), it is a headline, so it counts only on a thin page."""
    folded = title.strip().casefold()
    for marker in STUCK_CHALLENGE_TITLE_MARKERS:
        if folded.startswith(marker):
            rest = folded[len(marker):].lstrip()
            if thin or not rest or not rest[0].isalnum():
                return True
    return False


def _is_login(page: PageText, thin: bool) -> bool:
    """A password box on a thin page, or under a login title or address path. The host and the
    query never count: ``login.example/garden`` or ``?came_from=login`` is not a sign-in page."""
    if not page.password_field:
        return False
    if thin:
        return True
    return _has_word_marker(page.title, STUCK_LOGIN_MARKERS) or _has_word_marker(
        _url_path(page.url), STUCK_LOGIN_MARKERS)


def _is_code(page: PageText, thin: bool) -> bool:
    return thin and _has_marker(page.text, STUCK_CODE_MARKERS)


def _has_marker(haystack: str, markers: Iterable[str]) -> bool:
    folded = haystack.casefold()
    return any(marker in folded for marker in markers)


def _words(text: str) -> tuple[str, ...]:
    """The casefolded text split into its words: letters and digits between separators."""
    return tuple(word for word in _WORD_SEPARATORS.split(text.casefold()) if word)


def _has_word_marker(haystack: str, markers: Iterable[str]) -> bool:
    """True when a marker's words appear in the haystack as whole, consecutive words. "Log in",
    "log-in" and "log_in" are all the words (log, in); "catalog in" or "blog index" are not."""
    words = _words(haystack)
    for marker in markers:
        run = _words(marker)
        if run and any(words[start:start + len(run)] == run for start in range(len(words) - len(run) + 1)):
            return True
    return False


def _url_path(url: str) -> str:
    try:
        return urlsplit(url).path
    except ValueError:
        return ""
