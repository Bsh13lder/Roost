"""``RecurringService`` — repeating expenses: the rules, the lazy catch-up and "Upcoming charges" (Task 12).

- ``catch_up`` runs whenever money is read (summary, a month's list, a task's expenses, a project's page); it is
  idempotent (``RecurringStore.catch_up``).
- ``start`` is the expense line's: the first charge is the typed day (the caller logs it, tied to the rule), so
  the rule's ``next_due`` is the occurrence after it. ``create`` is the repeating tab's: its first charge is its
  anchor day, made by the next catch-up.
- A rule of an archived project is paused and is not in the upcoming list."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from roost.constants import PROJECT_STATUSES, RECURRING_CADENCES, UPCOMING_CHARGES_DAYS
from roost.events.hub import EventHub
from roost.money.models import Project
from roost.money.months import today_madrid
from roost.money.project_store import ProjectStore
from roost.money.recurring import Recurring, UpcomingCharge, next_occurrence, occurrences
from roost.money.recurring_store import RecurringStore, _now_iso

CADENCE_TEXT = "A repeat is weekly, monthly or yearly."
ENDS_BEFORE_START_TEXT = "The last day can't be before the first charge."
_ARCHIVED = PROJECT_STATUSES[1]
_UPCOMING_LIMIT = 60                    # per rule: a weekly rule fits about 5 in 31 days; this is only a ceiling


def check_cadence(cadence: str) -> str:
    if cadence not in RECURRING_CADENCES:
        raise ValueError(CADENCE_TEXT)
    return cadence


class RecurringService:
    def __init__(self, store: RecurringStore, projects: ProjectStore, events: EventHub) -> None:
        self._store = store
        self._projects = projects
        self._events = events

    async def catch_up(self, user_id: str, today: date | None = None) -> tuple[str, ...]:
        """Make the missed charges (idempotent); one ``recurring_changed`` frame per rule that made some."""
        day = today or date.fromisoformat(today_madrid())
        made = await self._store.catch_up(user_id, day)
        for rule_id in made:
            await self._events.publish(user_id, {"type": "money_changed", "change": "recurring_changed", "id": rule_id})
        return made

    def _rule(self, user_id: str, project: Project, *, amount: Decimal, currency: str, note: str | None,
              vendor: str | None, cadence: str, anchor: date, next_due: date, ends_on: date | None,
              created_by_bot: str | None, tainted: bool) -> Recurring:
        if ends_on is not None and ends_on < anchor:
            raise ValueError(ENDS_BEFORE_START_TEXT)
        now = _now_iso()
        return Recurring(
            id=str(uuid4()), user_id=user_id, project_id=project.id, amount=amount, currency=currency,
            description=note, vendor=vendor, cadence=check_cadence(cadence), anchor_day=anchor.isoformat(),
            next_due=next_due.isoformat(), ends_on=None if ends_on is None else ends_on.isoformat(),
            created_at=now, updated_at=now, created_by_bot=created_by_bot, tainted=tainted)

    async def start(self, user_id: str, project: Project, *, amount: Decimal, currency: str, note: str | None,
                    vendor: str | None, cadence: str, first_day: date, created_by_bot: str | None = None,
                    tainted: bool = False) -> Recurring:
        """A rule whose first charge (``first_day``) the caller logs itself: ``next_due`` is the one after."""
        following = next_occurrence(check_cadence(cadence), first_day, first_day)
        rule = self._rule(user_id, project, amount=amount, currency=currency, note=note, vendor=vendor,
                          cadence=cadence, anchor=first_day, next_due=following, ends_on=None,
                          created_by_bot=created_by_bot, tainted=tainted)
        return await self._store.add(rule)

    async def create(self, user_id: str, project: Project, *, amount: Decimal, currency: str | None,
                     note: str | None, vendor: str | None, cadence: str, anchor_day: date,
                     ends_on: date | None, created_by_bot: str | None = None, tainted: bool = False) -> Recurring:
        """A rule in an open project; its first charge is ``anchor_day`` (made by the next catch-up)."""
        rule = self._rule(user_id, project, amount=amount, currency=currency or project.currency, note=note,
                          vendor=vendor, cadence=cadence, anchor=anchor_day, next_due=anchor_day, ends_on=ends_on,
                          created_by_bot=created_by_bot, tainted=tainted)
        made = await self._store.add(rule)
        await self._events.publish(user_id, {"type": "money_changed", "change": "recurring_changed", "id": made.id})
        return made

    async def get(self, user_id: str, rule_id: str) -> Recurring | None:
        return await self._store.get(user_id, rule_id)

    async def list(self, user_id: str, project_id: str | None = None) -> tuple[Recurring, ...]:
        return await self._store.list(user_id, project_id)

    async def update(self, user_id: str, rule_id: str, changes: Mapping[str, Any]) -> Recurring | None:
        current = await self._store.get(user_id, rule_id)
        if current is None:
            return None
        ends_on = changes.get("ends_on")
        if ends_on is not None and ends_on < current.anchor_day:
            raise ValueError(ENDS_BEFORE_START_TEXT)
        updated = await self._store.update(user_id, rule_id, changes)
        if updated is not None:
            await self._events.publish(user_id, {"type": "money_changed", "change": "recurring_changed", "id": rule_id})
        return updated

    async def delete(self, user_id: str, rule_id: str) -> bool:
        deleted = await self._store.delete(user_id, rule_id)
        if deleted:
            await self._events.publish(user_id, {"type": "money_changed", "change": "recurring_changed", "id": rule_id})
        return deleted

    async def delete_for_project(self, user_id: str, project_id: str) -> int:
        return await self._store.delete_for_project(user_id, project_id)

    async def upcoming(self, user_id: str, project_id: str | None = None,
                       today: date | None = None) -> tuple[UpcomingCharge, ...]:
        """The charges due after today and within ``UPCOMING_CHARGES_DAYS``, soonest first. Catches up first, so
        none of them is already due. Paused (archived-project) rules and ended ones have none."""
        day = today or date.fromisoformat(today_madrid())
        await self.catch_up(user_id, day)
        active = {p.id for p in await self._projects.list(user_id) if p.status != _ARCHIVED}
        through = day + timedelta(days=UPCOMING_CHARGES_DAYS)
        found = [
            UpcomingCharge(rule.id, rule.project_id, when.isoformat(), rule.amount, rule.currency, rule.description)
            for rule in await self._store.list(user_id, project_id) if rule.project_id in active
            for when in occurrences(rule, through, _UPCOMING_LIMIT) if when > day]
        return tuple(sorted(found, key=lambda charge: (charge.day, charge.recurring_id)))
