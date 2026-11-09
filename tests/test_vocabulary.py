"""D1's words: Computer, Take control / Give it back, Chat, Profile, Board, main bot.
The old nouns must not come back into the web face or the vocabulary table."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IN_UI = (
    "Take the wheel", "About this desk", "Ask the team", "Add Chief", ">Desk<", "Talk ·",
    # D2: no role gates anything, so no text may send the user to "a bot with the Finance role in Talk".
    "role in Talk", "Finance role", " in Talk",
)


def _web_sources() -> list[Path]:
    src = ROOT / "web" / "src"
    return sorted([*src.rglob("*.tsx"), *src.rglob("*.ts")])


def test_the_web_face_uses_the_s1_words():
    offenders = [(str(path.relative_to(ROOT)), word) for path in _web_sources()
                 for word in FORBIDDEN_IN_UI if word in path.read_text(encoding="utf-8")]
    assert offenders == []


# Projects hub H1: money is grouped by project. "category" lives on only as a task's
# list (`task.category`, lower case), which the Board shows as a plain chip.
FORBIDDEN_MONEY_WORDS = ("Category", "By category", "categories")


def test_the_web_face_says_project_not_category():
    offenders = [(str(path.relative_to(ROOT)), word) for path in _web_sources()
                 for word in FORBIDDEN_MONEY_WORDS if word in path.read_text(encoding="utf-8")]
    assert offenders == []


def test_the_vocabulary_tables_name_the_computer_and_take_control():
    for doc in (ROOT / "CLAUDE.md", ROOT / "docs" / "specs" / "2026-10-12-roost-design.md"):
        text = doc.read_text(encoding="utf-8")
        assert "| A bot's computer | Computer |" in text, doc.name
        assert "| Control the bot's browser / return it | Take control / Give it back |" in text, doc.name


def test_claude_md_no_longer_teaches_the_old_words():
    # The spec keeps "take the wheel" in its history sections (§5.5, §11); CLAUDE.md loads on every turn.
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Take the wheel" not in text and "| Desk |" not in text
