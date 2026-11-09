"""Model ids are spelled in roost/llm/registry.py and nowhere else."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_ID = re.compile(r"claude-(fable|opus|sonnet|haiku|mythos)-\d")


def _sources():
    yield from (ROOT / "roost").rglob("*.py")
    web = ROOT / "web" / "src"
    for pattern in ("*.ts", "*.tsx"):
        yield from web.rglob(pattern)


def test_no_model_id_outside_the_registry():
    registry = ROOT / "roost" / "llm" / "registry.py"
    offenders = [
        str(p.relative_to(ROOT))
        for p in _sources()
        if p != registry and _ID.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []
