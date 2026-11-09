# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/docs/snapshot.py lines 1-245, 306-321, 405-716 @ 21e1002, adapted for Roost

"""Pure helpers over Univer's ``IDocumentData`` snapshot.

A doc is stored as one JSON blob in Univer's native document format. These
functions read and **immutably** edit that structure; Roost's documents tools
and routes use these for a single text model, instead of reaching into the
Univer snapshot shape themselves. No I/O, no Univer runtime dependency — just
dict shaping.

This file holds the factory (``blank_document``), the paragraph readers
(``get_paragraphs``) and the block builders/readers (``append_blocks``,
``get_blocks``) of LazyClaw's snapshot module — not its run-level helpers
(the skill-facing read/save functions) or its hyperlink-only helpers, which
Roost does not carry over.

Univer document shape (only the parts we touch)::

    {
      "id": "doc-…",
      "documentStyle": { "pageSize": {...}, ... },
      "body": {
        "dataStream": "Hello\\rWorld\\r\\n",
        "paragraphs": [{"startIndex": 5}, {"startIndex": 11}],
        "textRuns": [...],
        "sectionBreaks": [{"startIndex": 12}]
      }
    }

CONVENTION (Univer's on-the-wire form):
- In ``dataStream`` each paragraph ends with a ``"\\r"`` (carriage return);
  the whole body ends with a single ``"\\n"`` (the section-break sentinel).
- Each entry in ``body.paragraphs`` carries ``startIndex`` = the index of that
  paragraph's terminating ``"\\r"`` inside ``dataStream``.
- The text of paragraph *i* is the run of characters between the previous
  paragraph's ``"\\r"`` (exclusive) and this paragraph's ``"\\r"`` (exclusive).

Every mutator returns a NEW snapshot (deepcopy) — callers never observe
in-place changes (project immutability rule). Readers are robust to malformed
input (missing keys, wrong types) and degrade to an empty document.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from uuid import uuid4

# Univer's paragraph terminator and body terminator.
PARAGRAPH_BREAK = "\r"
SECTION_BREAK = "\n"

# Univer's custom-range sentinels. A hyperlink (or any custom range) wraps its
# span of ``dataStream`` between these two control characters; the range's
# ``startIndex`` points at CUSTOM_RANGE_START and ``endIndex`` at
# CUSTOM_RANGE_END (both inclusive). See @univerjs/core DataStreamTreeTokenType.
CUSTOM_RANGE_START = "\u001f"
CUSTOM_RANGE_END = "\u001e"

# CustomRangeType.HYPERLINK in @univerjs/core (i-document-data.d.ts).
_HYPERLINK = 0


def _strip_tokens(s: str) -> str:
    """Remove the custom-range sentinel chars from a visible-text slice."""
    return s.replace(CUSTOM_RANGE_START, "").replace(CUSTOM_RANGE_END, "")


# ───────────────────────── document factory ─────────────────────────

def blank_document(name: str, *, doc_id: str | None = None) -> dict[str, Any]:
    """Build a minimal valid empty Univer ``IDocumentData``.

    An empty doc is a single empty paragraph: ``dataStream`` is ``"\\r\\n"``
    (one paragraph break + the section terminator) with one paragraph whose
    ``startIndex`` points at the ``"\\r"`` (index 0). ``name`` is carried for
    convenience even though Univer keys docs by ``id``; the store uses the
    plaintext column for the sidebar.

    ``doc_id`` defaults to a fresh uuid; tests may pass a fixed one.
    """
    did = doc_id or f"doc-{uuid4().hex[:12]}"
    return {
        "id": did,
        "name": (name or "Untitled doc").strip() or "Untitled doc",
        "documentStyle": {},
        "body": {
            "dataStream": PARAGRAPH_BREAK + SECTION_BREAK,
            "paragraphs": [{"startIndex": 0}],
            "textRuns": [],
            "sectionBreaks": [{"startIndex": 1}],
        },
    }


# ───────────────────────── internal builders ────────────────────────

def _build_body(paragraphs: list[str]) -> dict[str, Any]:
    """Construct a valid ``body`` dict from a list of paragraph strings.

    Each paragraph contributes ``"<text>\\r"`` to ``dataStream``; the body is
    terminated with a single ``"\\n"``. ``startIndex`` for each paragraph is
    the index of its ``"\\r"``. An empty list collapses to one empty paragraph
    (matching :func:`blank_document`).
    """
    if not paragraphs:
        paragraphs = [""]

    stream_parts: list[str] = []
    para_meta: list[dict[str, Any]] = []
    cursor = 0
    for text in paragraphs:
        # Defensive: never let a stray "\r"/"\n" inside the text corrupt the
        # paragraph index bookkeeping.
        clean = str(text).replace(PARAGRAPH_BREAK, " ").replace(SECTION_BREAK, " ")
        stream_parts.append(clean)
        stream_parts.append(PARAGRAPH_BREAK)
        cursor += len(clean)
        para_meta.append({"startIndex": cursor})
        cursor += 1  # account for the "\r" we just appended

    data_stream = "".join(stream_parts) + SECTION_BREAK
    return {
        "dataStream": data_stream,
        "paragraphs": para_meta,
        "textRuns": [],
        "sectionBreaks": [{"startIndex": len(data_stream) - 1}],
    }


# ───────────────────────── text read ────────────────────────────────

def get_paragraphs(snap: dict[str, Any]) -> list[str]:
    """Return the document's paragraphs as a list of plain strings.

    Robust to malformed input: a missing/empty body yields ``[]``; a body with
    a ``dataStream`` but no usable ``paragraphs`` metadata falls back to
    splitting the stream on ``"\\r"`` (dropping the trailing section break).
    """
    body = snap.get("body") if isinstance(snap, dict) else None
    if not isinstance(body, dict):
        return []
    stream = body.get("dataStream")
    if not isinstance(stream, str) or stream == "":
        return []

    paras = body.get("paragraphs")
    if isinstance(paras, list) and paras:
        out: list[str] = []
        prev = 0
        for p in paras:
            if not isinstance(p, dict):
                continue
            end = p.get("startIndex")
            if not isinstance(end, int) or end < prev or end > len(stream):
                # Malformed index — bail to the stream-split fallback.
                return _split_stream(stream)
            out.append(_strip_tokens(stream[prev:end]))
            prev = end + 1  # skip the "\r"
        return out

    return _split_stream(stream)


def _split_stream(stream: str) -> list[str]:
    """Fallback: derive paragraphs purely from ``dataStream`` text.

    Mirrors :func:`_build_body`'s convention: every paragraph is terminated by
    a ``"\\r"`` and the body ends with a single ``"\\n"``. We drop the trailing
    section break, then drop the final paragraph terminator that sits right
    before it (so a well-formed ``"a\\rb\\r\\n"`` yields ``["a", "b"]``, not a
    spurious trailing empty paragraph), and split the remainder on ``"\\r"``.
    """
    body = stream[:-1] if stream.endswith(SECTION_BREAK) else stream
    if body.endswith(PARAGRAPH_BREAK):
        body = body[:-1]
    if body == "":
        return [""]
    return [_strip_tokens(p) for p in body.split(PARAGRAPH_BREAK)]


def get_text(snap: dict[str, Any]) -> str:
    """Join the document's paragraphs into plain text with ``"\\n"``."""
    return "\n".join(get_paragraphs(snap))


def is_empty(snap: dict[str, Any]) -> bool:
    """True when the document has no non-whitespace content."""
    return get_text(snap).strip() == ""


# ───────────────────────── text write (immutable) ───────────────────

def set_text(snap: dict[str, Any], text: str) -> dict[str, Any]:
    """Return a NEW snapshot whose body is rebuilt from ``text``.

    The text is split on ``"\\n"`` into paragraphs; ``dataStream`` and
    ``paragraphs`` are regenerated. Top-level keys (``id``, ``name``,
    ``documentStyle``) are preserved. ``textRuns`` are reset (we don't carry
    rich formatting through a plain-text rewrite).
    """
    out = copy.deepcopy(snap) if isinstance(snap, dict) else {}
    if "id" not in out:
        out["id"] = f"doc-{uuid4().hex[:12]}"
    out.setdefault("documentStyle", {})
    paragraphs = (text or "").split("\n") if text is not None else [""]
    out["body"] = _build_body(paragraphs)
    return out


def append_paragraph(snap: dict[str, Any], text: str) -> dict[str, Any]:
    """Return a NEW snapshot with ``text`` appended as one new paragraph.

    A blank document (single empty paragraph) is replaced by the new
    paragraph rather than gaining a leading empty line — matching what a user
    expects when they "add a line" to a fresh doc.
    """
    paras = get_paragraphs(snap)
    if paras == [""] or paras == []:
        paras = [str(text)]
    else:
        paras = [*paras, str(text)]
    out = copy.deepcopy(snap) if isinstance(snap, dict) else {}
    if "id" not in out:
        out["id"] = f"doc-{uuid4().hex[:12]}"
    out.setdefault("documentStyle", {})
    out["body"] = _build_body(paras)
    return out


# ───────────────────────── rich runs (hyperlinks) ───────────────────
#
# A "run" is the unit of inline content: ``{"text": str}`` for plain text or
# ``{"text": str, "url": str}`` for a hyperlink. A paragraph is a list of runs.
# These helpers carry hyperlinks through the same immutable model the plain-text
# helpers use, by emitting Univer ``customRanges`` bracketed in ``dataStream``
# with the CUSTOM_RANGE_START / CUSTOM_RANGE_END sentinels.

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _clean_run_text(text: str) -> str:
    """Sanitise run text: drop paragraph/section breaks and stray sentinels."""
    return (
        str(text)
        .replace(PARAGRAPH_BREAK, " ")
        .replace(SECTION_BREAK, " ")
        .replace(CUSTOM_RANGE_START, "")
        .replace(CUSTOM_RANGE_END, "")
    )


def _paragraph_spans(stream: str) -> list[tuple[int, int]]:
    """Absolute ``(start, end)`` char spans per paragraph (end = the ``\\r``).

    Scans ``dataStream`` for paragraph terminators, which is robust regardless
    of whether ``paragraphs`` metadata is present/consistent and yields the
    absolute indices the hyperlink ``customRanges`` are expressed in.
    """
    spans: list[tuple[int, int]] = []
    prev = 0
    for idx, ch in enumerate(stream):
        if ch == PARAGRAPH_BREAK:
            spans.append((prev, idx))
            prev = idx + 1
    return spans


_HEADING_NAMED_STYLE = {1: 4, 2: 5, 3: 6}
_NAMED_STYLE_HEADING = {4: 1, 5: 2, 6: 3}
_LIST_TYPE = {"bullet": "BULLET_LIST", "number": "ORDER_LIST"}
_ALIGNMENT = {"left": 1, "center": 2, "centre": 2, "right": 3, "justify": 4}
_ALIGNMENT_NAME = {1: "left", 2: "center", 3: "right", 4: "justify"}


def _run_style(run: dict[str, Any]) -> dict[str, Any]:
    """Map a run's bold/italic/underline flags to a Univer ``ts`` style dict."""
    ts: dict[str, Any] = {}
    if run.get("bold"):
        ts["bl"] = 1
    if run.get("italic"):
        ts["it"] = 1
    if run.get("underline"):
        ts["ul"] = {"s": 1}
    return ts


def build_body_with_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a Univer ``body`` from structured blocks (headings/lists/styles).

    Each block is ``{"type": heading|paragraph|bullet|number, "level": int,
    "runs": [run, ...]}``. Emits ``paragraphs[*].paragraphStyle`` for headings,
    ``paragraphs[*].bullet`` for list items (consecutive same-type items share a
    ``listId`` so ordered lists number continuously), ``textRuns`` for
    bold/italic/underline spans, and hyperlink ``customRanges`` (same sentinel
    convention as :func:`build_body_with_runs`). Empty input → one empty
    paragraph.
    """
    if not blocks:
        blocks = [{"type": "paragraph", "level": 0, "runs": [{"text": ""}]}]

    stream_parts: list[str] = []
    para_meta: list[dict[str, Any]] = []
    custom_ranges: list[dict[str, Any]] = []
    text_runs: list[dict[str, Any]] = []
    cursor = 0
    link_counter = 0
    list_counter = 0
    prev_list_kind: str | None = None
    cur_list_id: str | None = None

    for block in blocks:
        if not isinstance(block, dict):
            block = {"type": "paragraph", "runs": []}
        btype = block.get("type", "paragraph")
        runs = block.get("runs") or []
        for run in runs:
            if not isinstance(run, dict):
                continue
            text = _clean_run_text(run.get("text", ""))
            url = run.get("url")
            style = _run_style(run)
            if url:
                start_token = cursor
                stream_parts.append(CUSTOM_RANGE_START)
                cursor += 1
                text_start = cursor
                stream_parts.append(text)
                cursor += len(text)
                end_token = cursor
                stream_parts.append(CUSTOM_RANGE_END)
                cursor += 1
                custom_ranges.append(
                    {
                        "startIndex": start_token,
                        "endIndex": end_token,
                        "rangeId": f"link-{link_counter}",
                        "rangeType": _HYPERLINK,
                        "properties": {"url": str(url)},
                    }
                )
                link_counter += 1
                if style and text:
                    text_runs.append(
                        {"st": text_start, "ed": text_start + len(text), "ts": style}
                    )
            else:
                run_start = cursor
                stream_parts.append(text)
                cursor += len(text)
                if style and text:
                    text_runs.append(
                        {"st": run_start, "ed": run_start + len(text), "ts": style}
                    )

        stream_parts.append(PARAGRAPH_BREAK)
        meta: dict[str, Any] = {"startIndex": cursor}
        if btype == "heading":
            level = int(block.get("level") or 1)
            meta["paragraphStyle"] = {
                "namedStyleType": _HEADING_NAMED_STYLE.get(level, 4)
            }
            prev_list_kind = None
        elif btype in ("bullet", "number"):
            if prev_list_kind != btype:
                cur_list_id = f"list-{list_counter}"
                list_counter += 1
            prev_list_kind = btype
            meta["bullet"] = {
                "listType": _LIST_TYPE[btype],
                "listId": cur_list_id,
                "nestingLevel": int(block.get("level") or 0),
            }
        else:
            prev_list_kind = None

        # Paragraph alignment rides in the SAME `paragraphStyle` object a
        # heading uses, so it must be merged in rather than assigned — writing
        # it as a fresh dict would drop the heading's namedStyleType and demote
        # every centred heading to body text.
        align = _ALIGNMENT.get(str(block.get("align") or "").lower())
        if align is not None:
            style = meta.setdefault("paragraphStyle", {})
            style["horizontalAlign"] = align

        para_meta.append(meta)
        cursor += 1

    data_stream = "".join(stream_parts) + SECTION_BREAK
    return {
        "dataStream": data_stream,
        "paragraphs": para_meta,
        "textRuns": text_runs,
        "customRanges": custom_ranges,
        "sectionBreaks": [{"startIndex": len(data_stream) - 1}],
    }


def _index_styles(body: dict[str, Any]) -> dict[int, dict[str, bool]]:
    """Map each styled char index → ``{bold?/italic?/underline?: True}``."""
    out: dict[int, dict[str, bool]] = {}
    for tr in body.get("textRuns") or []:
        if not isinstance(tr, dict):
            continue
        st, ed, ts = tr.get("st"), tr.get("ed"), tr.get("ts")
        if not (isinstance(st, int) and isinstance(ed, int) and isinstance(ts, dict)):
            continue
        flags: dict[str, bool] = {}
        if ts.get("bl"):
            flags["bold"] = True
        if ts.get("it"):
            flags["italic"] = True
        ul = ts.get("ul")
        if (isinstance(ul, dict) and ul.get("s")) or ul == 1:
            flags["underline"] = True
        if not flags:
            continue
        for i in range(st, ed):
            out.setdefault(i, {}).update(flags)
    return out


def _block_type_from_meta(meta: Any) -> tuple[str, int]:
    """Resolve a paragraph's block type + level from its Univer metadata."""
    if not isinstance(meta, dict):
        return "paragraph", 0
    bullet = meta.get("bullet")
    if isinstance(bullet, dict):
        lt = str(bullet.get("listType", ""))
        kind = "number" if lt.startswith("ORDER") else "bullet"
        return kind, int(bullet.get("nestingLevel") or 0)
    ps = meta.get("paragraphStyle")
    if isinstance(ps, dict):
        named = ps.get("namedStyleType")
        if named in _NAMED_STYLE_HEADING:
            return "heading", _NAMED_STYLE_HEADING[named]
    return "paragraph", 0


def _alignment_from_meta(meta: Any) -> str | None:
    """A paragraph's alignment name, or ``None`` when it uses the default."""
    if not isinstance(meta, dict):
        return None
    ps = meta.get("paragraphStyle")
    if not isinstance(ps, dict):
        return None
    align = ps.get("horizontalAlign")
    return _ALIGNMENT_NAME.get(align) if isinstance(align, int) else None


def replace_block(
    snap: dict[str, Any], index: int, block: dict[str, Any]
) -> dict[str, Any]:
    """Return a NEW snapshot with block ``index`` swapped for ``block``.

    The targeted mid-document edit. Without it the only ways to change a
    document were "append at the end" and "replace the whole body", so
    "make the third paragraph bold" meant rewriting everything — and any
    formatting the model didn't bother to re-emit was silently lost.

    Raises ``IndexError`` for an out-of-range index so a bad plan fails loudly
    instead of appending in the wrong place.
    """
    blocks = get_blocks(snap)
    if not blocks:
        raise IndexError("document has no blocks to edit")
    if index < 0 or index >= len(blocks):
        raise IndexError(
            f"block {index} is out of range (document has {len(blocks)})"
        )
    updated = list(blocks)
    updated[index] = block
    out = copy.deepcopy(snap)
    out["body"] = build_body_with_blocks(updated)
    return out


def get_blocks(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Inverse of :func:`build_body_with_blocks`: paragraphs → typed blocks.

    Reconstructs block type (heading/bullet/number/paragraph) from
    ``paragraphStyle``/``bullet`` metadata and runs (carrying
    bold/italic/underline/url) from ``textRuns`` + ``customRanges``. Robust to
    missing metadata (degrades to a plain paragraph).
    """
    body = snap.get("body") if isinstance(snap, dict) else None
    if not isinstance(body, dict):
        return []
    stream = body.get("dataStream")
    if not isinstance(stream, str) or stream == "":
        return []

    start_map: dict[int, tuple[int, str]] = {}
    for c in body.get("customRanges") or []:
        if not isinstance(c, dict):
            continue
        s, e = c.get("startIndex"), c.get("endIndex")
        props = c.get("properties")
        url = props.get("url") if isinstance(props, dict) else None
        if isinstance(s, int) and isinstance(e, int) and url:
            start_map[s] = (e, str(url))

    styles = _index_styles(body)
    paras_meta = body.get("paragraphs") or []
    blocks: list[dict[str, Any]] = []

    for p_idx, (p_start, p_end) in enumerate(_paragraph_spans(stream)):
        runs: list[dict[str, Any]] = []
        cur_text: list[str] = []
        cur_flags: tuple[str, ...] | None = None

        def flush() -> None:
            nonlocal cur_text, cur_flags
            if cur_text:
                run: dict[str, Any] = {"text": "".join(cur_text)}
                for f in cur_flags or ():
                    run[f] = True
                runs.append(run)
            cur_text = []
            cur_flags = None

        i = p_start
        while i < p_end:
            ch = stream[i]
            if ch == CUSTOM_RANGE_START and i in start_map:
                flush()
                end_idx, url = start_map[i]
                link_run: dict[str, Any] = {
                    "text": _strip_tokens(stream[i + 1 : end_idx]),
                    "url": url,
                }
                link_run.update(styles.get(i + 1, {}))
                runs.append(link_run)
                i = end_idx + 1
            elif ch in (CUSTOM_RANGE_START, CUSTOM_RANGE_END):
                i += 1
            else:
                fl = styles.get(i)
                key = tuple(sorted(fl)) if fl else None
                if key != cur_flags:
                    flush()
                    cur_flags = key
                cur_text.append(ch)
                i += 1
        flush()

        meta = paras_meta[p_idx] if p_idx < len(paras_meta) else {}
        btype, level = _block_type_from_meta(meta)
        block: dict[str, Any] = {
            "type": btype, "level": level, "runs": runs or [{"text": ""}],
        }
        align = _alignment_from_meta(meta)
        if align:
            block["align"] = align
        blocks.append(block)
    return blocks


def append_blocks(
    snap: dict[str, Any], blocks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a NEW snapshot with ``blocks`` appended (existing content kept).

    A blank document is replaced by the new blocks (matching
    :func:`append_paragraph_with_runs`); existing headings/lists/styled runs are
    preserved by re-deriving them via :func:`get_blocks`.
    """
    existing = get_blocks(snap) if isinstance(snap, dict) else []
    if get_paragraphs(snap) in ([""], []):
        new_blocks = list(blocks)
    else:
        new_blocks = [*existing, *blocks]
    out = copy.deepcopy(snap) if isinstance(snap, dict) else {}
    if "id" not in out:
        out["id"] = f"doc-{uuid4().hex[:12]}"
    out.setdefault("documentStyle", {})
    out["body"] = build_body_with_blocks(new_blocks)
    return out


