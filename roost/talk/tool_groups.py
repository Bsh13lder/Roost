"""Tool groups (owner, 2026-11-09: "how does Claude Code do it? all tools and skills in one turn is too much").

Every model step used to carry the whole catalog (114 tools, about 66k characters of schema). A run is now offered
the core tools plus the groups it has loaded: the run's own words load a group before the first step
(``groups_in_text``), ``open_page`` loads the computer group, and the bot loads any other with ``load_tools``. A
loaded group stays for the rest of the run. Only what the model is shown changes: the gate, the allowlist and
every tool's rules stay the same. ``ROOST_TOOL_GROUPS=off`` offers the whole catalog again."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from roost.llm.types import ToolSpec

TOOL_GROUPS_ENV: Final = "ROOST_TOOL_GROUPS"
LOAD_TOOLS: Final = "load_tools"
COMPUTER_GROUP: Final = "computer"
ROUTINE_RUN_GROUP: Final = "routine_run"   # finish_routine: a routine's own run starts with it (run_groups.py)


@dataclass(frozen=True)
class ToolGroup:
    """A group's tools and the words (a regex, matched on lower-case text) that load it before the first step."""

    names: frozenset[str]
    words: str


CORE_TOOLS: Final = frozenset({
    "get_time", "remember", "recall", "forget", "search_chat", "ask_choice", "ask_for_help", "note_question",
    "web_search", "open_page", "read_page", "send_helpers", "list_skills", "search_skills", "read_skill",
    "ask_bot", "list_bots", LOAD_TOOLS,
})

TOOL_GROUPS: Final[Mapping[str, ToolGroup]] = {
    "tasks": ToolGroup(frozenset({
        "add_task", "update_task", "complete_task", "delete_task", "list_tasks", "add_step", "update_step",
        "delete_step", "move_step", "add_comment", "list_comments", "add_day_note",
    }), r"\b(?:tasks?|to-?dos?|remind|reminders?|due|deadline|steps?|overdue|today|tomorrow|tareas?|recu[eé]rd|"
        r"recordatorio|pendiente|ma[nñ]ana)"),
    "money": ToolGroup(frozenset({
        "log_expense", "update_expense", "delete_expense", "list_expenses", "money_summary", "set_budget",
        "add_topup", "edit_topup", "undo_topup",
    }), r"[€$£]|\b(?:expens|spent|spend|paid|budget|income|money|cost|invoice|receipt|top-?up|gast|pagu|pagad|"
        r"presupuesto|dinero|ingreso|factura|euros?|dollars?)"),
    "projects": ToolGroup(frozenset({
        "create_project", "update_project", "get_project", "list_projects", "set_document_project",
    }), r"#\w|\b(?:projects?|proyectos?)"),
    "notes": ToolGroup(frozenset({
        "add_note", "update_note", "append_to_note", "delete_note", "read_note", "find_notes", "create_doc",
        "create_sheet", "append_to_doc", "update_sheet_cells", "read_document", "list_documents",
        "delete_document", "make_pdf_from_doc",
    }), r"\b(?:notes?\b|docs?\b|documents?|sheets?|spreadsheet|pdf|write (?:it )?down|notas?\b|documentos?|"
        r"hojas?\b|apunt)"),
    "routines": ToolGroup(frozenset({
        "create_routine", "update_routine", "pause_routine", "resume_routine", "delete_routine", "list_routines",
        "propose_routine", "propose_routine_change", "propose_routine_pause",
    }), r"\b(?:routines?|every (?:day|morning|evening|night|week|hour|monday|tuesday|wednesday|thursday|friday|"
        r"saturday|sunday)|each (?:day|morning|week)|daily|weekly|hourly|schedul|rutinas?|cada (?:d[ií]a|ma[nñ]ana|"
        r"semana|hora)|todos los d[ií]as)"),
    "plan": ToolGroup(frozenset({
        "plan_read", "plan_add", "plan_update", "plan_complete", "journal_append", "journal_read",
    }), r"\b(?:your plan|my plan|the plan|journal|diary|diario)"),
    # A routine's own run starts with this group (run_groups.py); no words load it, since the tool refuses elsewhere.
    ROUTINE_RUN_GROUP: ToolGroup(frozenset({"finish_routine"}), r"(?!)"),
    COMPUTER_GROUP: ToolGroup(frozenset({
        "look", "click", "type", "press_key", "scroll", "wait_ready", "read_text", "read_pdf", "list_tabs",
        "switch_tab", "close_tab", "open_app", "use_saved_login", "use_vault_password", "ask_secret_field",
        "request_sign_in", "send_screenshot", "install_app", "remove_app", "list_apps",
    }), r"https?://|www\.|\.(?:com|es|net|org|io)\b|\b(?:sites?|website|web ?page|page|browser|click|tab|"
        r"sign ?in|log ?in|login|sign ?up|screen|screenshot|form|buy|book|order|apply|proposal|upwork|whatsapp|"
        r"gmail|install|app\b|apps\b|p[aá]gina|navegador|inicia|entra)"),
    "mac": ToolGroup(frozenset({
        "mac_find", "mac_read", "mac_write_new", "mac_edit", "mac_rename", "mac_trash",
    }), r"\b(?:mac\b|folders?|files?\b|finder|obsidian|vault folder|carpetas?|archivos?|ficheros?)"),
    "programs": ToolGroup(frozenset({
        "run_program", "write_file", "read_file", "list_files",
    }), r"\b(?:program|script|code|python|csv|calculat|workspace|programa)"),
    "connectors": ToolGroup(frozenset({
        "use_connector", "list_connectors", "request_connector",
    }), r"\b(?:connectors?|api\b|api key)"),
    "bots": ToolGroup(frozenset({
        "suggest_bot", "suggest_model", "create_bot", "set_bot_model", "update_my_instructions",
        "propose_instructions_update", "set_my_voice", "propose_skill", "propose_skill_change",
    }), r"\b(?:new bot|create (?:a )?bot|bots?\b|models?\b|opus|sonnet|haiku|fable|instructions|voice|skills?\b|"
        r"remember to always|from now on|nuevo bot|voz|habilidad)"),
}

_GROUP_OF: Final = {name: group for group, tools in TOOL_GROUPS.items() for name in tools.names}
_WORDS: Final = {group: re.compile(tools.words) for group, tools in TOOL_GROUPS.items()}
_NAME_RE: Final = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")

LOAD_TOOLS_SPEC: Final = ToolSpec(
    name=LOAD_TOOLS,
    description=(
        "Load more of your tools: name one or more groups from the list in your instructions (or a tool's own "
        "name). They are yours from your next step to the end of this request. Load what the request needs "
        "before you say you can't do something."
    ),
    input_schema={
        "type": "object",
        "properties": {"groups": {
            "type": "array", "items": {"type": "string", "enum": sorted(TOOL_GROUPS)},
            "description": "The groups to load.", "minItems": 1,
        }},
        "required": ["groups"],
    },
)

INDEX_LEAD: Final = ("More tools, loaded with load_tools when a request needs them (a tool listed here is not "
                     "yours until its group is loaded):")
LOADED_TEXT: Final = "Loaded: {groups}. Your new tools from the next step: {names}."
NOTHING_LOADED_TEXT: Final = "Nothing new loaded: name a group from your instructions' list."
UNKNOWN_TEXT: Final = " Unknown: {names}."


def tool_groups_on() -> bool:
    """The switch: anything but "off" keeps the groups on."""
    return os.environ.get(TOOL_GROUPS_ENV, "").strip().lower() != "off"


def group_of(name: str) -> str | None:
    """The group a tool is in; ``None`` for a core tool or an unknown name."""
    return _GROUP_OF.get(name)


def groups_in_text(text: str) -> frozenset[str]:
    """The groups a request's words call for, and the group of any tool named in them."""
    lower = text.lower()
    named = {_GROUP_OF[word] for word in _NAME_RE.findall(lower) if word in _GROUP_OF}
    return frozenset(named | {group for group, words in _WORDS.items() if words.search(lower)})


def _unloaded(specs: Iterable[ToolSpec], loaded: frozenset[str]) -> dict[str, list[str]]:
    waiting: dict[str, list[str]] = {}
    for spec in specs:
        group = _GROUP_OF.get(spec.name)
        if group is not None and group not in loaded:
            waiting.setdefault(group, []).append(spec.name)
    return waiting


def visible_specs(specs: tuple[ToolSpec, ...], loaded: frozenset[str]) -> tuple[ToolSpec, ...]:
    """The core tools and the loaded groups' tools, in the run's own order. ``load_tools`` stays even once every
    group is loaded (keeping the cache warm, §4): the offered list only ever grows during a run, so its tail never
    changes under the prompt cache."""
    return tuple(spec for spec in specs if spec.name in CORE_TOOLS or _GROUP_OF.get(spec.name) in loaded)


def index_text(specs: tuple[ToolSpec, ...], loaded: frozenset[str]) -> str:
    """The instructions' list of the groups not loaded yet, each with its tools' names; "" when none is left."""
    waiting = _unloaded(specs, loaded)
    if not waiting:
        return ""
    lines = [f"- {group}: {', '.join(names)}" for group, names in waiting.items()]
    return "\n".join((INDEX_LEAD, *lines))


def parse_groups(arguments: Mapping[str, Any]) -> tuple[frozenset[str], tuple[str, ...]]:
    """``load_tools``' groups, read leniently: a group's name in any case, or a tool's own name."""
    raw = arguments.get("groups", ())
    items = (raw,) if isinstance(raw, str) else tuple(raw) if isinstance(raw, (list, tuple)) else ()
    found: set[str] = set()
    unknown: list[str] = []
    for item in items:
        word = str(item).strip().lower()
        group = word if word in TOOL_GROUPS else _GROUP_OF.get(word)
        if group is None:
            unknown.append(str(item)[:40])
        else:
            found.add(group)
    return frozenset(found), tuple(unknown)


def load_tools_result(allowed: Iterable[str], groups: frozenset[str], *, unknown: tuple[str, ...]) -> str:
    """What the bot reads after ``load_tools``: the groups and the names of the run's tools it now has."""
    names = sorted(name for name in allowed if _GROUP_OF.get(name) in groups)
    text = (LOADED_TEXT.format(groups=", ".join(sorted(groups)), names=", ".join(names)) if names
            else NOTHING_LOADED_TEXT)
    return text + (UNKNOWN_TEXT.format(names=", ".join(unknown)) if unknown else "")
