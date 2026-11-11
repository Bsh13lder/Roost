"""CLAUDE.md loads on every turn, and the README is what a user reads first (projects hub, Task 10).
The Documentation Map names the plans that shaped the code, and only files that exist. The
Architecture section says where projects live. The README calls an expense's group its project (H1)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "user-guide.md"
HUB_DOCS = (
    "docs/plans/2026-10-14-roost-projects-hub-design.md",
    "docs/plans/2026-10-14-roost-projects-hub.md",
)
REDESIGN_DOCS = (
    "docs/plans/2026-10-15-roost-look-and-feel-design.md",
    "docs/plans/2026-10-15-roost-redesign-p1-foundation.md",
    "docs/plans/2026-10-15-roost-redesign-p2-chat.md",
    "docs/plans/2026-10-16-roost-redesign-p3-tasks.md",
)
MEMORY_DOCS = ("docs/plans/2026-10-20-roost-memory-design.md", "docs/plans/2026-10-20-roost-memory.md")
MEMORY_PLACES = (
    "roost/memory/", "memories:text", "memory_note", "POST /api/bots/{id}/chat", "chat_summaries",
    "web/src/components/memory/",
)
R1_DOCS = ("docs/plans/2026-10-20-roost-polish-r1-design.md", "docs/plans/2026-10-20-roost-polish-r1.md")
R1_PLACES = (
    "web/src/components/sidebar/", "web/src/components/panel/", "?panel=", "bots:group_label", "schema v16",
    "web/src/lib/chatMarks.ts", "web/tests/stylesheets.test.ts",
)
MODELS_DOCS = ("docs/plans/2026-10-20-roost-models-helpers-design.md", "docs/plans/2026-10-20-roost-models-helpers.md")
MODEL_IDS = ("claude-fable-5-2", "claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5")
MODELS_PLACES = (
    "roost/llm/registry.py", "roost/models_check/", "roost/helpers/", "send_helpers", "suggest_model", "schema v20",
)
INTEGRATION_DOCS = (
    "docs/plans/2026-10-20-roost-board-redesign-design.md", "docs/plans/2026-10-20-roost-tasks-money-polish-design.md",
    "docs/plans/2026-10-20-roost-tasks-money-polish.md", "docs/plans/2026-10-20-roost-lazyclaw-tasks-money-migration.md",
)
INTEGRATION_PLACES = (
    "robots-v7-sketch.html", "LENSBOT_SHAPES", "BOT_ROLES", "LEGACY_SHAPE_TO_LENSBOT", "web/src/components/board/", "web/src/components/board/kanban/",
    "schema v21", "money_expenses.kind", "roost/migrate/lazyclaw/", "import_links",
)
LOOK_PLACES = (
    "web/src/styles/tokens.css", "web/src/ui/", "web/src/components/robot/", "/api/bots/{id}/picture",
    "web/src/components/markdown/", "web/src/components/chat/", "web/src/lib/unread.ts",
    "web/src/components/tasks/", "roost/tasks/step_service.py", "task_comments", "POST /api/tasks/parse",
)
APPROVAL_MAC_DOCS = (
    "docs/plans/2026-10-21-roost-mac-folders-design.md", "docs/plans/2026-10-22-roost-approval-modes-mac-folders.md",
)
APPROVAL_MAC_PLACES = (
    "roost/approvals/", "roost/mac/", "roost/keeper/macfs/", "approval_cards", "mac_grants", "mac_file_marks",
    "approval_result", "mac_activity",
)
COMPUTERS_DOCS = (
    "docs/plans/2026-10-20-roost-computers-2-design.md", "docs/plans/2026-10-20-roost-computers-c1-c2.md",
)
COMPUTERS_PLACES = (
    "roost/keeper/computers.py", "roost/desk/rfb.py", "/api/bots/{id}/live", "roost/vault/", "bots.computer",
)
C3_DOCS = ("docs/plans/2026-10-22-roost-computers-c3-design.md", "docs/plans/2026-10-22-roost-computers-c3.md")
C3_PLACES = (
    "roost/computer_use/", "judge_act", "POST /desks/{id}/computer/input", "roost-input", "xdotool",
    "ComputerUseLease", "Browsing actions", "computer_pointer", "ROOST_FAKE_SCREEN",
)
C3_NOT_BUILT = "planned and not built"
C3_README_HEADING = "## Your bot uses its computer"
FINAL_PASS_PLACES = (
    # the chat feel
    "FIRST_LINE_ACTIVITY", "roost/choices/", "ask_choice", "DecisionBook", "stuck_status_line", "Madrid", "reaction",
    # routines and plan
    "roost/routines/", "roost/routines/scheduler.py", "roost/questions/", "roost/plan/", "schema v25", "note_question",
    "NoUsageSource", "full_limit_until", "reminder_sends", "propose_routine",
    # hardening
    "0.2.170", "HMAC-SHA256", "roost/log_rotation.py", "~/Roost/logs", "decrypt_field", "DISABLE_TELEMETRY",
    # Roost Lead and the freeze
    "~/roost-handoff/", "Roost Lead", "The v1 freeze",
)
FIRST_PLAN_DAY = "2026-10-20"
LAST_PLAN_DAY = "2026-10-22"
MAP_HEADING = "## Documentation Map"
ARCHITECTURE_HEADING = "## Architecture"
OLD_MONEY_WORD = "categor"            # "category" / "categories": money is grouped by project now (H1)
_MAP_ENTRY = re.compile(r"^- `([^`]+\.md)`", re.MULTILINE)


def _section(text: str, heading: str) -> str:
    """The text under ``heading``, up to the next ``## `` heading."""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _map_paths() -> list[str]:
    return _MAP_ENTRY.findall(_section(CLAUDE_MD.read_text(encoding="utf-8"), MAP_HEADING))


def test_the_documentation_map_names_the_projects_hub_design_and_plan():
    assert [path for path in HUB_DOCS if path not in _map_paths()] == []


def test_the_documentation_map_names_the_redesign_design_and_its_plans():
    assert [path for path in REDESIGN_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_the_look_lives():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in LOOK_PLACES if place not in architecture] == []


def test_every_file_on_the_documentation_map_exists():
    paths = _map_paths()
    assert paths, "the Documentation Map lists no files"
    assert [path for path in paths if not (ROOT / path).is_file()] == []


def test_the_architecture_section_says_where_projects_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert "roost/projects/" in architecture
    assert "/board/projects/:projectId" in architecture


def test_the_readme_calls_an_expenses_group_its_project():
    assert OLD_MONEY_WORD not in README.read_text(encoding="utf-8").casefold()


def test_the_documentation_map_names_the_memory_design_and_plan():
    assert [path for path in MEMORY_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_memory_lives():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in MEMORY_PLACES if place not in architecture] == []


def test_the_documentation_map_names_the_polish_r1_design_and_plan():
    assert [path for path in R1_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_the_shell_lives():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in R1_PLACES if place not in architecture] == []


def test_the_documentation_map_names_the_models_design_and_plan():
    assert [path for path in MODELS_DOCS if path not in _map_paths()] == []


def test_the_constraints_name_the_current_model_ids():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    constraints = text.split("## Global Constraints", 1)[1].split("\n## ", 1)[0]
    assert [model_id for model_id in MODEL_IDS if model_id not in constraints] == []
    assert "claude-sonnet-5`" not in constraints and "claude-haiku-4-5" not in constraints


def test_the_architecture_section_says_where_helpers_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in MODELS_PLACES if place not in architecture] == []


def test_the_documentation_map_names_the_board_redesign_tasks_money_and_importer_docs():
    assert [path for path in INTEGRATION_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_ghosts_the_board_income_and_the_importer_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in INTEGRATION_PLACES if place not in architecture] == []


def test_the_documentation_map_names_the_approval_and_mac_plans():
    assert [path for path in APPROVAL_MAC_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_approvals_and_mac_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in APPROVAL_MAC_PLACES if place not in architecture] == []


def test_the_documentation_map_names_the_computers_design_and_plan():
    assert [path for path in COMPUTERS_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_the_bots_computers_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in COMPUTERS_PLACES if place not in architecture] == []


def test_the_notices_cover_the_computers_programs():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "## Computers 2.0" in notices
    for name in ("noVNC", "pako", "seccomp", "TigerVNC", "JWM", "xterm", "tini", "Brave Browser", "python3", "roost-egress"):
        assert name in notices


def test_the_documentation_map_names_every_plan_from_the_last_three_days():
    plans = sorted(path.name for path in (ROOT / "docs" / "plans").glob("*.md")
                   if FIRST_PLAN_DAY <= path.name[:10] <= LAST_PLAN_DAY)
    assert plans, "no plans in the date range"
    assert [name for name in plans if f"docs/plans/{name}" not in _map_paths()] == []


def test_the_architecture_section_covers_the_chat_feel_routines_hardening_and_the_freeze():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert [place for place in FINAL_PASS_PLACES if place not in text] == []


def test_the_architecture_section_says_where_choices_and_routines_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert "roost/choices/" in architecture and "roost/routines/" in architecture and "roost/plan/" in architecture


def test_the_tagline_says_encrypted_at_rest_and_no_text_claims_end_to_end():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "encrypted at rest (true end-to-end planned)" in text.splitlines()[2]
    assert "E2E-encrypted" not in text and "E2E-encrypted" not in README.read_text(encoding="utf-8")


def test_the_licence_rule_allows_hpnd_and_the_web_gate_agrees():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "MPL-2.0/HPND" in text and "2026-10-21" in text
    assert '"HPND"' in (ROOT / "web" / "tests" / "licenseGate.ts").read_text(encoding="utf-8")


def test_the_vocabulary_table_has_the_profile_tabs_and_the_new_words():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "Info · Plan · Documents · Computer · Links" in text
    for word in ("Routine", "Question book", "Use the full limit until it resets", "Options card", "Decisions", "Tapback", "Queued"):
        assert f"| {word}" in text or f"| {word} " in text or f"{word} (" in text or word in text.split("## Documentation Map")[0]


def test_the_readme_lists_what_bots_can_do_with_routines_the_plan_and_options_cards():
    readme = GUIDE.read_text(encoding="utf-8").split("## What bots can do", 1)[1].split("\n## ", 1)[0]
    for phrase in ("Routines and Reports", "question book", "The Plan", "Options cards and Decisions", "Queued"):
        assert phrase in readme


def test_the_documentation_map_names_the_c3_design_and_plan():
    assert [path for path in C3_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_computer_use_lives():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in C3_PLACES if place not in architecture] == []
    assert C3_NOT_BUILT not in CLAUDE_MD.read_text(encoding="utf-8")


def test_the_readme_says_what_a_bot_does_on_its_computer_and_what_asks():
    readme = GUIDE.read_text(encoding="utf-8")
    assert C3_README_HEADING in readme
    section = readme.split(C3_README_HEADING, 1)[1].split("\n## ", 1)[0]
    for phrase in ("Browsing actions", "Just do it", "Ask first", "buy", "send", "submit", "Take control", "never"):
        assert phrase in section
