"""Docs as markdown (M2 D2, Roost): a new doc from markdown, markdown added to
a doc, and a doc read back as markdown or plain text — over the harvested
Univer block helpers (``doc_snapshot``) and markdown parser (``markdown_blocks``)."""

from __future__ import annotations

from typing import Any

from roost.documents.doc_snapshot import append_blocks, blank_document, get_blocks, get_paragraphs
from roost.documents.markdown_blocks import parse_blocks

_LIST_MARK = {"bullet": "- ", "number": "1. "}


def doc_from_markdown(title: str, markdown: str) -> dict[str, Any]:
    return append_blocks(blank_document(title), parse_blocks(markdown))


def append_markdown(snap: dict[str, Any], markdown: str) -> dict[str, Any]:
    return append_blocks(snap, parse_blocks(markdown))


def _run_markdown(run: dict[str, Any]) -> str:
    text = str(run.get("text", ""))
    if not text:
        return ""
    if run.get("bold"):
        text = f"**{text}**"
    if run.get("italic"):
        text = f"*{text}*"
    url = run.get("url")
    return f"[{text}]({url})" if url else text


def _block_markdown(block: dict[str, Any]) -> str:
    runs = "".join(_run_markdown(run) for run in block.get("runs") or [])
    if block.get("type") == "heading":
        return "#" * max(1, min(3, int(block.get("level") or 1))) + " " + runs
    return _LIST_MARK.get(str(block.get("type")), "") + runs


def doc_to_markdown(snap: dict[str, Any]) -> str:
    return "\n".join(_block_markdown(block) for block in get_blocks(snap)).strip("\n")


def doc_plain_text(snap: dict[str, Any]) -> str:
    """The doc's paragraphs as plain text, blank-line separated (what a PDF is made from)."""
    return "\n\n".join(paragraph for paragraph in get_paragraphs(snap) if paragraph.strip())
