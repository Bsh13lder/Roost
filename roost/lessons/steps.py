"""A run's own step lines for a lesson (docs/plans/2026-10-31-roost-lessons.md §1 L3).

``LessonSteps`` is an ``EventHub`` listener on the live ``run_step`` frames (``roost/talk/run_steps.py``). It keeps,
per run, each tool step's fixed words from ``plain_steps`` and its host, and whether it failed. A line that carries
a model-chosen argument (a search's query, a new task's title, a teammate's name, an app's label) is cut back to its
fixed words, so no typed or page-chosen text ever reaches the worker. Thinking and writing steps are left out."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from roost.lessons.constants import LESSON_SIGNAL_RUNS_KEPT, LESSON_STEP_LINES_MAX
from roost.talk.plain_steps import FALLBACK_LINE, FIXED_LINES
from roost.talk.run_steps import RUN_STEP_TYPE

_SKIPPED_KINDS = frozenset({"think", "message"})
_GENERIC = MappingProxyType({
    "search": "Searched the web", "read": "Opened a page", "program": "Ran a program", "tasks": "Added a task",
    "bots": "Asked a teammate", "computer": "Used the computer",
})
_FAILED = "failed"

Step = tuple[str, str, bool]      # (fixed words, host, failed)


def _words(kind: str, line: str, host: str) -> str:
    if line in FIXED_LINES:
        return line
    if host and line in (f"Opened {host}", f"Checked that {host} answers"):
        return line
    return _GENERIC.get(kind, FALLBACK_LINE)


def _as_line(step: Step) -> str:
    words, host, failed = step
    extras = [part for part in (host if host and host not in words else "", _FAILED if failed else "") if part]
    return " · ".join((words, *extras))


class LessonSteps:
    """Each run's step lines by run id, in memory, until the run's ``take``."""

    def __init__(self) -> None:
        self._runs: Mapping[str, Mapping[int, Step]] = MappingProxyType({})

    def listen(self, user_id: str, frame: dict[str, Any]) -> None:
        run_id, number, kind = frame.get("run_id"), frame.get("step"), frame.get("kind")
        if frame.get("type") != RUN_STEP_TYPE or not isinstance(run_id, str) or not isinstance(number, int):
            return
        if not isinstance(kind, str) or kind in _SKIPPED_KINDS:
            return
        host = frame.get("host") if isinstance(frame.get("host"), str) else ""
        step = (_words(kind, str(frame.get("line", "")), host), host, frame.get("state") == _FAILED)
        kept = self._runs.get(run_id, MappingProxyType({}))
        if number not in kept and len(kept) >= LESSON_STEP_LINES_MAX:
            return
        self._put(run_id, MappingProxyType({**kept, number: step}))

    def take(self, run_id: str) -> tuple[str, ...]:
        """This run's lines, oldest first, forgotten as they are handed over."""
        found = self._runs.get(run_id, {})
        self._runs = MappingProxyType({k: v for k, v in self._runs.items() if k != run_id})
        return tuple(_as_line(found[n]) for n in sorted(found))

    def _put(self, run_id: str, steps: Mapping[int, Step]) -> None:
        runs = {k: v for k, v in self._runs.items() if k != run_id}
        if len(runs) >= LESSON_SIGNAL_RUNS_KEPT:            # a run that never ended: the oldest is dropped
            runs = dict(list(runs.items())[1:])
        self._runs = MappingProxyType({**runs, run_id: steps})
