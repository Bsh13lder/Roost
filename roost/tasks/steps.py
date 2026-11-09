# SPDX-License-Identifier: MIT
# Harvested from LazyClaw lazyclaw/tasks/store.py lines 313-492 @ 21e1002, adapted for Roost

"""A task's checklist (M1 D6): harvested normalizer and completion cascade,
plus Roost's typed ``Step`` round-trip to and from the stored JSON."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import uuid4

from roost.constants import CURRENCY_PATTERN, MAX_STEP_TITLE_LENGTH, MAX_TASK_STEPS
from roost.money.amounts import amount_text, parse_amount
from roost.tasks.models import STEP_NOT_FOUND_TEXT, Step

logger = logging.getLogger(__name__)


def _step_timestamp(value: object) -> str | None:
    """Coerce a sub-task timestamp onto a canonical ISO string, or None.

    Deliberately TOLERANT, unlike ``_validate_iso_dt`` which raises. That gate
    guards ``reminder_at``, where a bad value silently stops the heartbeat from
    firing and is worth a loud 400. A sub-task timestamp is decoration: it is
    read by the UI and nothing schedules off it. ``_normalize_steps`` sits on
    EVERY steps write path, so raising here would turn one malformed field
    inside one checklist item — an epoch int from an older mobile build, a
    half-migrated row, a hand-written agent payload — into a 500 that loses the
    user's whole task edit. Junk therefore degrades to "absent" and the caller
    re-stamps.

    ``''`` is how form-bound clients spell "unset", so it maps to absent too.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        datetime.fromisoformat(trimmed)
    except (ValueError, TypeError):
        return None
    return trimmed


def normalize_steps(steps: list[dict] | None) -> list[dict]:
    """Coerce a steps payload into the canonical shape.

    Canonical sub-task::

        {id, title, done, created_at, completed_at?}

    Accepts loose input (plain strings, partial dicts) so callers — including
    the NL parser and the AI quick-add — don't need to pre-shape everything.

    Timestamps use ``datetime.now(timezone.utc).isoformat()`` — the SAME shape
    a task's own ``created_at`` carries (see ``create_task``), so sub-task times
    sort and render alongside task times instead of needing a second parser.

    Two rules make the timestamps trustworthy no matter which client wrote the
    row (Flutter, web, an agent skill, an offline-sync replay):

    * ``created_at`` is stamped ONLY when this call is MINTING the step — i.e.
      the payload arrived with no ``id``. Steps are born server-side too (the
      NL parser and the AI quick-add build them as bare ``{"title": ...}``, the
      recurring respawn rebuilds the checklist from titles alone), and those
      must not be permanently blank. But an incoming ``id`` means the step
      already existed somewhere, and this function never observed its creation.

      Stamping those too was a real bug: every steps write re-normalises the
      WHOLE list, so ticking one item in a checklist created last year came
      back with every untouched sibling claiming it was created today. The
      Flutter side deliberately refuses to invent creation times for legacy
      rows (see ``subtask.dart``); backfilling here erased that honesty one hop
      later. A legacy step keeps NO ``created_at``, and the UI renders nothing
      rather than a date we made up.

    * ``completed_at`` is PRESERVED when a step is ticked and CLEARED when it
      is un-ticked, but never derived. This function is stateless — it cannot
      tell "ticked by this very write" from "ticked months ago by a client that
      sent no timestamp", and guessing ``now`` for the second case dates old
      work to today just as wrongly. The callers that genuinely observe the
      transition stamp it themselves: ``toggle_step`` and
      ``_cascade_complete_steps`` server-side, ``subtask_editor.dart`` on
      mobile.

    Omitted-when-null keeps the wire lean: an unfinished item has no
    ``completed_at`` key at all, so no client has to special-case a ``null``.
    """
    if not steps:
        return []
    now = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for i, raw in enumerate(steps):
        if isinstance(raw, str):
            title = raw.strip()
            if not title:
                continue
            out.append({
                "id": f"s{i}-{uuid4().hex[:6]}",
                "title": title,
                "done": False,
                "created_at": now,
            })
            continue
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", "")).strip()
        if not title:
            continue
        done = bool(raw.get("done", False))
        incoming_id = str(raw.get("id") or "").strip()
        step = {
            "id": incoming_id or f"s{i}-{uuid4().hex[:6]}",
            "title": title,
            "done": done,
        }
        # Minting (no incoming id) is the only case where we actually witness
        # the creation, so it is the only case that may stamp one.
        created_at = _step_timestamp(raw.get("created_at"))
        if created_at is None and not incoming_id:
            created_at = now
        if created_at is not None:
            step["created_at"] = created_at

        if done:
            # Preserved verbatim, never re-derived — see the docstring. A
            # ticked step that arrives without one stays without one; the
            # caller that saw the tick is responsible for stamping it.
            completed_at = _step_timestamp(raw.get("completed_at"))
            if completed_at is None and not incoming_id:
                completed_at = now
            if completed_at is not None:
                step["completed_at"] = completed_at
        # ...and an un-ticked step gets NO completed_at, so re-opening an item
        # drops the stale time instead of showing "completed 3 days ago" beside
        # an empty checkbox.

        # Preserve the parent-completion cascade marker. Every steps write is
        # funnelled through this normaliser, so dropping the key here would
        # evaporate the "which steps did the user actually finish" record on the
        # next unrelated edit and make the tag decorative. Only carried when
        # true, so an ordinary checklist keeps its lean shape.
        if raw.get("cascaded"):
            step["cascaded"] = True
        step.update(_kept_budget(raw))
        out.append(step)
    return out


def _kept_budget(raw: dict) -> dict:
    """A step's budget and its currency, carried only when both read cleanly (owner, 2026-10-26): an
    amount string by ``parse_amount``'s rules and a three-letter code. Anything else is dropped, so a
    damaged budget reads as none instead of failing the whole checklist."""
    amount, currency = raw.get("budget"), raw.get("budget_currency")
    if not isinstance(amount, str) or not isinstance(currency, str) or not re.fullmatch(CURRENCY_PATTERN, currency):
        return {}
    try:
        return {"budget": amount_text(parse_amount(amount)), "budget_currency": currency}
    except ValueError:
        return {}


def cascade_complete_steps(steps: list[dict]) -> list[dict]:
    """Tick every unfinished step for a parent-task completion.

    Returns a NEW list; the input dicts are never mutated (``complete_task``
    keeps using the decoded task afterwards for the LazyBrain mirror and the
    recurring respawn).

    Steps the user genuinely ticked pass through untouched — same ``done``,
    same ``completed_at``, no ``cascaded`` tag — so a later reopen can un-tick
    exactly the auto-ticked ones and never erase real work.

    The ``completed_at`` is stamped HERE rather than left to
    ``_normalize_steps``, because this is the only place that actually observes
    the transition. The normaliser is stateless and deliberately never derives
    a completion time (it cannot tell a fresh tick from a legacy one), so an
    unstamped cascade would leave these items permanently without a completion
    time.
    """
    now = datetime.now(timezone.utc).isoformat()
    return normalize_steps([
        step
        if step.get("done")
        else {**step, "done": True, "cascaded": True, "completed_at": now}
        for step in steps
    ])


def decode_steps(raw: str | list | None) -> list[dict]:
    """Decode a task's ``steps`` value into a list of step dicts.

    ``steps`` is an ENCRYPTED field, so a row read back through
    ``_row_to_dict`` hands us the decrypted JSON *string*. Callers used to
    ``json.loads`` it inline and each one re-invented the failure handling; a
    malformed blob must degrade to "no checklist", never raise and take the
    whole completion down with it. Tolerates an already-parsed list so both
    read paths can share this.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse steps JSON; treating as empty checklist")
        return []
    if not isinstance(parsed, list):
        return []
    return [s for s in parsed if isinstance(s, dict)]


def _to_step(raw: dict[str, Any]) -> Step:
    return Step(
        id=str(raw["id"]), title=str(raw["title"]), done=bool(raw.get("done")),
        created_at=raw.get("created_at"), completed_at=raw.get("completed_at"), cascaded=bool(raw.get("cascaded")),
        budget=Decimal(raw["budget"]) if raw.get("budget") else None, budget_currency=raw.get("budget_currency"),
    )


def _to_dict(step: Step) -> dict[str, Any]:
    """LazyClaw's stored shape: optional keys only when set."""
    out: dict[str, Any] = {"id": step.id, "title": step.title, "done": step.done}
    if step.created_at:
        out["created_at"] = step.created_at
    if step.completed_at:
        out["completed_at"] = step.completed_at
    if step.cascaded:
        out["cascaded"] = True
    if step.budget is not None and step.budget_currency:
        out["budget"] = amount_text(step.budget)
        out["budget_currency"] = step.budget_currency
    return out


def steps_from_titles(titles: Sequence[str]) -> tuple[Step, ...]:
    return tuple(_to_step(raw) for raw in normalize_steps(list(titles)))


def steps_to_json(steps: Sequence[Step]) -> str:
    return json.dumps([_to_dict(step) for step in steps])


def steps_from_json(raw: str | None) -> tuple[Step, ...]:
    return tuple(_to_step(item) for item in normalize_steps(decode_steps(raw)))


def cascade_steps(steps: Sequence[Step]) -> tuple[Step, ...]:
    return tuple(_to_step(item) for item in cascade_complete_steps([_to_dict(step) for step in steps]))


def uncascade_steps(steps: Sequence[Step]) -> tuple[Step, ...]:
    """Reopen a closed task: steps that closing ticked for the user are open again; steps the user ticked stay."""
    return tuple(replace(step, done=False, cascaded=False, completed_at=None) if step.cascaded else step
                 for step in steps)


# ---------------------------------------------------------------------------
# Roost (redesign P3): one change to a checklist, as a pure function from the
# steps to the new steps. Ids are stable: a new step gets a fresh one, and a
# rename, a tick or a move keeps it, so an expense or a comment filed under a
# step stays with it. Each raises ``StepNotFound`` for an id the task doesn't
# have, or ``ValueError`` with a plain sentence for a change it refuses.
# ---------------------------------------------------------------------------

STEP_TITLE_TEXT = "A step needs a title."
LONG_STEP_TEXT = f"A step's title holds at most {MAX_STEP_TITLE_LENGTH} characters."
TOO_MANY_STEPS_TEXT = f"A task holds at most {MAX_TASK_STEPS} steps."


class StepNotFound(LookupError):
    """The task has no step with that id (a 404 over HTTP)."""


def step_title(text: str | None) -> str:
    title = (text or "").strip()
    if not title:
        raise ValueError(STEP_TITLE_TEXT)
    if len(title) > MAX_STEP_TITLE_LENGTH:
        raise ValueError(LONG_STEP_TEXT)
    return title


def _index(steps: Sequence[Step], step_id: str) -> int:
    for index, step in enumerate(steps):
        if step.id == step_id:
            return index
    raise StepNotFound(STEP_NOT_FOUND_TEXT)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def with_step_added(steps: Sequence[Step], title: str) -> tuple[Step, ...]:
    """``steps`` plus a new open step at the end."""
    if len(steps) >= MAX_TASK_STEPS:
        raise ValueError(TOO_MANY_STEPS_TEXT)
    added = Step(id=f"s-{uuid4().hex[:12]}", title=step_title(title), done=False, created_at=_now_iso())
    return (*steps, added)


def with_step_renamed(steps: Sequence[Step], step_id: str, title: str) -> tuple[Step, ...]:
    index = _index(steps, step_id)
    renamed = replace(steps[index], title=step_title(title))
    return (*steps[:index], renamed, *steps[index + 1:])


def with_step_done(steps: Sequence[Step], step_id: str, done: bool) -> tuple[Step, ...]:
    """Tick or untick. A tick is stamped now; an untick drops the stamp and the cascade mark."""
    index = _index(steps, step_id)
    current = steps[index]
    if current.done == done:
        return tuple(steps)
    changed = replace(current, done=done, completed_at=_now_iso() if done else None, cascaded=False)
    return (*steps[:index], changed, *steps[index + 1:])


def with_step_moved(steps: Sequence[Step], step_id: str, position: int) -> tuple[Step, ...]:
    """The step at ``position`` (0 is first), the others in their order. A position past either
    end puts it at that end."""
    index = _index(steps, step_id)
    rest = (*steps[:index], *steps[index + 1:])
    target = min(max(position, 0), len(rest))
    return (*rest[:target], steps[index], *rest[target:])


def without_step(steps: Sequence[Step], step_id: str) -> tuple[Step, ...]:
    index = _index(steps, step_id)
    return (*steps[:index], *steps[index + 1:])


def with_step_budget(steps: Sequence[Step], step_id: str, amount: Decimal | None,
                     currency: str) -> tuple[Step, ...]:
    """Set a step's budget in ``currency`` (the task's, owner 2026-10-26), or clear it with ``None``.
    The amount follows ``parse_amount``'s rules (``ValueError`` with its sentence)."""
    index = _index(steps, step_id)
    budget = None if amount is None else parse_amount(amount)
    changed = replace(steps[index], budget=budget, budget_currency=None if budget is None else currency)
    return (*steps[:index], changed, *steps[index + 1:])
