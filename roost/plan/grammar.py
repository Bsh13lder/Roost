"""The Plan grammar (design 4.1): pure, lenient read, canonical write.

A task line is ``- [s] desc fields``. Fields may come in any order when read;
they are written as ``desc ⏰ HH:MM #tags 📅 date ⏳ date ✅ date ❌ date 🆔 id``.
Every other line (and every task line that cannot be read) is kept byte for byte.
"""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass, replace
from datetime import date, timedelta

from roost.constants import (
    PLAN_ARCHIVE_DAYS,
    PLAN_ID_LENGTH,
    PLAN_MAX_BYTES,
    PLAN_MAX_ITEMS,
)

TOO_LONG = "The Plan is too long. Archive or remove some items."
ARCHIVE_HEADING = "## Archive"
STATUSES = ("planned", "on_it", "done", "dropped")
_MARK_TO_STATUS = {" ": "planned", "/": "on_it", "x": "done", "X": "done", "-": "dropped"}
_STATUS_TO_MARK = {"planned": " ", "on_it": "/", "done": "x", "dropped": "-"}
_ID_ALPHABET = string.ascii_lowercase + string.digits

_TASK = re.compile(r"^(?P<indent>\t| {4}| {2})?- \[(?P<mark>[ /xX-])\] (?P<body>.*\S.*)$")
_TAG = re.compile(r"#[A-Za-z0-9_/-]+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
_ID = re.compile(rf"[a-z0-9]{{{PLAN_ID_LENGTH}}}")
_FIELDS = {"⏰": "time", "📅": "date", "⏳": "scheduled", "✅": "done_on", "❌": "dropped_on", "🆔": "id"}


class PlanRefused(ValueError):
    """A Plan change refused with a plain sentence for the user."""


@dataclass(frozen=True)
class PlanItem:
    id: str | None
    status: str
    text: str
    tags: tuple[str, ...] = ()
    date: str | None = None
    time: str | None = None
    done_on: str | None = None
    dropped_on: str | None = None
    scheduled: str | None = None
    indent: int = 0
    line_no: int = 0


@dataclass(frozen=True)
class PlanDoc:
    lines: tuple[str | PlanItem, ...]
    items: tuple[PlanItem, ...]
    unreadable: int = 0


def _build(lines: list[str | PlanItem], unreadable: int) -> PlanDoc:
    numbered = tuple(replace(x, line_no=n) if isinstance(x, PlanItem) else x for n, x in enumerate(lines))
    return PlanDoc(numbered, tuple(x for x in numbered if isinstance(x, PlanItem)), unreadable)


def _valid(kind: str, value: str) -> bool:
    if kind == "time":
        return bool(_TIME.fullmatch(value))
    if kind == "id":
        return bool(_ID.fullmatch(value))
    if not _DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_body(body: str) -> tuple[str, tuple[str, ...], dict[str, str]] | None:
    words: list[str] = []
    tags: list[str] = []
    fields: dict[str, str] = {}
    tokens = body.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        kind = _FIELDS.get(tok)
        if kind is not None:
            value = tokens[i + 1] if i + 1 < len(tokens) else ""
            if kind in fields or not _valid(kind, value):
                return None
            fields[kind] = value
            i += 2
            continue
        if _TAG.fullmatch(tok):
            if tok not in tags:
                tags.append(tok)
        else:
            words.append(tok)
        i += 1
    if not words:
        return None
    return " ".join(words), tuple(tags), fields


def _parse_line(line: str) -> PlanItem | None | str:
    """A PlanItem, None for a plain other line, or "bad" for an unreadable task."""
    m = _TASK.match(line)
    if not m:
        return None
    parsed = _parse_body(m["body"])
    if parsed is None:
        return "bad"
    text, tags, f = parsed
    return PlanItem(
        id=f.get("id"), status=_MARK_TO_STATUS[m["mark"]], text=text, tags=tags,
        date=f.get("date"), time=f.get("time"), done_on=f.get("done_on"),
        dropped_on=f.get("dropped_on"), scheduled=f.get("scheduled"),
        indent=1 if m["indent"] else 0,
    )


def parse(text: str) -> PlanDoc:
    lines: list[str | PlanItem] = []
    bad = 0
    for raw in text.replace("\r\n", "\n").split("\n"):
        got = _parse_line(raw)
        if got == "bad":
            bad += 1
            lines.append(raw)
        elif got is None:
            lines.append(raw)
        else:
            lines.append(got)
    return _build(lines, bad)


def render_item(item: PlanItem) -> str:
    parts = [item.text]
    if item.time:
        parts.append(f"⏰ {item.time}")
    parts.extend(item.tags)
    for mark, value in (("📅", item.date), ("⏳", item.scheduled), ("✅", item.done_on), ("❌", item.dropped_on), ("🆔", item.id)):
        if value:
            parts.append(f"{mark} {value}")
    pad = "  " if item.indent else ""
    return f"{pad}- [{_STATUS_TO_MARK[item.status]}] {' '.join(parts)}"


def render(doc: PlanDoc) -> str:
    return "\n".join(render_item(x) if isinstance(x, PlanItem) else x for x in doc.lines)


def apply_status(item: PlanItem, status: str, today: date) -> PlanItem:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    stamp = today.isoformat()
    done_on = (item.done_on or stamp) if status == "done" else None
    dropped_on = (item.dropped_on or stamp) if status == "dropped" else None
    return replace(item, status=status, done_on=done_on, dropped_on=dropped_on)


def check_limits(text: str, doc: PlanDoc | None = None) -> None:
    if len(text.encode("utf-8")) > PLAN_MAX_BYTES:
        raise PlanRefused(TOO_LONG)
    if doc is not None and len(doc.items) > PLAN_MAX_ITEMS:
        raise PlanRefused(TOO_LONG)


def _map_items(doc: PlanDoc, fn) -> PlanDoc:
    return _build([fn(x) if isinstance(x, PlanItem) else x for x in doc.lines], doc.unreadable)


def normalise(doc: PlanDoc, today: date) -> PlanDoc:
    return _map_items(doc, lambda it: apply_status(it, it.status, today))


def canonical(text: str, today: date) -> str:
    check_limits(text)
    doc = parse(text)
    check_limits(text, doc)
    return render(normalise(doc, today))


def new_id(taken: set[str] | frozenset[str]) -> str:
    while True:
        candidate = "".join(secrets.choice(_ID_ALPHABET) for _ in range(PLAN_ID_LENGTH))
        if candidate not in taken:
            return candidate


def assign_ids(doc: PlanDoc, taken: frozenset[str] | set[str] = frozenset()) -> PlanDoc:
    used = set(taken)
    seen: set[str] = set()
    out: list[str | PlanItem] = []
    for x in doc.lines:
        if isinstance(x, PlanItem):
            if not x.id or x.id in seen:
                x = replace(x, id=new_id(used | seen | {i.id for i in doc.items if i.id}))
            seen.add(x.id)
        out.append(x)
    return _build(out, doc.unreadable)


def archive_old(doc: PlanDoc, today: date) -> PlanDoc:
    cutoff = (today - timedelta(days=PLAN_ARCHIVE_DAYS)).isoformat()
    lines = list(doc.lines)
    start = next((n for n, x in enumerate(lines) if x == ARCHIVE_HEADING), len(lines))
    moved: list[str | PlanItem] = []
    kept: list[str | PlanItem] = []
    carrying = False
    for n, x in enumerate(lines):
        if n < start and isinstance(x, PlanItem):
            if x.indent == 0:
                stamp = x.done_on if x.status == "done" else x.dropped_on if x.status == "dropped" else None
                carrying = bool(stamp and stamp < cutoff)
            if carrying:
                moved.append(x)
                continue
        elif n < start:
            carrying = False
        kept.append(x)
    if not moved:
        return doc
    trailing = bool(kept) and kept[-1] == ""
    while kept and kept[-1] == "":
        kept.pop()
    if ARCHIVE_HEADING not in kept:
        kept.extend(["", ARCHIVE_HEADING])
    else:
        # drop blank lines inside the archive tail so the new items join it
        while kept and kept[-1] == "":
            kept.pop()
    kept.extend(moved)
    if trailing:
        kept.append("")
    return _build(kept, doc.unreadable)
