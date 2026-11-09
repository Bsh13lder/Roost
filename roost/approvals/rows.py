"""``with_rows``: the card shows EVERY stored argument, and the stored call holds only what is shown.

A record tool's arguments are cut to the keys its spec names (unknown keys are dropped from the STORED call, so
what the card shows is what Yes runs), then each one becomes a labelled row in a fixed order: money amounts and
the income flag first, then the spec's own order. A Mac step keeps its ids, hashes and new text (the diff shows
that) out of the rows. A step whose arguments cannot all be rendered gets no card (``None``)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Mapping

from roost.approvals.models import ArgRow, PendingCall
from roost.computer_use.models import resolution_from_json
from roost.constants import APPROVAL_ROW_MAX_DEPTH
from roost.talk.tool_catalog import CATALOG

_FIRST = ("amount", "income")
_LABELS: Mapping[str, str] = {
    "income": "Kind", "spent_at": "Day", "new_path": "New path", "base_hash": "File hash", "ids": "Ids",
}
_INCOME = "Income (money in)"
_EXPENSE = "Expense (money out)"
# Mac steps store resolved fields next to the user-visible ones; these are shown by the diff, or are internal ids.
_MAC_SHOWN = ("folder", "path", "new_path", "query", "text")
_MAC_HIDDEN = frozenset({"grant_id", "grant_ids", "base_sha256", "new_text", "plus", "minus", "tainted_basis"})
_SCALARS = (str, int, float, bool, type(None))
# A connector step (design §4): what is sent is shown; the connector's id is kept hidden, like a grant id.
_CONNECTOR_SHOWN: Mapping[str, str] = {
    "connector": "Connector", "method": "Method", "path": "Path", "query": "Query", "json": "Body",
}
_CONNECTOR_HIDDEN = frozenset({"connector_id"})


def _label(key: str) -> str:
    return _LABELS.get(key) or key.replace("_", " ").capitalize()


def _depth_ok(value: Any, depth: int = 0) -> bool:
    if depth > APPROVAL_ROW_MAX_DEPTH:
        return False
    if isinstance(value, Mapping):
        return all(isinstance(k, str) and _depth_ok(v, depth + 1) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_depth_ok(v, depth + 1) for v in value)
    return isinstance(value, _SCALARS)


def _text(key: str, value: Any) -> str:
    if key == "income":
        return _INCOME if value is True else _EXPENSE
    if value is None:
        return "(empty)"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _spec_keys(name: str) -> tuple[str, ...] | None:
    tool = CATALOG.get(name)
    if tool is None:
        return None
    return tuple(tool.spec.input_schema.get("properties", {}))


def _ordered(keys: tuple[str, ...]) -> tuple[str, ...]:
    return (*[k for k in _FIRST if k in keys], *[k for k in keys if k not in _FIRST])


def _mac_rows(arguments: Mapping[str, Any]) -> tuple[ArgRow, ...] | None:
    if not set(arguments) <= set(_MAC_SHOWN) | _MAC_HIDDEN:
        return None
    return tuple(ArgRow(k, _label(k), _text(k, arguments[k])) for k in _MAC_SHOWN
                 if k in arguments and arguments[k] not in (None, ""))


def _connector_rows(arguments: Mapping[str, Any]) -> tuple[ArgRow, ...] | None:
    if not set(arguments) <= set(_CONNECTOR_SHOWN) | _CONNECTOR_HIDDEN:
        return None
    return tuple(ArgRow(k, label, _text(k, arguments[k])) for k, label in _CONNECTOR_SHOWN.items() if k in arguments)


# Vault: passwords (owner, 2026-11-08): the site and the user name Yes types; the box and the login id are hidden.
_VAULT_SHOWN: Mapping[str, str] = {"site": "Site", "username": "User name"}
_VAULT_HIDDEN = frozenset({"index", "expect", "login_id"})


def _vault_rows(arguments: Mapping[str, Any]) -> tuple[ArgRow, ...] | None:
    if not set(arguments) <= set(_VAULT_SHOWN) | _VAULT_HIDDEN or not set(_VAULT_SHOWN) <= set(arguments):
        return None
    return tuple(ArgRow(k, label, str(arguments[k])) for k, label in _VAULT_SHOWN.items())


# C3: what a click or key does, in the card's words (design §6.5: "Sends something").
_ACT_DOES: Mapping[str, str] = {
    "spend": "Buys or pays for something", "send": "Sends something", "submit": "Submits something",
    "accept": "Accepts or agrees to something", "delete": "Deletes something", "account": "Changes your account",
    "unknown": "I can't tell what it does, so I ask", "browsing": "Moves around the site",
    "consent": "Answers a cookie notice",
}
_NEW_SITE_DOES = "Goes to another site: {host}"
_NO_WORDS = "(no words on it)"
DRAFT_ROW_KEY = "draft"            # 2026-10-27 / 2026-11-03: what a Send sends, one row per box, named by its label
WHY_ROW_KEY = "why"
WHY_ROW_LABEL = "Why you see this"
OWN_TEXT_WHY = "I wrote this text myself, so you see it before it goes, even when you said send."


def _draft_rows(step: PendingCall) -> list[ArgRow]:
    """Every box the Send would send, in typing order, and why the card shows them when the text is the bot's."""
    rows = [ArgRow(DRAFT_ROW_KEY if n == 0 else f"{DRAFT_ROW_KEY}_{n + 1}", box.label, box.text)
            for n, box in enumerate(step.drafts)]
    if step.floor == "commit_click" and any(not box.yours for box in step.drafts):
        rows.append(ArgRow(WHY_ROW_KEY, WHY_ROW_LABEL, OWN_TEXT_WHY))
    return rows


def _act_rows(step: PendingCall, kept: Mapping[str, Any]) -> tuple[ArgRow, ...] | None:
    """A click, typing or key press: the site, the control's words read as text (R5), the typed text in full,
    the message a Send would send (as its box holds it), what it does and what the bot expected. ``None`` when the stored resolution is not valid."""
    try:
        r = resolution_from_json(step.act or {})
    except ValueError:
        return None
    words = " ".join((r.target.visible_text or r.target.text).split()) if r.target is not None else ""
    does = _NEW_SITE_DOES.format(host=r.nav_host) if step.floor == "new_site" else _ACT_DOES[r.commit]
    rows = [ArgRow("site", "Site", r.host or "(no site)")]
    if step.tool == "type":
        rows += [ArgRow("field", "Field", words or _NO_WORDS), ArgRow("text", "Text", str(kept.get("text", "")))]
    elif step.tool == "press_key":
        rows += [ArgRow("key", "Key", str(kept.get("key", ""))), ArgRow("field", "On", words or _NO_WORDS)]
    else:
        rows.append(ArgRow("button", "Button text", words or _NO_WORDS))
    rows += _draft_rows(step)
    rows += [ArgRow("does", "What it does", does), ArgRow("expect", "You expected", str(kept.get("expect", "")))]
    return tuple(rows)


def with_rows(step: PendingCall) -> PendingCall | None:
    """``step`` with its rows (and, for a record tool, only its known arguments), or ``None`` when it can't be shown."""
    if not _depth_ok(dict(step.arguments)):
        return None
    if step.tool == "use_connector":
        rows = _connector_rows(step.arguments)
        return None if rows is None else replace(step, rows=rows)
    if step.tool == "use_vault_password":
        rows = _vault_rows(step.arguments)
        return None if rows is None else replace(step, rows=rows)
    if step.tool.startswith("mac_"):
        rows = _mac_rows(step.arguments)
        return None if rows is None else replace(step, rows=rows)
    spec_keys = _spec_keys(step.tool)
    if spec_keys is None:
        return None
    kept = {k: step.arguments[k] for k in spec_keys if k in step.arguments}
    if step.act is not None:
        act_rows = _act_rows(step, kept)
        return None if act_rows is None else replace(step, arguments=kept, rows=act_rows)
    keys = _ordered(tuple(kept))
    if "income" in spec_keys and "amount" in spec_keys and "income" not in kept:
        kept = {**kept, "income": False}      # the default is shown, never left to guess
        keys = _ordered(tuple(kept))
    rows = tuple(ArgRow(k, _label(k), _text(k, kept[k])) for k in keys)
    return replace(step, arguments={k: kept[k] for k in keys}, rows=rows)
