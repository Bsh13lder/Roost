"""The computer card's steps (docs/plans/2026-10-23-roost-computer-card.md).

After each screen tool in a live run the runner publishes one ``computer_step`` frame: the step's number in the
run, its kind, the same words as the chat's activity line (never typed text: a line says only how many characters)
and the page's host name alone (no path, no query; ``None`` on the desktop or another app). The frames are
live only (``LIVE_ONLY_TYPES``): never stored. ``ComputerSteps`` is an ``EventHub`` listener that keeps each bot's
current run's newest steps in memory, so a page opened mid-run gets them in its ``snapshot``; a bot that stops
being On it moves them to its kept runs (the newest finished run per chat, ``COMPUTER_KEPT_RUNS_PER_BOT`` at most),
so a restarted phone still shows the kept card (``computer_kept``). No picture is ever part of a step."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from roost.constants import COMPUTER_KEPT_RUNS_PER_BOT, COMPUTER_STEP_LINE_MAX, COMPUTER_STEPS_KEPT

COMPUTER_STEP_TYPE = "computer_step"
_ON_IT = "on_it"
STEP_KINDS: Mapping[str, str] = MappingProxyType({
    "look": "look", "wait_ready": "wait", "scroll": "scroll", "click": "click", "type": "type",
    "press_key": "key", "open_app": "open_app", "open_page": "open_page",
    "list_tabs": "tab", "switch_tab": "tab", "close_tab": "tab",
})
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")
_WEB_SCHEMES = frozenset({"http", "https"})


def step_host(url: str) -> str | None:
    """The URL's host name, lowercased, or None when it is not a web page (``about:blank``, ``chrome://``)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in _WEB_SCHEMES or not host or not _HOST.fullmatch(host):
        return None
    return host


def step_frame(*, bot_id: str, thread_id: str | None, run_id: str, step: int, tool: str, line: str,
               host: str | None) -> dict[str, Any]:
    """One ``computer_step`` frame, exactly the contract's keys."""
    return {
        "type": COMPUTER_STEP_TYPE, "bot_id": bot_id, "thread_id": thread_id, "run_id": run_id, "step": step,
        "kind": STEP_KINDS.get(tool, "look"), "line": " ".join(line.split())[:COMPUTER_STEP_LINE_MAX],
        "host": host, "at": datetime.now(timezone.utc).isoformat(),
    }


Ring = tuple[dict[str, Any], ...]
_Key = tuple[str, str]


class ComputerSteps:
    """Each bot's current run's newest steps and its kept finished runs, keyed by (user id, bot id), in memory."""

    def __init__(self) -> None:
        self._rings: Mapping[_Key, Ring] = MappingProxyType({})
        self._kept: Mapping[_Key, tuple[Ring, ...]] = MappingProxyType({})

    def listen(self, user_id: str, frame: dict[str, Any]) -> None:
        """An ``EventHub`` listener: keep a step; a run that ends (the bot no longer On it, or a new run) is kept."""
        kind, bot_id = frame.get("type"), frame.get("bot_id")
        if not isinstance(bot_id, str):
            return
        key = (user_id, bot_id)
        if kind == COMPUTER_STEP_TYPE:
            ring = self._rings.get(key, ())
            if ring and ring[-1].get("run_id") != frame.get("run_id"):
                self._keep(key, ring)
                ring = ()
            kept = {name: value for name, value in frame.items() if name != "seq"}
            self._set(key, (*ring, kept)[-COMPUTER_STEPS_KEPT:])
        elif kind == "bot_status" and frame.get("status") != _ON_IT and key in self._rings:
            self._keep(key, self._rings[key])
            self._set(key, None)
        elif kind == "bot_removed":
            self._set(key, None)
            self._kept = MappingProxyType({name: runs for name, runs in self._kept.items() if name != key})

    def _set(self, key: _Key, ring: Ring | None) -> None:
        rings = {name: value for name, value in self._rings.items() if name != key}
        if ring:
            rings[key] = ring
        self._rings = MappingProxyType(rings)

    def _keep(self, key: _Key, ring: Ring) -> None:
        """The finished run becomes its chat's kept run, replacing an older one there; the oldest chat goes first."""
        thread = ring[-1].get("thread_id")
        others = tuple(run for run in self._kept.get(key, ()) if run[-1].get("thread_id") != thread)
        runs = (*others, ring)[-COMPUTER_KEPT_RUNS_PER_BOT:]
        self._kept = MappingProxyType({**{name: v for name, v in self._kept.items() if name != key}, key: runs})

    def for_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """The snapshot's ``computer_steps``: bot id -> its current run's steps, oldest first."""
        return {bot: [dict(f) for f in ring] for (user, bot), ring in self._rings.items() if user == user_id}

    def kept_for_user(self, user_id: str) -> dict[str, list[list[dict[str, Any]]]]:
        """The snapshot's ``computer_kept``: bot id -> its finished runs (each its steps), oldest run first."""
        return {bot: [[dict(f) for f in run] for run in runs]
                for (user, bot), runs in self._kept.items() if user == user_id}
