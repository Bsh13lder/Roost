"""The ``mac_activity`` line a Mac write leaves in the chat: what changed, and how to undo it.

The body is JSON ``{op, label, path, new_path?, plus, minus, tainted_basis, undo}``. ``undo`` is the keeper's
undo body without ``bot_id`` (plus the grant), or ``null`` for a line with nothing to undo. The line names the
file, never its contents."""

from __future__ import annotations

import json
from typing import Any, Mapping

from roost.approvals.texts import OUTSIDE_CONTENT_MARK
from roost.events.hub import EventHub
from roost.mac.wrap import clean_name
from roost.talk.store import Message, TalkStore, message_out


def activity_body(op: str, label: str, path: str, *, new_path: str | None = None, plus: int = 0, minus: int = 0,
                  tainted_basis: bool = False, undo: Mapping[str, Any] | None = None,
                  undid: str | None = None) -> str:
    data: dict[str, Any] = {"op": op, "label": label, "path": path, "plus": plus, "minus": minus,
                            "tainted_basis": tainted_basis, "undo": None if undo is None else dict(undo)}
    if new_path is not None:
        data["new_path"] = new_path
    if undid is not None:
        data["undid"] = undid
    return json.dumps(data)


def _name(path: str) -> str:
    return clean_name(path.rstrip("/").rsplit("/", 1)[-1])


def activity_line(body: str) -> str:
    """The sentence for a stored activity body ("Edited Tasks.md · MySpace (+2 −1)"), without the Undo button."""
    try:
        data = json.loads(body)
        op, label, name = data["op"], clean_name(str(data["label"])), _name(str(data["path"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        return "Changed a file"
    mark = f" · {OUTSIDE_CONTENT_MARK}" if data.get("tainted_basis") else ""
    if op == "create":
        return f"Created {name} · {label}{mark}"
    if op == "edit":
        return f"Edited {name} · {label} (+{data.get('plus', 0)} −{data.get('minus', 0)}){mark}"
    if op == "rename":
        return f"Renamed {name} → {_name(str(data.get('new_path', '')))} · {label}{mark}"
    if op == "trash":
        return f"Moved {name} to the trash · {label}{mark}"
    undid = data.get("undid")
    if undid == "trash":
        return f"Moved {name} back from the trash · {label}"
    word = {"edit": "the edit of", "create": "the creation of", "rename": "the rename of"}.get(undid, "the change to")
    return f"Undid {word} {name} · {label}"


async def post_mac_activity(talk: TalkStore, events: EventHub, user_id: str, thread_id: str, bot_id: str,
                            body: str) -> Message:
    """Store the line (role ``activity``) and publish it. It is never replayed to a model."""
    message = await talk.add_message(user_id, thread_id, role="activity", body=body, kind="mac_activity",
                                     author_bot_id=bot_id)
    await events.publish(user_id, {"type": "message", "thread_id": thread_id, "message": message_out(message)})
    return message
