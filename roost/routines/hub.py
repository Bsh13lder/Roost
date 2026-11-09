"""``RoutinesHub``: every routine of every one of the user's bots, in one place.

Reads go across bots (each still scoped by ``user_id``); the one write, adding a template to a bot, goes through
``RoutineService.create`` like any routine the user makes, so its caps, checks and quiet chat line all apply."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from roost.bots.store import BotStore
from roost.constants import ROUTINE_OCCURRENCES_MAX
from roost.routines.models import Clock, Routine, RoutineRun
from roost.routines.occurrences import OccurrencePage, madrid_span, occurrences_between
from roost.routines.runs import RoutineRunStore, utc_now
from roost.routines.service import NoSuchBot, Refused, RoutineService, RoutineView
from roost.routines.store import RoutineStore
from roost.routines.templates import template_by_id

NO_SUCH_TEMPLATE = "There's no such template."


@dataclass(frozen=True)
class HubRoutine:
    view: RoutineView
    bot_name: str
    last_run: RoutineRun | None


@dataclass(frozen=True)
class HubRun:
    run: RoutineRun
    routine_name: str
    bot_name: str


class RoutinesHub:
    def __init__(self, service: RoutineService, routines: RoutineStore, runs: RoutineRunStore, bots: BotStore,
                 *, clock: Clock = utc_now) -> None:
        self._service = service
        self._routines = routines
        self._runs = runs
        self._bots = bots
        self._clock = clock

    async def list_all(self, user_id: str) -> tuple[HubRoutine, ...]:
        names = await self._bot_names(user_id)
        found: list[HubRoutine] = []
        for routine in await self._routines.list_for_user(user_id):
            latest = await self._runs.list_for_routine(user_id, routine.id, 1)
            found.append(HubRoutine(view=await self._service.view(user_id, routine),
                                    bot_name=names.get(routine.bot_id, ""), last_run=latest[0] if latest else None))
        return tuple(found)

    async def recent_runs(self, user_id: str, limit: int) -> tuple[HubRun, ...]:
        names = await self._bot_names(user_id)
        routines = {r.id: r for r in await self._routines.list_for_user(user_id)}
        return tuple(
            HubRun(run=run, routine_name=_name(routines.get(run.routine_id)), bot_name=names.get(run.bot_id, ""))
            for run in await self._runs.list_recent_for_user(user_id, limit))

    async def occurrences(self, user_id: str, first: date, last: date, *, bot_id: str | None = None,
                          cap: int = ROUTINE_OCCURRENCES_MAX) -> OccurrencePage:
        """The upcoming run times of the user's enabled routines on the local days ``first``..``last`` (from now on),
        only ``bot_id``'s when given. ``NoSuchBot`` when ``bot_id`` is not one of the user's bots."""
        names = await self._bot_names(user_id)
        if bot_id is not None and bot_id not in names:
            raise NoSuchBot(bot_id)
        start, end = madrid_span(first, last)
        routines = await self._routines.list_for_user(user_id)
        mine = tuple(r for r in routines if bot_id is None or r.bot_id == bot_id)
        return occurrences_between(mine, names, max(start, self._clock()), end, cap=cap)

    async def add_template(self, user_id: str, bot_id: str, template_id: str) -> Routine:
        """Create the template's routine on ``bot_id`` as the user's own, paused when it ``needs_edit``.
        ``Refused`` for an unknown template."""
        template = template_by_id(template_id)
        if template is None:
            raise Refused(NO_SUCH_TEMPLATE)
        return await self._service.create(user_id, bot_id, template.name, template.instructions, template.schedule,
                                         enabled=not template.needs_edit)

    async def _bot_names(self, user_id: str) -> dict[str, str]:
        return {bot.id: bot.name for bot in await self._bots.list(user_id)}


def _name(routine: Routine | None) -> str:
    return routine.name if routine is not None else ""
