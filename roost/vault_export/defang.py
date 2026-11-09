"""Make text safe to write into the user's Obsidian vault, pure.

Obsidian loads a remote image (``![x](https://…)``, ``<img src=…>``) as soon as a note is shown, and runs
code blocks some plugins understand, so text that came from a web page could send data out with no click.
``defang`` turns such text inert before the export writes it: every web address becomes inline code, and
``\\ ` ~ [ ] < >`` are escaped, so nothing can start an image, an embed, a link, a wikilink, HTML or a
code fence. ``label`` and ``heading`` keep a title on one line and inside its wikilink or heading."""

from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s`]+", re.IGNORECASE)
_ESCAPED = re.compile(r"([\\`~\[\]!])")
_ANGLES = {"<": "&lt;", ">": "&gt;"}
_LABEL_SWAPS = str.maketrans({"[": "(", "]": ")", "|": "/", "<": "‹", ">": "›", "#": "♯"})
_SPACE = re.compile(r"\s+")


def _escape(text: str) -> str:
    escaped = _ESCAPED.sub(r"\\\1", text)
    return "".join(_ANGLES.get(char, char) for char in escaped)


def defang(text: str) -> str:
    """``text`` with no live image, embed, link, HTML or code fence; web addresses shown as inline code."""
    parts: list[str] = []
    last = 0
    for match in _URL.finditer(text):
        parts += [_escape(text[last:match.start()]), f"`{match.group(0)}`"]
        last = match.end()
    parts.append(_escape(text[last:]))
    return "".join(parts)


def one_line(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def label(text: str) -> str:
    """A wikilink's shown text: one line with no ``[ ] |`` or HTML that could end the link early."""
    return one_line(text).translate(_LABEL_SWAPS)


def heading(text: str) -> str:
    """A ``# `` heading's text: one line, defanged."""
    return defang(one_line(text))


def body(text: str, tainted: bool) -> str:
    """A record's own text: kept as written unless it came from the web."""
    return defang(text) if tainted else text


def markdown_body(content: str, tainted: bool) -> str:
    """Roost-made Markdown with front matter: only the part after the front matter is defanged."""
    if not tainted:
        return content
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            split = end + len("\n---\n")
            return content[:split] + defang(content[split:])
    return defang(content)
