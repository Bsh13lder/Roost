"""The bot's routine tools.

The direct tools (``create_routine``, ``update_routine``, ``pause_routine``, ``resume_routine``,
``delete_routine``) write at once, but only in a run the user's own message started in a 1:1 chat; they carry the
normal gate kinds, so the bot's approval mode decides (an Ask card, Auto-edit, or a step of a Proposal), and a tainted
run outside your own chat is refused by the gate itself. ``list_routines`` and the ``propose_*`` tools work anywhere: a
proposal is flagged ``allowed_when_tainted`` (the card is marked) and ``no_ask`` (the proposal card IS the ask)."""

from __future__ import annotations

from roost.constants import (
    ROUTINE_FINISHED_KEEP_DAYS, ROUTINE_FINISHED_REASON_MAX, ROUTINE_INSTRUCTIONS_MAX, ROUTINE_NAME_MAX,
    WATCH_EVERY_MAX_MINUTES, WATCH_EVERY_MIN_MINUTES,
)
from roost.llm.types import ToolSpec
from roost.routines.direct_texts import TAINTED_TEXT
from roost.standing.constants import STANDING_ACTIONS, STANDING_MAX_PER_DAY_MAX, STANDING_UNTIL_MAX_DAYS
from roost.talk.tool_def import ToolDef

_SCHEDULE_PROPERTY = {
    "type": "object",
    "description": ("When it runs, in local time. Either {\"kind\": \"times\", \"days\": [1..7 (1=Monday)], "
                    "\"times\": [\"HH:MM\"]} or {\"kind\": \"cron\", \"expr\": \"0 9 * * 1\"} (no more often than "
                    "every 15 minutes)."),
}

_WATCH_PROPERTY = {
    "type": "object",
    "description": ("Optional: only run when a page changes. {\"url\": \"https://…\" (a page the user named), "
                    "\"part\": \"what to watch in plain words, like the physio chat or the price box\", "
                    f"\"every_min\": {WATCH_EVERY_MIN_MINUTES}..{WATCH_EVERY_MAX_MINUTES} (how often Roost checks)}}. "
                    "Roost reads the page itself and starts a run only when that part changed, telling you what is "
                    "new. {\"off\": true} stops watching."),
    "properties": {"url": {"type": "string"}, "part": {"type": "string"}, "every_min": {"type": "integer"},
                   "off": {"type": "boolean"}},
}

LIST_ROUTINES_SPEC = ToolSpec(
    name="list_routines",
    description="List your own routines: name, when they run, whether they are on, and the next run (local time).",
    input_schema={"type": "object", "properties": {}},
)

_PERMISSION_PROPERTY = {
    "type": "object",
    "description": ("Optional standing permission, only when the routine must post, send or submit on one site "
                    "with nobody watching: {\"host\": \"x.com\", \"action\": \"post\"|\"send\"|\"submit\", "
                    f"\"max_per_day\": 1..{STANDING_MAX_PER_DAY_MAX}, \"until\": \"YYYY-MM-DD\" (at most "
                    f"{STANDING_UNTIL_MAX_DAYS} days ahead)}}. The user approves it with the routine; each act it "
                    "covers is still checked and can still ask. Never for buying, deleting or account changes."),
    "properties": {"host": {"type": "string"}, "action": {"type": "string", "enum": list(STANDING_ACTIONS)},
                   "max_per_day": {"type": "integer"}, "until": {"type": "string"}},
}

PROPOSE_ROUTINE_SPEC = ToolSpec(
    name="propose_routine",
    description=("Propose a new routine for yourself. The user sees a card and it starts only after they approve. "
                 "Repeat the exact next run time back to the user in local time."),
    input_schema={"type": "object", "properties": {
        "name": {"type": "string", "description": f"A short name, up to {ROUTINE_NAME_MAX} characters."},
        "instructions": {"type": "string",
                         "description": f"What to do each time, up to {ROUTINE_INSTRUCTIONS_MAX} characters."},
        "schedule": _SCHEDULE_PROPERTY,
        "permission": _PERMISSION_PROPERTY,
        "watch": _WATCH_PROPERTY,
    }, "required": ["name", "instructions", "schedule"]},
)

PROPOSE_ROUTINE_CHANGE_SPEC = ToolSpec(
    name="propose_routine_change",
    description=("Propose a change to one of your routines (its name, instructions, schedule or watch). The user "
                 "sees a card with the differences and it applies only after they approve."),
    input_schema={"type": "object", "properties": {
        "routine_id": {"type": "string", "description": "The routine's id from list_routines."},
        "name": {"type": "string"}, "instructions": {"type": "string"}, "schedule": _SCHEDULE_PROPERTY,
        "watch": _WATCH_PROPERTY,
    }, "required": ["routine_id"]},
)

PROPOSE_ROUTINE_PAUSE_SPEC = ToolSpec(
    name="propose_routine_pause",
    description=("Propose pausing one of your routines when pause_routine is refused here. The user sees a card "
                 "and it pauses only after they approve."),
    input_schema={"type": "object", "properties": {
        "routine_id": {"type": "string", "description": "The routine's id from list_routines."},
    }, "required": ["routine_id"]},
)

_ROUTINE_ID = {"routine_id": {"type": "string", "description": "The routine's id from list_routines."}}
_DIRECT_NOTE = (" Only when the user asked for it in their own message to you; elsewhere it is refused and you "
                "use the propose tools.")

# A routine's own model (owner, 2026-11-09): leave it out to run on your own model. Pick a cheaper one only for a
# simple, repeated job, and say why in your reply; the user changes it in one tap, and two failed runs in a row on it
# go back to your model.
_MODEL_PROPERTY: dict = {
    "type": "string", "enum": ["same", "haiku", "sonnet", "opus", "fable"],
    "description": ("The model this routine runs on. Leave it out (or 'same') for your own model. Pick 'haiku' or "
                    "'sonnet' only for a simple, repeated check, and tell the user which and why."),
}

CREATE_ROUTINE_SPEC = ToolSpec(
    name="create_routine",
    description=("Create a routine for yourself when the user asked for one: it runs on its schedule from now on. "
                 "Repeat the exact next run time back to the user in local time." + _DIRECT_NOTE),
    input_schema={"type": "object", "properties": {
        "name": {"type": "string", "description": f"A short name, up to {ROUTINE_NAME_MAX} characters."},
        "instructions": {"type": "string",
                         "description": f"What to do each time, up to {ROUTINE_INSTRUCTIONS_MAX} characters."},
        "schedule": _SCHEDULE_PROPERTY,
        "watch": _WATCH_PROPERTY,
        "model": _MODEL_PROPERTY,
    }, "required": ["name", "instructions", "schedule"]},
)

UPDATE_ROUTINE_SPEC = ToolSpec(
    name="update_routine",
    description=("Change one of your routines (its name, instructions, schedule or watch) as the user asked."
                 + _DIRECT_NOTE),
    input_schema={"type": "object", "properties": {
        **_ROUTINE_ID, "name": {"type": "string"}, "instructions": {"type": "string"},
        "schedule": _SCHEDULE_PROPERTY, "watch": _WATCH_PROPERTY, "model": _MODEL_PROPERTY,
    }, "required": ["routine_id"]},
)


def _by_id(name: str, what: str) -> ToolSpec:
    return ToolSpec(name=name, description=what + _DIRECT_NOTE,
                    input_schema={"type": "object", "properties": dict(_ROUTINE_ID), "required": ["routine_id"]})


PAUSE_ROUTINE_SPEC = _by_id("pause_routine", "Pause one of your routines as the user asked.")
RESUME_ROUTINE_SPEC = _by_id("resume_routine", "Switch one of your paused routines back on as the user asked.")
DELETE_ROUTINE_SPEC = _by_id("delete_routine", "Delete one of your routines and its history as the user asked.")


# Finishing (owner, 2026-11-11): only in a routine's own run, only for that routine; it reduces what runs, so a
# tainted change run may call it and no Ask card stands in front of it. Outside a routine run the handler refuses.
FINISH_ROUTINE = "finish_routine"
FINISH_ROUTINE_SPEC = ToolSpec(
    name=FINISH_ROUTINE,
    description=("Only inside a routine's own run: end this routine because its purpose is complete (what it "
                 "waited for happened, or its one-off job is done). It is paused and deleted after "
                 f"{ROUTINE_FINISHED_KEEP_DAYS} days unless the user resumes it. Never for a run that merely found "
                 "nothing new."),
    input_schema={"type": "object", "properties": {
        "reason": {"type": "string",
                   "description": f"Why it is done, in one short line (up to {ROUTINE_FINISHED_REASON_MAX} characters)."},
    }, "required": ["reason"]},
)


def _direct(spec: ToolSpec, kind) -> ToolDef:
    return ToolDef(spec, kind, tainted_refusal=TAINTED_TEXT, refused_when_tainted=True)


DIRECT_ROUTINE_TOOL_DEFS: tuple[ToolDef, ...] = (
    _direct(CREATE_ROUTINE_SPEC, "write_create"),
    _direct(UPDATE_ROUTINE_SPEC, "write_change"),
    _direct(PAUSE_ROUTINE_SPEC, "write_change"),
    _direct(RESUME_ROUTINE_SPEC, "write_change"),
    _direct(DELETE_ROUTINE_SPEC, "write_change"),     # the gate has no stricter kind for a delete
)
DIRECT_ROUTINE_NAMES = frozenset(tool.name for tool in DIRECT_ROUTINE_TOOL_DEFS)

ROUTINE_TOOL_DEFS: tuple[ToolDef, ...] = (
    ToolDef(LIST_ROUTINES_SPEC, "read", allowed_when_tainted=True),
    ToolDef(PROPOSE_ROUTINE_SPEC, "write_create", allowed_when_tainted=True, no_ask=True),
    ToolDef(PROPOSE_ROUTINE_CHANGE_SPEC, "write_change", allowed_when_tainted=True, no_ask=True),
    ToolDef(PROPOSE_ROUTINE_PAUSE_SPEC, "write_change", allowed_when_tainted=True, no_ask=True),
    ToolDef(FINISH_ROUTINE_SPEC, "write_change", allowed_when_tainted=True, no_ask=True),
    *DIRECT_ROUTINE_TOOL_DEFS,
)
