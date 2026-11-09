"""Routine templates: a short built-in list that only fills a new routine (name, instructions, local schedule).

A template is never a routine by itself. "Add to <bot>" creates one through ``RoutineService.create``, the same
path as ``POST /api/bots/{id}/routines``, made by the user. Days are 1 = Monday ... 7 = Sunday.

A template whose instructions hold a ``<placeholder>`` is ``needs_edit``: it is added paused, so it never runs (and
never starts a model run) until the user fills it in and switches it on."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

_EVERY_DAY = (1, 2, 3, 4, 5, 6, 7)
_WEEKDAYS = (1, 2, 3, 4, 5)


@dataclass(frozen=True)
class RoutineTemplate:
    id: str
    name: str
    instructions: str
    schedule: Mapping
    needs_edit: bool = False


def _times(days: tuple[int, ...], *times: str) -> Mapping:
    return MappingProxyType({"kind": "times", "days": list(days), "times": list(times)})


ROUTINE_TEMPLATES: tuple[RoutineTemplate, ...] = (
    RoutineTemplate(
        id="morning-brief", name="Morning brief",
        instructions=("Give me a short morning brief: my tasks due today and any that are overdue, what I planned "
                      "in my calendar notes, and one line on anything that needs my answer. Keep it under ten lines."),
        schedule=_times(_WEEKDAYS, "08:30")),
    RoutineTemplate(
        id="weekly-money", name="Weekly money summary",
        instructions=("Sum up my money for the past seven days: what I spent by project, any income, the projects "
                      "close to their budget, and the three biggest expenses. Plain numbers, no advice."),
        schedule=_times((7,), "19:00")),
    RoutineTemplate(
        id="inbox-tidy", name="Inbox tidy",
        instructions=("Look at my tasks with no project or no due date. Suggest a project and a day for each, as a "
                      "short list. Don't change anything yourself; I'll decide."),
        schedule=_times((1, 4), "09:00")),
    RoutineTemplate(
        id="daily-journal", name="Daily journal note",
        instructions=("Write today's journal note: what got done today (finished tasks and steps), what moved, "
                      "and what is still open for tomorrow. Save it as a note titled with today's date."),
        schedule=_times(_EVERY_DAY, "21:30")),
    RoutineTemplate(
        id="price-watch", name="Price watch for a page",
        instructions=("Open the page I name here: <paste the page address>. Find the price of the item I care "
                      "about and tell me if it changed since your last Report. Only report the price and the change."),
        schedule=_times(_EVERY_DAY, "10:00"), needs_edit=True),
)

_BY_ID: Mapping[str, RoutineTemplate] = MappingProxyType({t.id: t for t in ROUTINE_TEMPLATES})


def template_by_id(template_id: str) -> RoutineTemplate | None:
    return _BY_ID.get(template_id)
