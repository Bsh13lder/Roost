"""Structured bot instructions (docs/plans/2026-10-22-roost-replies.md, part 2).

``structure_instructions`` turns free text into five Markdown sections, always in the order of
``INSTRUCTION_SECTIONS``: Who you are and context · What you do · Rules · Tone · Team. A heading it knows (any
level) or a ``Label:`` line starts or fills its section (a Never, Always or Don'ts heading or label is kept word
for word under Rules, so a rule never loses its word); another heading stays as bold text. Text before any
heading goes under What you do, except lines that start like a rule (Never, Always, Don't …), which go under
Rules. An empty section gets one short default line. Code fences are left alone. Structuring structured text
changes nothing, and the result never passes ``MAX_BOT_INSTRUCTIONS_LENGTH``: the defaults go first, and when even
that does not fit, the text is kept as it was."""

from __future__ import annotations

import re
from types import MappingProxyType

from roost.constants import INSTRUCTION_SECTIONS, MAX_BOT_INSTRUCTIONS_LENGTH

KEYS = ("who", "what", "rules", "tone", "team")
TITLES = MappingProxyType(dict(zip(KEYS, INSTRUCTION_SECTIONS)))
_ALIASES = MappingProxyType({
    "who": ("who you are and context", "who you are", "context", "identity", "about", "background", "role",
            "persona"),
    "what": ("what you do", "what", "job", "your job", "tasks", "duties", "what to do", "work", "focus"),
    "rules": ("rules", "constraints", "limits", "boundaries", "never", "always", "don'ts", "dos and don'ts"),
    "tone": ("tone", "voice", "style", "tone of voice", "how you talk", "how to talk"),
    "team": ("team", "teammates", "teamwork", "working with others", "handoffs"),
})
_BY_ALIAS = MappingProxyType({alias: key for key, aliases in _ALIASES.items() for alias in aliases})
# Titles that carry meaning of their own: "Never: share the list" must not become "share the list" under Rules,
# so these headings and labels are kept word for word inside Rules.
_RULE_WORD_TITLES = frozenset({"never", "always", "don'ts", "dos and don'ts"})
DEFAULTS = MappingProxyType({
    "who": "You are one of the user's bots in Roost.",
    "what": "Help the user with what they ask.",
    "rules": "Follow the user's own words first. Ask before anything that spends, sends or deletes.",
    "tone": "Plain, short and friendly.",
    "team": "When a teammate's job fits better, hand the work over with ask_bot.",
})
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_LABEL = re.compile(r"^\s*(?:\*\*)?([A-Za-z][A-Za-z '’&/-]{0,40}?)(?:\*\*)?\s*:\s*(.*)$")
_RULE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*(never|always|don't|don’t|do not|only|must)\b", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(```|~~~)")


def _norm(title: str) -> str:
    return " ".join(title.strip().strip("*").lower().replace("’", "'").split())


def _section_of(title: str) -> str | None:
    return _BY_ALIAS.get(_norm(title))


def section_key(title: str) -> str | None:
    """The section a title names ("Tone", "rules", "Who you are"), or ``None``: its key in ``KEYS``."""
    return _section_of(title)


def render_sections(sections: dict[str, str]) -> str:
    """Every section that has text, in order, as ``## Title`` and its text."""
    return _render(sections)


def _is_rule_word(title: str) -> bool:
    return _norm(title) in _RULE_WORD_TITLES


def _empty() -> dict[str, list[str]]:
    return {key: [] for key in KEYS}


def _place(line: str, current: str | None, buckets: dict[str, list[str]]) -> str | None:
    """Put one line (outside a code fence) where it belongs; returns the section later lines go to."""
    heading = _HEADING.match(line)
    if heading:
        key = _section_of(heading.group(1))
        if key is not None and _is_rule_word(heading.group(1)):
            buckets[key].append(f"**{heading.group(1).strip()}**")
        if key is not None:
            return key
        buckets[current or "what"].append(f"**{heading.group(1).strip()}**")
        return current
    label = _LABEL.match(line)
    key = _section_of(label.group(1)) if label else None
    if key is not None and _is_rule_word(label.group(1)):
        buckets[key].append(line.strip())
        return current if label.group(2).strip() else key
    if key is not None:
        rest = label.group(2).strip()
        if not rest:
            return key
        buckets[key].append(rest)
        return current
    target = current or ("rules" if _RULE.match(line) else "what")
    buckets[target].append(line.rstrip())
    return current


def _tidy(lines: list[str]) -> str:
    """One section's text: no blank lines at either end, at most one blank line in a row."""
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip("\n").strip()


def parse_sections(text: str) -> dict[str, str]:
    """The text of each section, by key (``who``, ``what``, ``rules``, ``tone``, ``team``); "" when empty."""
    buckets, current, fenced = _empty(), None, False
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
        if fenced or _FENCE.match(line):
            buckets[current or "what"].append(line.rstrip())
            continue
        current = _place(line, current, buckets)
    return {key: _tidy(lines) for key, lines in buckets.items()}


def _filled(sections: dict[str, str], name: str | None, job: str | None) -> dict[str, str]:
    who = f"You are {name}. Your job: {job}." if name and job else (f"You are {name}." if name else DEFAULTS["who"])
    defaults = {**DEFAULTS, "who": who, "what": job or DEFAULTS["what"]}
    return {key: sections[key] or defaults[key] for key in KEYS}


def _render(sections: dict[str, str]) -> str:
    """Every section that has text, as a level-2 heading and its text."""
    return "\n\n".join(f"## {TITLES[key]}\n\n{sections[key]}" for key in KEYS if sections[key])


def structure_instructions(text: str, *, name: str | None = None, job: str | None = None,
                           limit: int = MAX_BOT_INSTRUCTIONS_LENGTH) -> str:
    """``text`` as the five sections (see the module docstring), never longer than ``limit``."""
    sections = parse_sections(text)
    full = _render(_filled(sections, name, job))
    if len(full) <= limit:
        return full
    bare = _render(sections)
    if bare and len(bare) <= limit:
        return bare
    return text if len(text) <= limit else text[:limit]
