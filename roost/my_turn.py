"""My turn's rows: what waits on the owner, in the web's words and order (``web/src/lib/myTurn.ts`` and
``myTurnLine`` in ``web/src/lib/stuck.ts``), so the phone and the web show the same lines.

The order is routine proposals, skill proposals, Add a key requests, questions, then Stuck cards newest first. Only
items of bots still on the team get a row. Every input is already the signed-in user's own (each list is read with
their ``user_id``); this module only words them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from roost.stuck.models import StuckCard

SEP = " · "
NEEDS_HELP = "Needs your help"
STUCK_ON = "Stuck on {host}"
SIGN_IN_LINE = "{name} needs you to sign in to {host}"
ADD_A_KEY = "Add a key"
ROUTINE_WORDS = {"create": "New routine", "change": "Change routine", "pause": "Pause routine"}
SKILL_WORDS = {"create": "New skill", "change": "Change skill"}
INFO_PANEL = "info"
_WEB_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class MyTurnLists:
    """Each list in its own route's JSON shape (``GET /api/stuck``, ``/api/routine-proposals``, ...)."""
    stuck: Sequence[StuckCard]
    routine_proposals: Sequence[Mapping[str, Any]]
    skill_proposals: Sequence[Mapping[str, Any]]
    key_requests: Sequence[Mapping[str, Any]]
    questions: Sequence[Mapping[str, Any]]


def _is_web(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in _WEB_SCHEMES and bool(parts.hostname)


def stuck_line(bot_name: str, card: StuckCard) -> str:
    """A Sign-in card asks you to sign in; any other says where it is stuck, or that it needs your help."""
    web = bool(card.host) and _is_web(card.url)
    if card.sign_in and web:
        return SIGN_IN_LINE.format(name=bot_name, host=card.host)
    title = STUCK_ON.format(host=card.host) if web else NEEDS_HELP
    return f"{bot_name}{SEP}{title}"


def _joined(*parts: str | None) -> str:
    """The words joined with " · ", a missing last word left out (the web's ``.replace(/ · $/, "")``)."""
    return SEP.join(part or "" for part in parts).removesuffix(SEP)


def _row(kind: str, item: Mapping[str, Any], text: str, *, panel: str | None = None,
         thread_id: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "id": item["id"], "bot_id": item["bot_id"], "thread_id": thread_id, "panel": panel,
            "text": text, "created_at": item["created_at"]}


def _ask_rows(lists: MyTurnLists, names: Mapping[str, str]) -> list[dict[str, Any]]:
    def on_team(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [item for item in items if item["bot_id"] in names]

    routines = [_row("routine_proposal", p, _joined(
        names[p["bot_id"]], ROUTINE_WORDS.get(p["action"], ""),
        (p.get("payload") or {}).get("name") or p.get("routine_name")))
        for p in on_team(lists.routine_proposals)]
    skills = [_row("skill_proposal", p, _joined(
        names[p["bot_id"]], SKILL_WORDS.get(p["action"], ""),
        p["payload"]["name"] if p["action"] == "create" else p.get("skill_name")))
        for p in on_team(lists.skill_proposals)]
    keys = [_row("key_request", r, _joined(names[r["bot_id"]], ADD_A_KEY, r["service"]), thread_id=r["thread_id"])
            for r in on_team(lists.key_requests)]
    questions = [_row("question", q, _joined(names[q["bot_id"]], q["question"]), panel=INFO_PANEL)
                 for q in on_team(lists.questions)]
    return [*routines, *skills, *keys, *questions]


def _stuck_rows(cards: Sequence[StuckCard], names: Mapping[str, str]) -> list[dict[str, Any]]:
    newest_first = sorted((card for card in cards if card.bot_id in names), key=lambda c: c.created_at, reverse=True)
    return [{"kind": "stuck", "id": card.id, "bot_id": card.bot_id, "thread_id": card.thread_id, "panel": None,
             "text": stuck_line(names[card.bot_id], card), "created_at": card.created_at} for card in newest_first]


def my_turn_rows(lists: MyTurnLists, names: Mapping[str, str]) -> list[dict[str, Any]]:
    """``names`` maps each bot still on the team to its name."""
    return [*_ask_rows(lists, names), *_stuck_rows(lists.stuck, names)]
