"""What the audit keeps of a write: never file text, a diff or a note body (design §6; approval plan Task 12).

A ``mac_*`` call keeps its folder label, a keyed hash of its path, character and edit counts (``edit_count``) and two flags.
Any other write tool keeps ids, numbers, flags and a short list of plain choice words, and only the length of
everything else. A computer-use act (C3) keeps the label, host and class from the page's resolution, and for
``type`` the text's source, length and a keyed hash, never the text. A call that is not a write (``open_page`` and
the like) is unchanged."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import TYPE_CHECKING, Any, Mapping

from roost.approvals.topics import TOOL_TOPICS
from roost.constants import CU_ACT_TOOLS, CU_APP_NAME_RE, CU_KEYS, CU_LABEL_SHOWN_CHARS, CU_OPEN_APPS
from roost.mac.marks import path_key

if TYPE_CHECKING:
    from roost.computer_use.models import ActResolution

_SOURCE_KINDS = frozenset({"message", "card", "note", "document"})
_SOURCE_ID_MAX = 64
_APP_NAME = re.compile(CU_APP_NAME_RE)

# String values that are choices or dates, not the user's words.
_PLAIN_KEYS = frozenset({
    "id", "status", "priority", "currency", "kind", "day", "date", "spent_at", "reminder_at", "recurring",
    "recur_until", "due", "due_at", "mode", "effort", "model", "tag",
})


def _chars(value: Any) -> int:
    return len(value) if isinstance(value, str) else len(json.dumps(value, default=str))


def _mac(name: str, arguments: Mapping[str, Any], dek: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    folder, path = arguments.get("folder"), arguments.get("path")
    if isinstance(folder, str):
        out["folder"] = folder
        if isinstance(path, str):
            out["path_key"] = path_key(dek, folder, path)
    if name == "mac_find":                      # words to look for, never kept
        out["has_query"] = bool(arguments.get("query"))
        out["has_text"] = bool(arguments.get("text"))
        return out
    body = arguments.get("text") if arguments.get("text") is not None else arguments.get("new_text")
    if isinstance(body, str):
        out["chars"] = len(body)
        out["has_text"] = True
    if isinstance(arguments.get("edits"), list):
        out["edit_count"] = len(arguments["edits"])
    return out


def _record(arguments: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in arguments.items():
        plain = key in _PLAIN_KEYS or key.endswith("_id")
        if value is None or isinstance(value, (bool, int, float)) or (isinstance(value, str) and plain):
            out[key] = value
        else:
            out[key] = {"chars": _chars(value)}
    return out


def _source(value: Any) -> dict[str, Any]:
    """Where typed text came from: the source word and the record id, nothing else."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, Any] = {}
    kind, ref = value.get("from"), value.get("id")
    if kind in _SOURCE_KINDS:
        out["from"] = kind
    if isinstance(ref, str) and 0 < len(ref) <= _SOURCE_ID_MAX:
        out["id"] = ref
    return out


def _resolution_facts(act: "ActResolution | None") -> dict[str, Any]:
    if act is None:
        return {}
    label = act.target.text[:CU_LABEL_SHOWN_CHARS] if act.target is not None else ""
    return {"label": label, "host": act.host, "class": act.commit, "nav_host": act.nav_host, "space": act.space}


def _open_app(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """open_app: the app's id when it is one (a fixed app or a package name), and the reason's length only."""
    app, why = arguments.get("app"), arguments.get("why")
    out: dict[str, Any] = {}
    if isinstance(app, str) and (app in CU_OPEN_APPS or _APP_NAME.fullmatch(app)):
        out["app"] = app
    out["why"] = {"chars": len(why)} if isinstance(why, str) else None
    return out


def _act(name: str, arguments: Mapping[str, Any], dek: bytes, act: "ActResolution | None") -> dict[str, Any]:
    """Only known fields: a point, a listed key, the expect's length, and for typing a keyed hash of the text."""
    out: dict[str, Any] = {key: arguments[key] for key in ("x", "y") if isinstance(arguments.get(key), int)}
    if name == "press_key" and arguments.get("key") in CU_KEYS:
        out["key"] = arguments["key"]
    if "expect" in arguments:
        out["expect"] = {"chars": _chars(arguments["expect"])}
    text = arguments.get("text")
    if name == "type" and isinstance(text, str):
        out["source"] = _source(arguments.get("source"))
        out["length"] = len(text)
        out["sha256"] = hmac.new(dek, text.encode(), hashlib.sha256).hexdigest()
    return {**out, **_resolution_facts(act)}


def redact_for_audit(name: str, arguments: Mapping[str, Any], dek: bytes,
                     act: "ActResolution | None" = None) -> dict[str, Any]:
    if name in CU_ACT_TOOLS:
        return _act(name, arguments, dek, act)
    if name == "open_app":
        return _open_app(arguments)
    if name.startswith("mac_"):
        return _mac(name, arguments, dek)
    if name in TOOL_TOPICS:
        return _record(arguments)
    return dict(arguments)
