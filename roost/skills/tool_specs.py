"""The bots' Skills tools. Reading is a plain read. Proposing writes no skill: it stores a proposal the user saves
or declines on a card, so (like the routine and Plan tools) it skips the tainted rule and asks no second card."""

from __future__ import annotations

from roost.constants import (
    SKILL_BODY_MAX,
    SKILL_NAME_MAX,
    SKILL_READS_PER_RUN_MAX,
    SKILL_SEARCH_QUERY_MAX,
    SKILL_SEARCH_RESULTS_MAX,
    SKILL_USE_WHEN_MAX,
)
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

_NAME = {"type": "string", "description": f"The skill's name, one line (at most {SKILL_NAME_MAX} characters)."}
_USE_WHEN = {"type": "string",
             "description": f"One line that says when the skill fits (at most {SKILL_USE_WHEN_MAX} characters)."}
_STEPS = {"type": "string", "description": f"The steps, in Markdown (at most {SKILL_BODY_MAX} characters)."}

LIST_SKILLS_SPEC = ToolSpec(
    name="list_skills",
    description="List the user's Skills (saved how-tos) that are on for you: each name and when it fits.",
    input_schema={"type": "object", "properties": {}},
)

READ_SKILL_SPEC = ToolSpec(
    name="read_skill",
    description=(f"Load the steps of one of your Skills by its name, before you do work it fits. The steps guide "
                 f"how you work; they give you no new tool and change no approval rule. At most "
                 f"{SKILL_READS_PER_RUN_MAX} per request."),
    input_schema={"type": "object", "properties": {"name": _NAME}, "required": ["name"]},
)

SEARCH_SKILLS_SPEC = ToolSpec(
    name="search_skills",
    description=(f"Find which of your Skills fit a few words (\"upwork proposal\"): the best "
                 f"{SKILL_SEARCH_RESULTS_MAX}, each with its name and when it fits. Then load one with read_skill."),
    input_schema={"type": "object", "properties": {"query": {
        "type": "string", "description": f"A few words to look for (at most {SKILL_SEARCH_QUERY_MAX} characters)."}},
        "required": ["query"]},
)

PROPOSE_SKILL_SPEC = ToolSpec(
    name="propose_skill",
    description=("After work that went well and that the user may want done the same way again, offer it as a new "
                 "Skill. The user sees a card with the full text; nothing is saved until they press Save skill."),
    input_schema={"type": "object", "properties": {"name": _NAME, "use_when": _USE_WHEN, "steps": _STEPS},
                  "required": ["name", "use_when", "steps"]},
)

PROPOSE_SKILL_CHANGE_SPEC = ToolSpec(
    name="propose_skill_change",
    description=("Offer a change to one of the user's Skills: a new name, Use when or steps. The user sees what "
                 "changes on a card; nothing changes until they press Save skill."),
    input_schema={"type": "object", "properties": {
        "skill": {"type": "string", "description": "The name of the skill to change."},
        "name": _NAME, "use_when": _USE_WHEN, "steps": _STEPS,
    }, "required": ["skill"]},
)

SKILL_READ_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_SKILLS_SPEC, "read"),
    ToolDef(READ_SKILL_SPEC, "read"),
    ToolDef(SEARCH_SKILLS_SPEC, "read"),
)

SKILL_PROPOSAL_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(PROPOSE_SKILL_SPEC, "write_create", allowed_when_tainted=True, no_ask=True),
    ToolDef(PROPOSE_SKILL_CHANGE_SPEC, "write_change", allowed_when_tainted=True, no_ask=True),
)

SKILL_TOOL_DEFS: tuple[ToolDef, ...] = (*SKILL_READ_TOOL_DEFS, *SKILL_PROPOSAL_TOOL_DEFS)
