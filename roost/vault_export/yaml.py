"""The export's front matter, pure: every string is written JSON-quoted (a valid YAML double-quoted scalar),
so no title, tag or note text can break out of its line or the block."""

from __future__ import annotations

import json
import re
from typing import Iterable, Sequence, Union

from roost.tags.rules import obsidian_tag
from roost.vault_export.defang import label as wikilink_label

Value = Union[str, int, float, bool, None, Sequence[str]]
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _scalar(value: Value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in value) + "]"


def front_matter(props: Iterable[tuple[str, Value]]) -> str:
    """A ``---`` block; a key that is not a plain YAML key, or a ``None`` value, is left out."""
    lines = [f"{key}: {_scalar(value)}" for key, value in props if value is not None and _KEY.fullmatch(key)]
    return "---\n" + "".join(f"{line}\n" for line in lines) + "---\n"


def vault_tags(kind_tag: str, tags: Iterable[str]) -> list[str]:
    """``roost/<kind>`` first, then the record's tags in Obsidian's spelling (``bot:ana`` -> ``bot/ana``)."""
    out = [kind_tag]
    for tag in tags:
        cleaned = obsidian_tag(tag)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def link(path: str, label: str) -> str:
    """A path wikilink without the ``.md``: ``[[Roost/Projects/Garden/Garden|Garden]]``."""
    target = path[:-3] if path.endswith(".md") else path
    return f"[[{target}|{wikilink_label(label)}]]"
