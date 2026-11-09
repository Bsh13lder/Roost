"""A routine's watch (owner, 2026-11-04): "Only run when the page changes".

A watch is a page address, the part to watch in plain words ("the physio chat", "the price box"; empty: the whole
page) and how often Roost checks it, never more often than every ``WATCH_EVERY_MIN_MINUTES``. The address passes the
same rule as an Open card's (``askable_url``: http(s), no credentials, no port, the URL policy), so a watch never
opens what ``open_page`` could not. ``parse_watch`` is the one door for every writer: the routes, the bot's routine
tools and an approved proposal. ``{"off": true}`` (or None) means no watch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    WATCH_EVERY_DEFAULT_MINUTES, WATCH_EVERY_MAX_MINUTES, WATCH_EVERY_MIN_MINUTES, WATCH_PART_MAX, WATCH_URL_MAX,
)
from roost.talk.new_site import askable_url, url_host

BAD_URL_TEXT = "That address can't be watched. Use a full web address, like https://web.whatsapp.com."
BAD_EVERY_TEXT = (f"A watch checks the page every {WATCH_EVERY_MIN_MINUTES} to {WATCH_EVERY_MAX_MINUTES} "
                  "minutes.")
BAD_PART_TEXT = f"Say what part to watch in up to {WATCH_PART_MAX} characters."
NO_WATCH_WORDS = "Runs on its schedule"
BAD_WATCH_TEXT = "A watch needs a page address (url), what part to watch (part) and every_min."


class WatchRefused(ValueError):
    """A watch that can't be kept; ``text`` is the plain sentence to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


@dataclass(frozen=True)
class Watch:
    url: str
    part: str
    every_min: int

    @property
    def host(self) -> str:
        return url_host(self.url)


class WatchIn(BaseModel):
    """What crosses a boundary (a route body, a tool argument, a proposal payload)."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(default="", max_length=WATCH_URL_MAX)
    part: str = Field(default="", max_length=WATCH_PART_MAX * 2)
    every_min: int = WATCH_EVERY_DEFAULT_MINUTES
    off: bool = False


def parse_watch(raw: Mapping[str, Any] | WatchIn | None) -> Watch | None:
    """The watch ``raw`` asks for, or None for no watch. Raises ``WatchRefused`` with a plain sentence."""
    if raw is None:
        return None
    try:
        given = raw if isinstance(raw, WatchIn) else WatchIn.model_validate(dict(raw))
    except (ValidationError, TypeError, ValueError):
        raise WatchRefused(BAD_WATCH_TEXT) from None
    if given.off:
        return None
    url = askable_url(given.url)
    if url is None:
        raise WatchRefused(BAD_URL_TEXT)
    if not WATCH_EVERY_MIN_MINUTES <= given.every_min <= WATCH_EVERY_MAX_MINUTES:
        raise WatchRefused(BAD_EVERY_TEXT)
    part = " ".join(given.part.split())
    if len(part) > WATCH_PART_MAX:
        raise WatchRefused(BAD_PART_TEXT)
    return Watch(url=url, part=part, every_min=given.every_min)


def next_check(watch: Watch, now: datetime) -> datetime:
    """When the next check is due: ``every_min`` from now, at whole seconds."""
    return (now + timedelta(minutes=watch.every_min)).replace(microsecond=0)


def watch_out(watch: Watch | None) -> dict[str, Any] | None:
    if watch is None:
        return None
    return {"url": watch.url, "part": watch.part, "every_min": watch.every_min, "host": watch.host}


def watch_words(watch: Watch) -> str:
    """"Watching web.whatsapp.com · every 5 min": a watching routine's words in its row, list_routines and cards."""
    return f"Watching {watch.host} · every {watch.every_min} min"


def watch_summary(watch: Watch | None) -> str:
    """A watch in full for a card ("Only when https://… changes (the physio chat), checked every 5 min")."""
    if watch is None:
        return NO_WATCH_WORDS
    return f"Only when {watch.url} changes ({watch.part or 'the whole page'}), checked every {watch.every_min} min"
