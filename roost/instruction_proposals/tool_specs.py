"""The instructions card's tool spec, apart from its handler so the tool catalog imports no service."""

from __future__ import annotations

from roost.constants import INSTRUCTION_SECTIONS, INSTRUCTION_WHY_MAX, MAX_BOT_INSTRUCTIONS_LENGTH
from roost.instruction_proposals.texts import CHANGE_TAINTED
from roost.llm.types import ToolSpec
from roost.talk.tool_def import ToolDef

TOOL_NAME = "propose_instructions_update"

PROPOSE_INSTRUCTIONS_SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "Offer the user new instructions for yourself (only your own), when what they told you shows your "
        "instructions should change. Send them in full, in Markdown sections: ## Who you are and context, "
        "## What you do, ## Rules, ## Tone, ## Team. The user sees what changes and your reason on a card; nothing "
        "changes until they press Accept. At most one card waits at a time."),
    input_schema={"type": "object", "properties": {
        "new_text": {"type": "string",
                     "description": f"Your full new instructions (at most {MAX_BOT_INSTRUCTIONS_LENGTH} characters)."},
        "why": {"type": "string", "description": f"One line: why they should change (at most {INSTRUCTION_WHY_MAX})."},
    }, "required": ["new_text", "why"]},
)

UPDATE_TOOL_NAME = "update_my_instructions"

UPDATE_INSTRUCTIONS_SPEC = ToolSpec(
    name=UPDATE_TOOL_NAME,
    description=(
        "Change one section of your own instructions at once, when the user asks you in their own chat to change "
        "how you behave. Send that section's full new text. The user sees an \"Updated my instructions\" line "
        "with Undo. Only in the user's own chat, in a run their message started; anywhere else use "
        "propose_instructions_update."),
    input_schema={"type": "object", "properties": {
        "section": {"type": "string", "enum": list(INSTRUCTION_SECTIONS),
                    "description": "Which section to change."},
        "new_text": {"type": "string", "description": (
            f"The section's full new text, without its heading (at most {MAX_BOT_INSTRUCTIONS_LENGTH} characters).")},
        "why": {"type": "string", "description": f"One line: what the user asked (at most {INSTRUCTION_WHY_MAX})."},
    }, "required": ["section", "new_text", "why"]},
)

INSTRUCTION_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(PROPOSE_INSTRUCTIONS_SPEC, "write_change", allowed_when_tainted=True, no_ask=True),
    # A direct change with an Undo line: no Ask card. A tainted run is refused outside your own chat (owner chat rule).
    ToolDef(UPDATE_INSTRUCTIONS_SPEC, "write_change", no_ask=True, tainted_refusal=CHANGE_TAINTED),
)
