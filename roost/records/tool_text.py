"""Text a write tool takes from the model (M2 final fix). Every tool result
escapes record text with ``html.escape(quote=True)`` — the rule against tag
smuggling — so text the model copies from a result into a write arrives as
``&#x27;``, ``&amp;``, ``&quot;``, ``&lt;`` and ``&gt;``. ``plain`` reverses
exactly that escape, in one pass, so a copied "Ana&#x27;s" is stored as
"Ana's" and a stored literal "&amp;" (shown as "&amp;amp;") comes back exact.
Never ``html.unescape``: its legacy names without a semicolon would turn
"Tasks&notes" into "Tasks¬es"."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&#39;": "'"}
_ENTITY = re.compile("|".join(re.escape(entity) for entity in _ENTITIES))


def plain(text: str) -> str:
    """``text`` with the tool-result escape undone (and nothing else)."""
    return _ENTITY.sub(lambda match: _ENTITIES[match.group(0)], text)


ToolText = Annotated[str, AfterValidator(plain)]
