"""Redesign P2: a bot's steps show in its reply as compact lines, and a finished step reads in the past
tense ("adding a task" becomes "Added a task"). The web does that with one table, ``PAST`` in
``web/src/lib/toolLines.ts``; this test keeps it in step with every verb the gateway announces."""

import re
from pathlib import Path

from roost.documents.tools import _ACTIVITY as DOCUMENT_ACTIVITY
from roost.mac.tools import _ACTIVITY as MAC_ACTIVITY
from roost.memory.tools import _ACTIVITY as MEMORY_ACTIVITY
from roost.money.tools import _ACTIVITY as MONEY_ACTIVITY
from roost.notes.tools import _ACTIVITY as NOTE_ACTIVITY
from roost.projects.tools import _ACTIVITY as PROJECT_ACTIVITY
from roost.tasks.tools import _ACTIVITY as TASK_ACTIVITY

ROOT = Path(__file__).resolve().parents[1]
TOOL_LINES = ROOT / "web" / "src" / "lib" / "toolLines.ts"
TALK = ROOT / "roost" / "talk"
ANNOUNCED = re.compile(r'announce\(f?"([a-z]+)[ :]')
PAST_ENTRY = re.compile(r'\b([a-z]+): "[a-z]+"')


def _web_past_verbs() -> set[str]:
    table = TOOL_LINES.read_text(encoding="utf-8").split("const PAST")[1].split("};")[0]
    return set(PAST_ENTRY.findall(table))


def _announced_verbs() -> set[str]:
    domain = [*TASK_ACTIVITY.values(), *MONEY_ACTIVITY.values(), *NOTE_ACTIVITY.values(),
              *DOCUMENT_ACTIVITY.values(), *PROJECT_ACTIVITY.values(), *MEMORY_ACTIVITY.values(), *MAC_ACTIVITY.values()]
    spoken = [verb for path in TALK.glob("*.py") for verb in ANNOUNCED.findall(path.read_text(encoding="utf-8"))]
    return {text.split()[0] for text in domain} | set(spoken)


def test_the_scan_finds_the_web_table_and_the_spoken_verbs():
    assert {"adding", "writing"} <= _web_past_verbs()
    assert {"opening", "reading", "asking", "creating", "waiting", "switching", "editing", "renaming"} <= _announced_verbs()


def test_every_announced_verb_has_a_past_tense_on_the_web():
    assert sorted(_announced_verbs() - _web_past_verbs()) == []
