"""The watched part of a page, found and compared with no model (owner, 2026-11-04).

Pure functions over what the bot's browser read: the page's readable areas (``roost/desk/page_text.py``) and its
whole text. ``pick_part`` finds the part the owner named in plain words, in this order:

A part that names every chat ("all chats", "chat list", or chats in the plural with no name) is the whole chat list (owner, 2026-11-11). Each name in
quotes or brackets, and each phone number, is looked for on its own, the rest of the sentence aside ("new messages from Ana in her chat
"Physio Ana"" looks for "Physio Ana"; owner, 2026-11-10); with no quotes, every meaningful word of the part is.

1. an area whose name holds every meaningful word ("the price box" -> an area named "Price box");
2. a chat that is open: the words stand in a line outside every area (a chat's header), and a message pane
   (``WATCH_PANE_ROLES``) is on the page: its newest ``WATCH_TAIL_LINES`` lines;
3. the lines that hold the words, each with the ``WATCH_CONTEXT_LINES`` after it (a chat list's row: its name, time
   and preview);
4. with no words, the page's main text (``WATCH_PAGE_ROLES``), or the whole page; words found nowhere are
   ``missing`` (owner, 2026-11-09: the whole page as a fallback made every other chat's news a model run).

``normalise`` drops what changes with nothing new (times like "14:50", "5 min ago", unread counters, "online",
"typing…", spacing and case), so only a real change gives a new ``fingerprint`` (an HMAC under a key derived from
the user's DEK, never the text itself)."""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from roost.constants import (
    WATCH_CHANGE_MAX_CHARS, WATCH_CONTEXT_LINES, WATCH_HITS_MAX, WATCH_NOISE_WORDS, WATCH_PAGE_ROLES,
    WATCH_ALL_CHATS, WATCH_CHATS_PLURAL, WATCH_DAY_WORDS, WATCH_LIST_ROLES, WATCH_PANE_ROLES, WATCH_QUOTED, WATCH_SNAPSHOT_MAX_CHARS, WATCH_STOP_WORDS, WATCH_TAIL_LINES,
)

Where = Literal["area", "pane", "rows", "page", "missing"]
_KEY_LABEL = b"roost:watch-fingerprint:v1"
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?\s?m\.?)?", re.IGNORECASE)
_RELATIVE = re.compile(
    r"(?:\bhace\s+)?\b\d+\s*(?:s|secs?|seconds?|segundos?|m|mins?|minutes?|minutos?|h|hrs?|hours?|horas?|d|days?|"
    r"d[ií]as?)\b(?:\s+ago)?", re.IGNORECASE)
_COUNTER = re.compile(
    r"^\(?\d{1,3}(?:[.,\s]?\d{3})*\)?(?:\s+unread messages?|\s+mensajes? no le[ií]dos?)?$")
_NOISE_PREFIXES = ("last seen", "últ. vez", "ult. vez")
_QUOTED = re.compile(WATCH_QUOTED)
_BRACKETS = re.compile(r"\([^()]*\)")
_BRACKET_GROUP = 4      # the group of WATCH_QUOTED that holds a bracket's text
_DATE = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")


@dataclass(frozen=True)
class AreaText:
    """One readable area of the page and its text."""
    role: str
    name: str
    text: str


@dataclass(frozen=True)
class WatchedPart:
    text: str
    where: Where


def fold(text: str) -> str:
    """Case and accents aside, spacing collapsed."""
    bare = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in bare if not unicodedata.combining(c)).split())


def _words(part: str) -> tuple[str, ...]:
    return tuple(w for w in re.findall(r"\w+", fold(part)) if w not in WATCH_STOP_WORDS)


def _name_like(text: str) -> bool:
    """A bracket holds a name when a word in it starts with a capital or a digit ("(Ana)", not "(not groups)")."""
    return any(word[0].isupper() or word[0].isdigit() for word in re.findall(r"\w+", text))


def _named_parts(part: str) -> tuple[tuple[str, ...], ...]:
    """Each name in quotes or brackets and each phone number (a bracket that is no name, like "(not groups)", is a
    remark)."""
    found = []
    for match in _QUOTED.finditer(part):
        text = next(group for group in match.groups() if group)
        if match.group(_BRACKET_GROUP) is None or _name_like(text):
            found.append(_words(text))
    return tuple(words for words in found if words)


def _names(part: str) -> tuple[tuple[str, ...], ...]:
    """The word sets to look for: the named parts, or else the meaningful words of the part outside its brackets."""
    return _named_parts(part) or (_words(_BRACKETS.sub(" ", part)),)


def _every_chat(part: str) -> bool:
    """The part names every chat: a phrase for it, or chats in the plural with no name ("personal chats")."""
    folded = fold(part)
    if any(phrase in folded for phrase in WATCH_ALL_CHATS):
        return True
    return not _named_parts(part) and bool(WATCH_CHATS_PLURAL.intersection(re.findall(r"\w+", folded)))


def _chat_list(areas: Sequence[AreaText], page_text: str) -> WatchedPart:
    """Every chat: the area named for chats, else the largest list on the page, else the main text."""
    lists = [a for a in areas if a.text.strip() and ("chat" in fold(a.name) or a.role in WATCH_LIST_ROLES)]
    named = [a for a in lists if "chat" in fold(a.name)]
    best = max(named or lists, key=lambda a: len(a.text), default=None)
    return WatchedPart(_cut(best.text), "area") if best is not None else WatchedPart(_cut(_page(areas, page_text)), "page")


def _holds(line: str, words: tuple[str, ...]) -> bool:
    folded = fold(line)
    return bool(words) and all(word in folded for word in words)


def _cut(text: str, *, keep_end: bool = False) -> str:
    if len(text) <= WATCH_SNAPSHOT_MAX_CHARS:
        return text
    return text[-WATCH_SNAPSHOT_MAX_CHARS:] if keep_end else text[:WATCH_SNAPSHOT_MAX_CHARS]


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-WATCH_TAIL_LINES:])


def _open_pane(words: tuple[str, ...], areas: Sequence[AreaText], page_text: str) -> AreaText | None:
    """The largest message pane, when the words stand in a line outside every area (the open chat's header)."""
    panes = [a for a in areas if a.role in WATCH_PANE_ROLES and a.text.strip()]
    if not panes:
        return None
    inside = {line for area in areas for line in area.text.splitlines()}
    loose = (line for line in page_text.splitlines() if line not in inside)
    if not any(_holds(line, words) for line in loose):
        return None
    return max(panes, key=lambda a: len(a.text))


def _stamp(line: str) -> bool:
    """A chat list row's time or day ("14:50", "Yesterday", "10/11/2026")."""
    text = fold(line)
    return bool(_TIME.fullmatch(text) or _DATE.fullmatch(text)) or text in WATCH_DAY_WORDS


def _row_end(lines: list[str], hit: int) -> int:
    """Where the row that starts at ``hit`` ends: after its context lines, or before the next row's name (a line
    followed by a stamp), so the next chat's news is never in the part."""
    end = min(len(lines), hit + WATCH_CONTEXT_LINES + 1)
    return next((j for j in range(hit + 2, end) if j + 1 < len(lines) and _stamp(lines[j + 1])), end)


def _rows(names: tuple[tuple[str, ...], ...], page_text: str) -> str:
    lines = page_text.splitlines()
    hits = [i for i, line in enumerate(lines) if any(_holds(line, words) for words in names)][:WATCH_HITS_MAX]
    kept: list[int] = []
    for hit in hits:
        kept.extend(i for i in range(hit, _row_end(lines, hit)) if i not in kept)
    return "\n".join(lines[i] for i in kept)


def _page(areas: Sequence[AreaText], page_text: str) -> str:
    mains = [a for a in areas if a.role in WATCH_PAGE_ROLES and a.text.strip()]
    return max(mains, key=lambda a: len(a.text)).text if mains else page_text


def _named(words: tuple[str, ...], areas: Sequence[AreaText], page_text: str) -> WatchedPart | None:
    named = next((a for a in areas if _holds(a.name, words) and a.text.strip()), None)
    if named is not None:
        body = _tail(named.text) if named.role in WATCH_PANE_ROLES else named.text
        return WatchedPart(_cut(body, keep_end=True), "area")
    pane = _open_pane(words, areas, page_text)
    return WatchedPart(_cut(_tail(pane.text), keep_end=True), "pane") if pane is not None else None


def pick_part(part: str, areas: Sequence[AreaText], page_text: str) -> WatchedPart:
    """The watched part of the page (see the module's order); with several quoted names, the first one found as an
    area or open chat, else the rows of every one."""
    if _every_chat(part):
        return _chat_list(areas, page_text)
    names = tuple(words for words in _names(part) if words)
    if not names:
        return WatchedPart(_cut(_page(areas, page_text)), "page")
    found = next((hit for words in names if (hit := _named(words, areas, page_text)) is not None), None)
    if found is not None:
        return found
    rows = _rows(names, page_text)
    return WatchedPart(_cut(rows), "rows") if rows else WatchedPart("", "missing")


def _line(line: str) -> str:
    text = " ".join(_RELATIVE.sub(" ", _TIME.sub(" ", line.casefold())).split())
    if _COUNTER.match(text) or text in WATCH_NOISE_WORDS or text.startswith(_NOISE_PREFIXES):
        return ""
    return text


def normalise(text: str) -> str:
    """The part as compared: no times, relative times, counters, chat noise, extra spacing or case."""
    return "\n".join(line for line in (_line(raw) for raw in text.splitlines()) if line)


def compared(text: str) -> str:
    """What the fingerprint is made of: the normalised lines in sorted order, so rows that only move (a chat list
    re-sorting) are no change, while a repeated line still counts."""
    return "\n".join(sorted(normalise(text).splitlines()))


def fingerprint(dek: bytes, routine_id: str, normalised: str) -> str:
    """An HMAC of the routine id and the normalised part, under a key derived from the DEK."""
    key = hmac.new(dek, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(key, f"{routine_id}\n{normalised}".encode("utf-8"), hashlib.sha256).hexdigest()


def changed_lines(old: str, new: str) -> str:
    """The lines of ``new`` that ``old`` did not hold (as compared), newest kept within the cap; the whole new
    part when no single line is new (lines moved)."""
    seen = set(normalise(old).splitlines())
    fresh = [line.strip() for line in new.splitlines() if (key := _line(line)) and key not in seen]
    text = "\n".join(fresh) if fresh else new.strip()
    return text[-WATCH_CHANGE_MAX_CHARS:] if len(text) > WATCH_CHANGE_MAX_CHARS else text
