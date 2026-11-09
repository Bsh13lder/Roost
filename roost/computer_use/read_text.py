"""How ``read_text`` and ``read_pdf`` hand text to the model (fast pages, slices 3 and 5).

The text is the page's (or a PDF's), so it is untrusted: one ``<untrusted_page>`` wrapper, escaped like a look's,
and reading it taints the run. A call reads at most ``CU_READ_TEXT_CHARS`` characters, cut at a line end, and says
where the next call starts; ``find`` shows only the lines that hold the words (case and accents aside) with their
neighbours, so a long chat is searched in one step."""

from __future__ import annotations

import html
import unicodedata

from roost.desk.card_redact import hide_card_numbers
from roost.constants import CU_READ_FIND_CONTEXT, CU_READ_FIND_HITS_MAX, CU_READ_TEXT_CHARS

GAP = "…"


def text_window(text: str, start: int, budget: int = CU_READ_TEXT_CHARS) -> tuple[str, int]:
    """The text from ``start``, at most ``budget`` characters, ending on a line end when one is in reach, and where
    the next window starts (``len(text)`` at the end)."""
    if start >= len(text):
        return "", len(text)
    end = min(len(text), start + budget)
    if end < len(text):
        cut = text.rfind("\n", start, end)
        if cut > start:
            return text[start:cut], cut + 1
    return text[start:end], end


def _fold(text: str) -> str:
    bare = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in bare if not unicodedata.combining(c)).split())


def find_lines(text: str, words: str, *, context: int = CU_READ_FIND_CONTEXT,
               limit: int = CU_READ_FIND_HITS_MAX) -> list[str]:
    """The lines holding ``words`` (at most ``limit`` hits) with ``context`` lines around each; ``GAP`` between
    windows that don't touch."""
    lines = text.splitlines()
    wanted = _fold(words)
    hits = [i for i, line in enumerate(lines) if wanted and wanted in _fold(line)][:limit]
    shown: list[int] = []
    for hit in hits:
        for i in range(max(0, hit - context), min(len(lines), hit + context + 1)):
            if not shown or i > shown[-1]:
                shown.append(i)
    out: list[str] = []
    for position, i in enumerate(shown):
        if position and i != shown[position - 1] + 1:
            out.append(GAP)
        out.append(lines[i])
    return out


def wrapped(url: str, head: str, body: str) -> str:
    """One escaped ``<untrusted_page>`` wrapper: the facts line, then the text."""
    inner = html.escape(hide_card_numbers(f"{head}\n{body}"), quote=True)
    return f'<untrusted_page url="{html.escape(url, quote=True)}">{inner}</untrusted_page>'


def read_reply(url: str, what: str, text: str, *, start: int, find: str | None, again: str) -> str:
    """What one read hands the model. ``again`` is the call that reads on, without its ``start``."""
    if find:
        lines = find_lines(text, find)
        head = f"{what}: lines with \"{find}\" ({len(text)} characters searched)."
        return wrapped(url, head, "\n".join(lines) if lines else "(no line holds those words)")
    chunk, end = text_window(text, start)
    head = f"{what}: characters {start}–{end} of {len(text)}."
    reply = wrapped(url, head, chunk or "(nothing more to read)")
    return f"{reply}\nMore: {again} start={end}" if end < len(text) else reply
