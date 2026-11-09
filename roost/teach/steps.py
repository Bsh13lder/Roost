"""Steps as plain lines: for the worker model's input and for the plain draft when the worker can't help.

Pure functions. A line says where (only when the page changed since the step before) and what was done; a label
is quoted as the page gave it. ``fitted_body`` is the plain draft's body: it leaves out a line that shows an email
address or a secret and stops before the skill body limit, with a note for each."""

from __future__ import annotations

import re
from collections.abc import Sequence

from roost.bots.redact import find_secret_kinds
from roost.teach import texts
from roost.teach.models import TeachStep


def page_of(step: TeachStep) -> str:
    """``host/path (“title”)``, or "" for a step with no web page."""
    if not step.host:
        return ""
    template = texts.PAGE_TITLED if step.title else texts.PAGE_PLAIN
    return template.format(host=step.host, path=step.path, title=step.title)


def action_of(step: TeachStep) -> str:
    """What was done, in words. Never a typed character: there are none to show."""
    if step.kind == "click":
        return texts.CLICK.format(role=step.role or "control", label=step.label) if step.label \
            else texts.CLICK_UNNAMED
    if step.kind == "type":
        if not step.host and not step.label:
            return texts.TYPE_ADDRESS
        return texts.TYPE.format(label=step.label) if step.label else texts.TYPE_UNNAMED
    if step.kind == "password":
        return texts.PASSWORD
    if step.kind == "paste":
        return texts.PASTE.format(label=step.label) if step.label else texts.PASTE_UNNAMED
    if step.kind == "key":
        return texts.KEY.format(key=step.key or "a key")
    return texts.BROWSER


def step_lines(steps: Sequence[TeachStep]) -> tuple[str, ...]:
    """One line per step; the page is named when it differs from the step before."""
    lines: list[str] = []
    last_page = None
    for step in steps:
        page = page_of(step)
        prefix = texts.ON_PAGE.format(where=page) if page and page != last_page else ""
        if page:
            last_page = page
        action = action_of(step)
        lines.append(prefix + (action[0].upper() + action[1:] if not prefix else action))
    return tuple(lines)


def numbered(lines: Sequence[str]) -> str:
    return "\n".join(f"{n}. {line}" for n, line in enumerate(lines, start=1))


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _shareable(line: str) -> bool:
    """A line that names no email address and no secret (a label such as an account chooser's can)."""
    return not _EMAIL.search(line) and not find_secret_kinds(line)


def fitted_body(lines: Sequence[str], limit: int) -> str:
    """The numbered lines that are shareable, as many as fit in ``limit`` characters with their notes."""
    kept = [line for line in lines if _shareable(line)]
    notes = [texts.LEFT_OUT_NOTE] if len(kept) < len(lines) else []
    reserve = len("\n\n") + len(texts.SHORTENED_NOTE) + sum(len(note) + 1 for note in notes)
    numbered_lines: list[str] = []
    used = 0
    for n, line in enumerate(kept, start=1):
        entry = f"{n}. {line}"
        if used + len(entry) + 1 > limit - reserve:
            notes.append(texts.SHORTENED_NOTE)
            break
        numbered_lines.append(entry)
        used += len(entry) + 1
    return "\n\n".join(part for part in ("\n".join(numbered_lines), "\n".join(notes)) if part)


def same_step(a: TeachStep, b: TeachStep) -> bool:
    """A repeat (a double click, two presses of Enter on one page) is kept once."""
    return a == b
